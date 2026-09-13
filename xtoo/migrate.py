"""Derive fields for documents indexed before those fields existed, or before they
changed meaning.

Everything is recomputed from the text already in the index, so no source file is
reopened. Documents carry the version of the derivation applied to them, so work is
committed in batches, skips what is already current, and can be interrupted and
resumed on a large index.
"""

from .enrich import ENRICHMENT_VERSION, enrichment

BATCH = 2000


def pending(db) -> int:
    return db.execute(
        "SELECT COUNT(*) FROM documents WHERE enriched < ?", (ENRICHMENT_VERSION,)
    ).fetchone()[0]


def enrich_documents(store, report=None, batch: int = BATCH) -> int:
    """Return how many documents were given dates, conversations, senders and entities."""
    done = 0
    with store.connect() as db:
        remaining = pending(db)
    if report:
        report(f"{remaining:,} documents to enrich")
    while True:
        with store.connect() as db:
            rows = db.execute(
                "SELECT id, title, kind, content, modified_ns FROM documents "
                "WHERE enriched < ? LIMIT ?",
                (ENRICHMENT_VERSION, batch),
            ).fetchall()
            if not rows:
                return done
            for row in rows:
                derived = enrichment(
                    row["content"], row["title"], row["kind"], row["modified_ns"] or 1
                )
                db.execute(
                    "UPDATE documents SET document_ns = ?, thread = ?, automated = ?, "
                    "enriched = ? WHERE id = ?",
                    (
                        derived["document_ns"],
                        derived["thread"],
                        derived["automated"],
                        ENRICHMENT_VERSION,
                        row["id"],
                    ),
                )
                store.link(db, row["id"], derived["entities"])
            done += len(rows)
        if report:
            report(f"  enriched {done:,} of {remaining:,}")
