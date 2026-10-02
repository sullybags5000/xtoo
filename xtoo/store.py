import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from .enrich import ENRICHMENT_VERSION

TABLES = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    root TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    modified_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    content TEXT NOT NULL,
    document_ns INTEGER NOT NULL DEFAULT 0,
    thread TEXT NOT NULL DEFAULT '',
    automated INTEGER NOT NULL DEFAULT 0,
    enriched INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS folders (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    mtime_ns INTEGER NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS failures (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    modified_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    failed_at REAL NOT NULL,
    message TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS entities (
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (document_id, kind, name)
) WITHOUT ROWID;
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    title, content, content='documents', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2', prefix='2 3 4'
);
"""

# Applied after TABLES, because an index created before its column exists fails on an
# index built by an earlier version.
INDEXES = """
CREATE INDEX IF NOT EXISTS documents_thread ON documents(thread) WHERE thread <> '';
CREATE INDEX IF NOT EXISTS documents_recent ON documents(document_ns DESC, id DESC);
CREATE INDEX IF NOT EXISTS entities_name ON entities(name);
CREATE TRIGGER IF NOT EXISTS documents_insert AFTER INSERT ON documents BEGIN
    INSERT INTO search_index(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS documents_delete AFTER DELETE ON documents BEGIN
    INSERT INTO search_index(search_index, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;
"""

# Fires only when indexed text changes. An unqualified UPDATE trigger would rewrite the
# full-text index for metadata-only writes, which is ruinous on a large index.
UPDATE_TRIGGER = """
CREATE TRIGGER documents_update AFTER UPDATE OF title, content ON documents BEGIN
    INSERT INTO search_index(search_index, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO search_index(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
"""

# Older indexes predate document_ns, so fall back to the file timestamp until migrated.
DATE_COLUMN = "CASE WHEN d.document_ns > 0 THEN d.document_ns ELSE d.modified_ns END"
# Ranking scaffolding that callers should never see.
INTERNAL = {"score", "thread_key", "position"}
# Grouping reads a bounded window of the best matches. Collapsing every match would
# mean a window function over the whole index on each keystroke.
CANDIDATES = 2000
COLUMNS = (
    f"d.id, d.title, d.path, d.kind, d.size, d.thread, d.automated, {DATE_COLUMN} AS document_ns"
)


# A quoted phrase, closed or running to the end, or a bare token; either may be negated.
TOKEN = re.compile(r'(-?)"([^"]*)"?|(-?)(\S+)')
WORD = re.compile(r"[^\W_]+", re.UNICODE)
MAX_TERMS = 32


def parse(query):
    """Full-text expressions for what a query requires and what it excludes, and its
    plain words for semantic search.

    Bare words match as prefixes, so results arrive while typing. A quoted phrase
    matches those words in that order. A leading `-` excludes a word or phrase
    exactly. Only word characters reach FTS5, each inside quotes, so user input is
    never read as an FTS operator or as SQL.
    """
    required, excluded, words = [], [], []
    budget = MAX_TERMS
    for token in TOKEN.finditer(query):
        quoted = token.group(2) is not None
        negated = bool(token.group(1) if quoted else token.group(3))
        terms = WORD.findall(token.group(2) if quoted else token.group(4))[:budget]
        if not terms:
            continue
        budget -= len(terms)
        if negated:
            excluded.append('"' + " ".join(terms) + '"')
        elif quoted:
            required.append('"' + " ".join(terms) + '"')
            words += terms
        else:
            required += ['"' + term + '"*' for term in terms]
            words += terms
        if not budget:
            break
    return " AND ".join(required), " OR ".join(excluded), " ".join(words)


def like(text):
    """A LIKE pattern matching the text literally, for use with ESCAPE '\\'."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def shaped(row, thread_size=None):
    item = {key: value for key, value in dict(row).items() if key not in INTERNAL}
    if thread_size is not None:
        item["thread_size"] = thread_size
    return item


class Batch:
    """Writes queued during a scan and applied together in one short transaction.
    Opening a connection and syncing to disk once per file is most of the cost of a
    first scan, and queuing rather than holding a transaction open means no lock is
    held while files are read, so other writers are never kept waiting on a scan."""

    def __init__(self, store, size, seconds, failed):
        self.store = store
        self.size = size
        self.seconds = seconds
        self.failed = failed
        self.queue = []
        self.started = time.monotonic()

    def upsert(self, **fields):
        self.queue.append(("upsert", fields))

    def remove(self, paths):
        self.queue.append(("remove", {"paths": list(paths)}))

    def record_failure(self, **fields):
        self.queue.append(("record_failure", fields))

    def record_folders(self, root, times):
        self.queue.append(("record_folders", {"root": root, "times": times}))

    def tick(self):
        """Apply the queue once enough has accumulated. The time limit bounds how long
        new results take to appear in searches."""
        if len(self.queue) >= self.size or (
            self.queue and time.monotonic() - self.started >= self.seconds
        ):
            self.flush()

    def flush(self):
        queue, self.queue = self.queue, []
        self.started = time.monotonic()
        if not queue:
            return
        db = sqlite3.connect(self.store.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        self.store._local.db = db
        failed = []
        try:
            db.execute("BEGIN IMMEDIATE")
            for name, fields in queue:
                # A write that fails is undone alone, as it was when each had its own
                # transaction.
                db.execute("SAVEPOINT write")
                try:
                    getattr(self.store, name)(**fields)
                except sqlite3.Error as exc:
                    db.execute("ROLLBACK TO write")
                    if name != "upsert":
                        raise
                    # Do not continue serving old text after a failed refresh.
                    self.store.remove([fields["path"]])
                    self.store.record_failure(
                        path=fields["path"],
                        root=fields["root"],
                        modified_ns=fields["modified_ns"],
                        size=fields["size"],
                        message=str(exc),
                    )
                    failed.append((fields["path"], exc))
                db.execute("RELEASE write")
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            self.store._local.db = None
            db.close()
        for path, exc in failed:
            self.failed(path, exc)


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "index.sqlite3"
        self._local = threading.local()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(TABLES)
            self.upgrade(db)
            db.executescript(INDEXES)
        self.path.chmod(0o600)

    def upgrade(self, db):
        columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
        for name, definition in (
            ("document_ns", "INTEGER NOT NULL DEFAULT 0"),
            ("thread", "TEXT NOT NULL DEFAULT ''"),
            ("automated", "INTEGER NOT NULL DEFAULT 0"),
            ("enriched", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
        db.execute("DROP TRIGGER IF EXISTS documents_update")
        db.executescript(UPDATE_TRIGGER)

    @contextmanager
    def connect(self):
        shared = getattr(self._local, "db", None)
        if shared is not None:
            # A batch is applying its queue; it owns the transaction.
            yield shared
            return
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def batch(self, failed, size=500, seconds=2.0):
        """Queue writes until the block ends, applying them in chunks. `failed` is
        called with the path and error of any document that could not be stored."""
        batch = Batch(self, size, seconds, failed)
        yield batch
        batch.flush()

    def upsert(
        self,
        *,
        path,
        root,
        title,
        kind,
        modified_ns,
        size,
        content,
        document_ns=0,
        thread="",
        automated=0,
        entities=(),
        enriched=ENRICHMENT_VERSION,
    ):
        with self.connect() as db:
            document_id = db.execute(
                """INSERT INTO documents(path, root, title, kind, modified_ns, size, content,
                document_ns, thread, automated, enriched)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET root=excluded.root, title=excluded.title,
                kind=excluded.kind, modified_ns=excluded.modified_ns,
                size=excluded.size, content=excluded.content,
                document_ns=excluded.document_ns, thread=excluded.thread,
                automated=excluded.automated, enriched=excluded.enriched
                RETURNING id""",
                (
                    path,
                    root,
                    title,
                    kind,
                    modified_ns,
                    size,
                    content,
                    document_ns,
                    thread,
                    automated,
                    enriched,
                ),
            ).fetchone()[0]
            self.link(db, document_id, entities)
            db.execute("DELETE FROM failures WHERE path = ?", (path,))

    def link(self, db, document_id, entities):
        db.execute("DELETE FROM entities WHERE document_id = ?", (document_id,))
        db.executemany(
            "INSERT OR IGNORE INTO entities(document_id, kind, name) VALUES (?, ?, ?)",
            ((document_id, kind, name) for kind, name in entities),
        )

    def inventory(self, root):
        with self.connect() as db:
            return {
                row["path"]: (row["modified_ns"], row["size"])
                for row in db.execute(
                    "SELECT path, modified_ns, size FROM documents WHERE root = ?", (root,)
                )
            }

    def remove(self, paths):
        with self.connect() as db:
            paths = [(p,) for p in paths]
            db.executemany("DELETE FROM documents WHERE path = ?", paths)
            db.executemany("DELETE FROM failures WHERE path = ?", paths)

    def record_failure(self, *, path, root, modified_ns, size, message):
        """Remember that a file could not be read, so it is not read again unchanged."""
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO failures(path, root, modified_ns, size, failed_at, "
                "message) VALUES (?, ?, ?, ?, ?, ?)",
                (path, root, modified_ns, size, time.time(), message),
            )

    def failures(self, root):
        with self.connect() as db:
            return {
                row["path"]: dict(row)
                for row in db.execute("SELECT * FROM failures WHERE root = ?", (root,))
            }

    def retain_roots(self, roots):
        with self.connect() as db:
            existing = [row[0] for row in db.execute("SELECT DISTINCT root FROM documents")]
            existing += [row[0] for row in db.execute("SELECT DISTINCT root FROM failures")]
            dropped = [(r,) for r in set(existing) if r not in roots]
            db.executemany("DELETE FROM documents WHERE root = ?", dropped)
            db.executemany("DELETE FROM failures WHERE root = ?", dropped)

    def stats(self):
        with self.connect() as db:
            return {
                row["kind"]: row["count"]
                for row in db.execute(
                    "SELECT kind, COUNT(*) AS count FROM documents GROUP BY kind ORDER BY kind"
                )
            }

    def document(self, document_id):
        with self.connect() as db:
            row = db.execute(
                f"SELECT d.*, {DATE_COLUMN} AS document_ns FROM documents d WHERE d.id = ?",
                (document_id,),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            item["entities"] = [
                dict(entity)
                for entity in db.execute(
                    "SELECT kind, name FROM entities WHERE document_id = ? ORDER BY kind, name",
                    (document_id,),
                )
            ]
            return item

    def entities(self, name, exclude=()):
        """Every indexed name that starts with the given text, for browsing links,
        counting only documents outside the excluded paths."""
        conditions, params = self.predicates(exclude=exclude)
        narrowing = "".join(f" AND {condition}" for condition in conditions)
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    f"""SELECT e.kind, e.name, COUNT(*) AS count FROM entities e
                    JOIN documents d ON d.id = e.document_id
                    WHERE e.name LIKE ? ESCAPE '\\'{narrowing} GROUP BY e.kind, e.name
                    ORDER BY count DESC, e.name LIMIT 50""",
                    (like(name) + "%", *params),
                )
            ]

    def hydrate(self, db, ids, expression=""):
        """Full rows for a page of ids, in order. Snippets cost several times what
        ranking does, so they are computed here and not across every candidate."""
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        if expression:
            rows = db.execute(
                f"SELECT {COLUMNS}, snippet(search_index, 1, '', '', ' … ', 36) AS snippet "
                f"FROM documents d JOIN search_index ON search_index.rowid = d.id "
                f"WHERE search_index MATCH ? AND d.id IN ({marks})",
                (expression, *ids),
            )
        else:
            rows = db.execute(
                f"SELECT {COLUMNS}, substr(d.content, 1, 240) AS snippet "
                f"FROM documents d WHERE d.id IN ({marks})",
                tuple(ids),
            )
        found = {row["id"]: shaped(row, 1) for row in rows}
        return [found[document_id] for document_id in ids if document_id in found]

    def threads_of(self, ids):
        """Conversation keys for a set of ids, for grouping a ranking built outside SQL."""
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        with self.connect() as db:
            return {
                row["id"]: row["thread"]
                for row in db.execute(
                    f"SELECT id, thread FROM documents WHERE id IN ({marks})", tuple(ids)
                )
            }

    def by_ids(self, ids):
        """Documents in the order given, for rankings produced outside SQL."""
        with self.connect() as db:
            return self.hydrate(db, ids)

    def predicates(
        self, kind="", entity="", since=0, until=0, people_only=False, exclude=(), without=""
    ):
        """SQL conditions and parameters shared by every way of searching. `without` is
        a full-text expression for words a query excludes, from `parse`."""
        conditions = []
        params = []
        if without:
            conditions.append(
                "d.id NOT IN (SELECT rowid FROM search_index WHERE search_index MATCH ?)"
            )
            params.append(without)
        if kind:
            conditions.append("d.kind = ?")
            params.append(kind)
        if entity:
            conditions.append("d.id IN (SELECT document_id FROM entities WHERE name = ?)")
            params.append(entity)
        if since:
            conditions.append(f"{DATE_COLUMN} >= ?")
            params.append(since)
        if until:
            conditions.append(f"{DATE_COLUMN} <= ?")
            params.append(until)
        if people_only:
            conditions.append("d.automated = 0")
        for fragment in exclude:
            conditions.append("d.path NOT LIKE ? ESCAPE '\\'")
            params.append(f"%{like(fragment)}%")
        return conditions, params

    def narrow(self, ids, **predicates):
        """Which of the given ids satisfy the predicates, for rankings built outside SQL."""
        if not ids:
            return set()
        conditions, params = self.predicates(**predicates)
        if not conditions:
            return set(ids)
        marks = ",".join("?" * len(ids))
        where = " AND ".join(conditions)
        with self.connect() as db:
            return {
                row[0]
                for row in db.execute(
                    f"SELECT d.id FROM documents d WHERE d.id IN ({marks}) AND {where}",
                    (*ids, *params),
                )
            }

    def remember(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, str(value)))

    def recall(self, key, default=""):
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def folder_times(self, root):
        with self.connect() as db:
            return {
                row["path"]: row["mtime_ns"]
                for row in db.execute("SELECT path, mtime_ns FROM folders WHERE root = ?", (root,))
            }

    def record_folders(self, root, times):
        with self.connect() as db:
            db.execute("DELETE FROM folders WHERE root = ?", (root,))
            db.executemany(
                "INSERT OR REPLACE INTO folders(path, root, mtime_ns) VALUES (?, ?, ?)",
                ((path, root, mtime) for path, mtime in times.items()),
            )

    def paths_under(self, root, directory, failed=False):
        """Indexed paths directly inside one directory, or with `failed` those that could
        not be read, for skipping unchanged folders."""
        table = "failures" if failed else "documents"
        with self.connect() as db:
            return [
                row[0]
                for row in db.execute(
                    f"SELECT path FROM {table} WHERE root = ? AND path LIKE ? ESCAPE '\\' "
                    "AND instr(substr(path, ?), '/') = 0",
                    (root, f"{like(directory)}/%", len(directory) + 2),
                )
            ]

    def search(
        self,
        query="",
        kind="",
        offset=0,
        limit=40,
        entity="",
        collapse=False,
        since=0,
        until=0,
        people_only=False,
        exact=False,
        exclude=(),
    ):
        # If exact mode is on, wrap the query in quotes for exact phrase matching
        if exact and query.strip():
            query = f'"{query}"'
        expression, without, _ = parse(query)
        empty = {"items": [], "total": 0, "matched": 0, "offset": offset, "limit": limit}
        conditions, params = self.predicates(
            kind=kind,
            entity=entity,
            since=since,
            until=until,
            people_only=people_only,
            exclude=exclude,
            without=without,
        )
        source = "documents d"
        snippet = "substr(d.content, 1, 240)"
        score = "0"
        if expression:
            source += " JOIN search_index ON search_index.rowid = d.id"
            # The match must lead, so its parameter goes before the narrowing ones.
            conditions.insert(0, "search_index MATCH ?")
            params.insert(0, expression)
            snippet = "snippet(search_index, 1, '', '', ' … ', 36)"
            score = "bm25(search_index, 5.0, 1.0)"
        elif query.strip() and not without:
            return empty
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        # A constant score would stop the date index being used when browsing.
        order = "score, document_ns DESC, id DESC" if expression else "document_ns DESC, id DESC"
        selection = f"{COLUMNS}, {score} AS score, {snippet} AS snippet"
        with self.connect() as db:
            if not collapse:
                total = db.execute(f"SELECT COUNT(*) FROM {source}{where}", params).fetchone()[0]
                rows = db.execute(
                    f"SELECT {selection} FROM {source}{where} ORDER BY {order} LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                ).fetchall()
                items = [shaped(row, 1) for row in rows]
                matched = total
            else:
                # Documents outside a conversation each stand alone.
                key = "CASE WHEN d.thread = '' THEN 'id:' || d.id ELSE d.thread END"
                candidates = (
                    f"SELECT d.id AS id, {key} AS thread_key, {score} AS score, "
                    f"{DATE_COLUMN} AS document_ns FROM {source}{where} "
                    f"ORDER BY {order} LIMIT {CANDIDATES}"
                )
                rows = db.execute(
                    f"WITH ranked AS MATERIALIZED ({candidates}), groups AS ("
                    f"SELECT *, ROW_NUMBER() OVER (PARTITION BY thread_key ORDER BY {order}) "
                    f"AS position, COUNT(*) OVER (PARTITION BY thread_key) AS thread_size "
                    f"FROM ranked) SELECT id, thread_size, "
                    f"(SELECT COUNT(DISTINCT thread_key) FROM ranked) AS total "
                    f"FROM groups WHERE position = 1 ORDER BY {order} LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                ).fetchall()
                matched = db.execute(f"SELECT COUNT(*) FROM {source}{where}", params).fetchone()[0]
                total = (
                    rows[0]["total"]
                    if rows
                    else db.execute(
                        f"SELECT COUNT(DISTINCT thread_key) FROM ({candidates})", params
                    ).fetchone()[0]
                )
                sizes = {row["id"]: row["thread_size"] for row in rows}
                items = self.hydrate(db, list(sizes), expression)
                for item in items:
                    item["thread_size"] = sizes[item["id"]]
            return {
                "items": items,
                "total": total,
                "matched": matched,
                "offset": offset,
                "limit": limit,
            }
