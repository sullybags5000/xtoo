"""Backfill derived fields for documents indexed before enrichment existed.

Everything is recomputed from the text already in the index, so no source file is
reopened. Work is committed in batches and skips what is already done, which makes
the command safe to interrupt and resume on a large index.
"""

from .enrich import enrichment

BATCH = 2000


def pending(db) -> int:
    return db.execute("SELECT COUNT(*) FROM documents WHERE document_ns = 0").fetchone()[0]


def enrich_documents(store, report=None, batch: int = BATCH) -> int:
    """Return how many documents were given dates, conversations and entities."""
    done = 0
    with store.connect() as db:
        remaining = pending(db)
    if report:
        report(f"{remaining:,} documents to enrich")
    while True:
        with store.connect() as db:
            rows = db.execute(
                "SELECT id, title, kind, content, modified_ns FROM documents "
                "WHERE document_ns = 0 LIMIT ?",
                (batch,),
            ).fetchall()
            if not rows:
                return done
            for row in rows:
                derived = enrichment(
                    row["content"], row["title"], row["kind"], row["modified_ns"] or 1
                )
                db.execute(
                    "UPDATE documents SET document_ns = ?, thread = ? WHERE id = ?",
                    (derived["document_ns"], derived["thread"], row["id"]),
                )
                store.link(db, row["id"], derived["entities"])
            done += len(rows)
        if report:
            report(f"  enriched {done:,} of {remaining:,}")
