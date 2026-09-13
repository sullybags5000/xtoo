"""Optional semantic search over the same index file.

Embeddings are computed on this machine by a small static model and stored beside the
documents, so nothing is sent anywhere and no service has to be running. Install with
`pip install -e '.[vectors]'` and build with `xtoo embed`; without that, everything
here stays dormant and full-text search is unaffected.
"""

import struct

MODEL = "minishlab/potion-base-8M"
DIMENSIONS = 256
CHUNK = 1500
OVERLAP = 150
MAX_CHUNKS = 4
FUSION_DEPTH = 200
# Reciprocal rank fusion; 60 is the value from the original formulation.
FUSION_CONSTANT = 60

TABLES = f"""
CREATE VIRTUAL TABLE IF NOT EXISTS vectors USING vec0(
    document_id integer, embedding float[{DIMENSIONS}]
);
CREATE TABLE IF NOT EXISTS embedded (
    document_id INTEGER PRIMARY KEY,
    modified_ns INTEGER NOT NULL,
    chunks INTEGER NOT NULL
);
"""


def available() -> bool:
    try:
        import sqlite_vec  # noqa: F401
    except ImportError:
        return False
    return True


def ready(store) -> bool:
    """Whether semantic search can answer: the extras installed and vectors built."""
    if not available():
        return False
    with store.connect() as db:
        if not db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='embedded'"
        ).fetchone():
            return False
        return db.execute("SELECT COUNT(*) FROM embedded").fetchone()[0] > 0


def pieces(title: str, content: str):
    """Overlapping windows over the start of a document, titled for context."""
    text = f"{title}\n{content}".strip()
    if not text:
        return []
    step = CHUNK - OVERLAP
    return [text[start : start + CHUNK] for start in range(0, len(text), step)][:MAX_CHUNKS]


def pack(vector):
    return struct.pack(f"{len(vector)}f", *(float(value) for value in vector))


def embedder(model_name: str = MODEL):
    from model2vec import StaticModel

    model = StaticModel.from_pretrained(model_name)

    def encode(texts):
        return model.encode(list(texts), show_progress_bar=False)

    return encode


def prepare(db):
    import sqlite_vec

    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.executescript(TABLES)
    return db


def pending(db) -> int:
    return db.execute(
        """SELECT COUNT(*) FROM documents d LEFT JOIN embedded e ON e.document_id = d.id
        WHERE e.document_id IS NULL OR e.modified_ns <> d.modified_ns"""
    ).fetchone()[0]


def build(store, encode=None, report=None, batch: int = 500, model_name: str = MODEL):
    """Embed every document that has no current vectors. Safe to interrupt and resume."""
    encode = encode or embedder(model_name)
    documents = chunks = 0
    with store.connect() as db:
        prepare(db)
        remaining = pending(db)
        # Vectors for documents that have since been removed.
        for (orphan,) in db.execute(
            "SELECT document_id FROM embedded WHERE document_id NOT IN (SELECT id FROM documents)"
        ).fetchall():
            db.execute("DELETE FROM vectors WHERE document_id = ?", (orphan,))
            db.execute("DELETE FROM embedded WHERE document_id = ?", (orphan,))
    if report:
        report(f"{remaining:,} documents to embed")
    while True:
        with store.connect() as db:
            prepare(db)
            rows = db.execute(
                """SELECT d.id, d.title, d.content, d.modified_ns FROM documents d
                LEFT JOIN embedded e ON e.document_id = d.id
                WHERE e.document_id IS NULL OR e.modified_ns <> d.modified_ns LIMIT ?""",
                (batch,),
            ).fetchall()
            if not rows:
                return {"documents": documents, "chunks": chunks}
            texts = []
            owners = []
            for row in rows:
                for piece in pieces(row["title"], row["content"]):
                    texts.append(piece)
                    owners.append(row["id"])
            vectors = encode(texts) if texts else []
            for row in rows:
                db.execute("DELETE FROM vectors WHERE document_id = ?", (row["id"],))
            for document_id, vector in zip(owners, vectors):
                db.execute(
                    "INSERT INTO vectors(document_id, embedding) VALUES (?, ?)",
                    (document_id, pack(vector)),
                )
            db.executemany(
                "INSERT OR REPLACE INTO embedded(document_id, modified_ns, chunks) "
                "VALUES (?, ?, ?)",
                [(row["id"], row["modified_ns"], owners.count(row["id"])) for row in rows],
            )
            documents += len(rows)
            chunks += len(texts)
        if report:
            report(f"  embedded {documents:,} of {remaining:,}")


def similar(store, query: str, limit: int = FUSION_DEPTH, encode=None, model_name: str = MODEL):
    """Document ids ordered by how close their closest chunk is to the query."""
    encode = encode or embedder(model_name)
    vector = pack(encode([query])[0])
    with store.connect() as db:
        prepare(db)
        rows = db.execute(
            "SELECT document_id, distance FROM vectors WHERE embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (vector, max(1, limit) * MAX_CHUNKS),
        ).fetchall()
    best = {}
    for row in rows:
        document_id = row["document_id"]
        if document_id not in best:
            best[document_id] = row["distance"]
    return list(best)[:limit]


def fuse(*rankings):
    scores = {}
    for ranking in rankings:
        for position, document_id in enumerate(ranking):
            scores[document_id] = scores.get(document_id, 0) + 1 / (FUSION_CONSTANT + position + 1)
    return sorted(scores, key=lambda document_id: -scores[document_id])


def search(store, query="", kind="", offset=0, limit=40, encode=None, model_name: str = MODEL):
    """Full-text and vector results combined by reciprocal rank fusion."""
    lexical = store.search(query, kind=kind, limit=FUSION_DEPTH)
    snippets = {item["id"]: item["snippet"] for item in lexical["items"]}
    ranking = [item["id"] for item in lexical["items"]]
    if query.strip():
        meanings = similar(store, query, FUSION_DEPTH, encode=encode, model_name=model_name)
        if kind:
            allowed = store.kinds_of(meanings, kind)
            meanings = [document_id for document_id in meanings if document_id in allowed]
        ranking = fuse(ranking, meanings)
    page = ranking[offset : offset + limit]
    items = [
        {**item, "snippet": snippets.get(item["id"], item["snippet"])}
        for item in store.by_ids(page)
    ]
    return {"items": items, "total": len(ranking), "offset": offset, "limit": limit}
