import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    root TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    modified_ns INTEGER NOT NULL,
    size INTEGER NOT NULL,
    content TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
    title, content, content='documents', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2', prefix='2 3 4'
);
CREATE TRIGGER IF NOT EXISTS documents_insert AFTER INSERT ON documents BEGIN
    INSERT INTO search_index(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS documents_delete AFTER DELETE ON documents BEGIN
    INSERT INTO search_index(search_index, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
END;
CREATE TRIGGER IF NOT EXISTS documents_update AFTER UPDATE ON documents BEGIN
    INSERT INTO search_index(search_index, rowid, title, content)
    VALUES ('delete', old.id, old.title, old.content);
    INSERT INTO search_index(rowid, title, content) VALUES (new.id, new.title, new.content);
END;
"""


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "index.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def upsert(self, *, path, root, title, kind, modified_ns, size, content):
        with self.connect() as db:
            db.execute(
                """INSERT INTO documents(path, root, title, kind, modified_ns, size, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET root=excluded.root, title=excluded.title,
                kind=excluded.kind, modified_ns=excluded.modified_ns,
                size=excluded.size, content=excluded.content""",
                (path, root, title, kind, modified_ns, size, content),
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
            row = db.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
            return dict(row) if row else None

    def search(self, query="", kind="", offset=0, limit=40):
        # Treat user input as literal words, never as FTS operators or SQL.
        terms = re.findall(r"[^\W_]+", query, re.UNICODE)[:32]
        expression = " AND ".join('"' + term + '"*' for term in terms)
        params = []
        conditions = []
        source = "documents d"
        snippet = "substr(d.content, 1, 240)"
        order = "d.modified_ns DESC, d.id DESC"
        if expression:
            source += " JOIN search_index ON search_index.rowid = d.id"
            conditions.append("search_index MATCH ?")
            params.append(expression)
            snippet = "snippet(search_index, 1, '', '', ' … ', 36)"
            order = "bm25(search_index, 5.0, 1.0), d.modified_ns DESC, d.id DESC"
        elif query.strip():
            return {"items": [], "total": 0, "offset": offset, "limit": limit}
        if kind:
            conditions.append("d.kind = ?")
            params.append(kind)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        with self.connect() as db:
            total = db.execute(f"SELECT COUNT(*) FROM {source}{where}", params).fetchone()[0]
            rows = db.execute(
                f"SELECT d.id, d.title, d.path, d.kind, d.size, d.modified_ns, {snippet} AS snippet "
                f"FROM {source}{where} ORDER BY {order} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "offset": offset,
                "limit": limit,
            }
