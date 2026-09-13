import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

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
    thread TEXT NOT NULL DEFAULT ''
);
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
COLUMNS = f"d.id, d.title, d.path, d.kind, d.size, d.thread, {DATE_COLUMN} AS document_ns"


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "index.sqlite3"
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
        ):
            if name not in columns:
                db.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
        db.execute("DROP TRIGGER IF EXISTS documents_update")
        db.executescript(UPDATE_TRIGGER)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

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
        entities=(),
    ):
        with self.connect() as db:
            document_id = db.execute(
                """INSERT INTO documents(path, root, title, kind, modified_ns, size, content,
                document_ns, thread) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET root=excluded.root, title=excluded.title,
                kind=excluded.kind, modified_ns=excluded.modified_ns,
                size=excluded.size, content=excluded.content,
                document_ns=excluded.document_ns, thread=excluded.thread
                RETURNING id""",
                (path, root, title, kind, modified_ns, size, content, document_ns, thread),
            ).fetchone()[0]
            self.link(db, document_id, entities)

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
            db.executemany("DELETE FROM documents WHERE path = ?", ((p,) for p in paths))

    def retain_roots(self, roots):
        with self.connect() as db:
            existing = [row[0] for row in db.execute("SELECT DISTINCT root FROM documents")]
            db.executemany(
                "DELETE FROM documents WHERE root = ?", ((r,) for r in existing if r not in roots)
            )

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

    def entities(self, name):
        """Every indexed name that starts with the given text, for browsing links."""
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    """SELECT kind, name, COUNT(*) AS count FROM entities
                    WHERE name LIKE ? ESCAPE '\\' GROUP BY kind, name
                    ORDER BY count DESC, name LIMIT 50""",
                    (name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",),
                )
            ]

    def by_ids(self, ids):
        """Documents in the order given, for rankings produced outside SQL."""
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        with self.connect() as db:
            found = {
                row["id"]: {**dict(row), "thread_size": 1}
                for row in db.execute(
                    f"SELECT {COLUMNS}, substr(d.content, 1, 240) AS snippet "
                    f"FROM documents d WHERE d.id IN ({marks})",
                    tuple(ids),
                )
            }
        return [found[document_id] for document_id in ids if document_id in found]

    def kinds_of(self, ids, kind):
        """Which of the given ids are of one file type."""
        if not ids:
            return set()
        marks = ",".join("?" * len(ids))
        with self.connect() as db:
            return {
                row[0]
                for row in db.execute(
                    f"SELECT id FROM documents WHERE kind = ? AND id IN ({marks})",
                    (kind, *ids),
                )
            }

    def search(self, query="", kind="", offset=0, limit=40, entity="", collapse=False):
        # Treat user input as literal words, never as FTS operators or SQL.
        terms = re.findall(r"[^\W_]+", query, re.UNICODE)[:32]
        expression = " AND ".join('"' + term + '"*' for term in terms)
        empty = {"items": [], "total": 0, "offset": offset, "limit": limit}
        params = []
        conditions = []
        source = "documents d"
        snippet = "substr(d.content, 1, 240)"
        score = "0"
        if expression:
            source += " JOIN search_index ON search_index.rowid = d.id"
            conditions.append("search_index MATCH ?")
            params.append(expression)
            snippet = "snippet(search_index, 1, '', '', ' … ', 36)"
            score = "bm25(search_index, 5.0, 1.0)"
        elif query.strip():
            return empty
        if kind:
            conditions.append("d.kind = ?")
            params.append(kind)
        if entity:
            conditions.append("d.id IN (SELECT document_id FROM entities WHERE name = ?)")
            params.append(entity)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        order = "score, document_ns DESC, id DESC"
        selection = f"{COLUMNS}, {score} AS score, {snippet} AS snippet"
        with self.connect() as db:
            if not collapse:
                total = db.execute(f"SELECT COUNT(*) FROM {source}{where}", params).fetchone()[0]
                rows = db.execute(
                    f"SELECT {selection} FROM {source}{where} ORDER BY {order} LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                ).fetchall()
                items = [{**dict(row), "thread_size": 1} for row in rows]
            else:
                # Documents outside a conversation each stand alone.
                key = "CASE WHEN d.thread = '' THEN 'id:' || d.id ELSE d.thread END"
                inner = f"SELECT {selection}, {key} AS thread_key FROM {source}{where}"
                ranked = (
                    f"SELECT *, ROW_NUMBER() OVER (PARTITION BY thread_key ORDER BY {order}) "
                    f"AS position, COUNT(*) OVER (PARTITION BY thread_key) AS thread_size "
                    f"FROM ({inner})"
                )
                total = db.execute(
                    f"SELECT COUNT(*) FROM (SELECT DISTINCT thread_key FROM ({inner}))", params
                ).fetchone()[0]
                rows = db.execute(
                    f"SELECT * FROM ({ranked}) WHERE position = 1 "
                    f"ORDER BY {order} LIMIT ? OFFSET ?",
                    (*params, limit, offset),
                ).fetchall()
                items = [
                    {key: value for key, value in dict(row).items() if key != "position"}
                    for row in rows
                ]
            return {"items": items, "total": total, "offset": offset, "limit": limit}
