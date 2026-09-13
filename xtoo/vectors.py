"""Optional semantic search over the same index file.

Embeddings are computed on this machine by a small static model and stored beside the
documents, so nothing is sent anywhere and no service has to be running. Install with
`pip install -e '.[vectors]'` and build with `xtoo embed`; without that, everything
here stays dormant and full-text search is unaffected.
"""

import struct

MODEL = "minishlab/potion-base-8M"
DIMENSIONS = 256
# Vectors are stored with unit length, so distance depends on direction alone and can be
# compared against a fixed threshold. Raise when that storage changes, which makes an
# index built the old way rebuild itself rather than compare incomparable numbers.
FORMAT = "unit-length-2"
# Nearest-neighbour search returns the closest vectors however far away they are, so
# without a limit a search for something absent still returns a page of noise. Unit
# vectors put this at roughly a quarter cosine similarity.
MAX_DISTANCE = 1.25
CHUNK = 2000
OVERLAP = 200
# Nearest-neighbour search scans every stored vector, so each extra window per document
# is paid on every query. Two windows cover the substance of a message; what follows in
# a long mail is usually a quoted chain that would only add near-duplicate vectors.
MAX_CHUNKS = 2
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
CREATE TABLE IF NOT EXISTS vector_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
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
    """Bytes for a unit-length vector, or None for text with no direction at all.

    Text the model cannot tokenise — whitespace, NUL padding, control characters,
    replacement characters from a failed decode — embeds to zeros. A zero vector is
    equidistant from everything, which puts it nearer any query than genuinely
    unrelated text, so it is never stored.
    """
    values = [float(value) for value in vector]
    length = sum(value * value for value in values) ** 0.5
    if not length:
        return None
    return struct.pack(f"{len(values)}f", *(value / length for value in values))


_LOADED = {}


def embedder(model_name: str = MODEL):
    """Load the model once per process; it costs most of a second each time."""
    if model_name not in _LOADED:
        from model2vec import StaticModel

        model = StaticModel.from_pretrained(model_name)
        _LOADED[model_name] = lambda texts: model.encode(list(texts), show_progress_bar=False)
    return _LOADED[model_name]


def prepare(db):
    import sqlite_vec

    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.executescript(TABLES)
    return db


def setting_of(db, key) -> str:
    row = db.execute("SELECT value FROM vector_settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else ""


def model_of(db) -> str:
    """The model the stored vectors were built with, which queries must match."""
    return setting_of(db, "model")


def pending(db) -> int:
    return db.execute(
        """SELECT COUNT(*) FROM documents d LEFT JOIN embedded e ON e.document_id = d.id
        WHERE e.document_id IS NULL OR e.modified_ns <> d.modified_ns"""
    ).fetchone()[0]


def build(
    store, encode=None, report=None, batch: int = 500, model_name: str = MODEL, rebuild=False
):
    """Embed every document that has no current vectors. Safe to interrupt and resume."""
    encode = encode or embedder(model_name)
    documents = chunks = 0
    with store.connect() as db:
        prepare(db)
        # Vectors from two different models cannot be compared, so changing the model
        # discards what is there rather than silently mixing them.
        built_before = db.execute("SELECT COUNT(*) FROM embedded").fetchone()[0]
        # Vectors built before these were recorded came from the default model, stored
        # the old way.
        previous = model_of(db) or (MODEL if built_before else "")
        stored_format = setting_of(db, "format") or ("unrecorded" if built_before else FORMAT)
        if rebuild or (previous and previous != model_name) or stored_format != FORMAT:
            if report and built_before:
                reason = "Model changed" if previous != model_name else "Vector storage changed"
                report(f"{reason}; rebuilding every vector")
            db.execute("DELETE FROM vectors")
            db.execute("DELETE FROM embedded")
        db.executemany(
            "INSERT OR REPLACE INTO vector_settings(key, value) VALUES (?, ?)",
            (("model", model_name), ("format", FORMAT)),
        )
        remaining = pending(db)
        # Vectors for documents that have since been removed.
        orphans = [
            row[0]
            for row in db.execute(
                "SELECT document_id FROM embedded "
                "WHERE document_id NOT IN (SELECT id FROM documents)"
            )
        ]
        if orphans:
            marks = ",".join("?" * len(orphans))
            db.execute(f"DELETE FROM vectors WHERE document_id IN ({marks})", orphans)
            db.execute(f"DELETE FROM embedded WHERE document_id IN ({marks})", orphans)
    if report:
        report(f"{remaining:,} documents to embed")
    while True:
        with store.connect() as db:
            prepare(db)
            rows = db.execute(
                """SELECT d.id, d.title, d.content, d.modified_ns,
                e.document_id IS NOT NULL AS embedded_before FROM documents d
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
            # Deleting from a vec0 table scans it, so never delete for a document that
            # has no vectors yet, and clear the rest in one statement rather than one
            # scan each. Per-document deletes cost hours over a large index.
            replacing = [row["id"] for row in rows if row["embedded_before"]]
            if replacing:
                marks = ",".join("?" * len(replacing))
                db.execute(f"DELETE FROM vectors WHERE document_id IN ({marks})", replacing)
            stored = {}
            for document_id, vector in zip(owners, vectors):
                embedding = pack(vector)
                if embedding is None:
                    continue
                db.execute(
                    "INSERT INTO vectors(document_id, embedding) VALUES (?, ?)",
                    (document_id, embedding),
                )
                stored[document_id] = stored.get(document_id, 0) + 1
            # A document with nothing embeddable still records the attempt, so it is
            # not examined again on every run.
            db.executemany(
                "INSERT OR REPLACE INTO embedded(document_id, modified_ns, chunks) "
                "VALUES (?, ?, ?)",
                [(row["id"], row["modified_ns"], stored.get(row["id"], 0)) for row in rows],
            )
            documents += len(rows)
            chunks += sum(stored.values())
        if report:
            report(f"  embedded {documents:,} of {remaining:,}")


def similar(store, query: str, limit: int = FUSION_DEPTH, encode=None, model_name: str = ""):
    """Document ids ordered by how close their closest chunk is to the query."""
    if encode is None:
        with store.connect() as db:
            prepare(db)
            encode = embedder(model_name or model_of(db) or MODEL)
    vector = pack(encode([query])[0])
    if vector is None:
        return []
    with store.connect() as db:
        prepare(db)
        rows = db.execute(
            "SELECT document_id, distance FROM vectors WHERE embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (vector, max(1, limit) * MAX_CHUNKS),
        ).fetchall()
    best = {}
    for row in rows:
        if row["distance"] > MAX_DISTANCE:
            continue
        best.setdefault(row["document_id"], row["distance"])
    return list(best)[:limit]


def fuse(*rankings):
    scores = {}
    for ranking in rankings:
        for position, document_id in enumerate(ranking):
            scores[document_id] = scores.get(document_id, 0) + 1 / (FUSION_CONSTANT + position + 1)
    return sorted(scores, key=lambda document_id: -scores[document_id])


def group(store, ranking):
    """Keep the best-ranked document of each conversation, with how many it stands for."""
    threads = store.threads_of(ranking)
    leaders = {}
    sizes = {}
    order = []
    for document_id in ranking:
        key = threads.get(document_id) or f"id:{document_id}"
        if key in leaders:
            sizes[leaders[key]] += 1
        else:
            leaders[key] = document_id
            sizes[document_id] = 1
            order.append(document_id)
    return order, sizes


def search(store, query, encode=None, model_name: str = ""):
    """Full-text and vector results combined by reciprocal rank fusion.

    Both arms are narrowed by the same predicates through `store.narrow`, so a filter
    cannot apply to one and quietly not the other.
    """
    lexical = store.search(
        query.text,
        kind=query.kind,
        limit=FUSION_DEPTH,
        entity=query.entity,
        since=query.since,
        until=query.until,
        people_only=query.people_only,
        exclude=query.exclude,
    )
    snippets = {item["id"]: item["snippet"] for item in lexical["items"]}
    ranking = [item["id"] for item in lexical["items"]]
    if query.text.strip():
        meanings = similar(store, query.text, FUSION_DEPTH, encode=encode, model_name=model_name)
        allowed = store.narrow(meanings, **query.narrowing())
        ranking = fuse(ranking, [document_id for document_id in meanings if document_id in allowed])
    matched = len(ranking)
    sizes = {}
    if query.collapse:
        ranking, sizes = group(store, ranking)
    page = ranking[query.offset : query.offset + query.limit]
    items = [
        {
            **item,
            "snippet": snippets.get(item["id"], item["snippet"]),
            "thread_size": sizes.get(item["id"], 1),
        }
        for item in store.by_ids(page)
    ]
    return {
        "items": items,
        "total": len(ranking),
        "matched": matched,
        "offset": query.offset,
        "limit": query.limit,
    }
