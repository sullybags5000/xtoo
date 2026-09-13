"""Report how close the nearest vectors are to a query, for choosing a relevance limit.

Semantic search returns the closest vectors however far away they are, so a limit
decides what counts as close enough to offer. The right value depends on the corpus:
one full of boilerplate, encoded blobs or near-duplicates has noise closer to
everything than a clean one does.

Run with a question that should match and one that should not:

    python scripts/vector_distances.py "why did the upgrade fail" "recipe for bread"

Distances run from 0 (identical direction) to 2 (opposite). Anything at or below
vectors.MAX_DISTANCE is currently offered.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xtoo import vectors  # noqa: E402
from xtoo.config import config_path, load_settings  # noqa: E402
from xtoo.store import Store  # noqa: E402


def distances(store, encode, text, count):
    vector = vectors.pack(encode([text])[0])
    with store.connect() as db:
        vectors.prepare(db)
        return [
            (row["distance"], row["document_id"])
            for row in db.execute(
                "SELECT document_id, distance FROM vectors WHERE embedding MATCH ? AND k = ? "
                "ORDER BY distance",
                (vector, count),
            )
        ]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("queries", nargs="+")
    parser.add_argument("--config", type=Path, default=config_path())
    parser.add_argument("--count", type=int, default=10, help="Nearest vectors to report")
    arguments = parser.parse_args()

    store = Store(load_settings(arguments.config).data_dir)
    if not vectors.ready(store):
        parser.exit(1, "No vectors are built. Run: xtoo embed\n")
    encode = vectors.embedder()
    print(f"current limit: {vectors.MAX_DISTANCE}\n")
    for text in arguments.queries:
        found = distances(store, encode, text, arguments.count)
        offered = sum(1 for distance, _ in found if distance <= vectors.MAX_DISTANCE)
        numbers = "  ".join(f"{distance:.3f}" for distance, _ in found)
        print(f"{text}\n  {numbers}\n  {offered} of {len(found)} within the limit\n")


if __name__ == "__main__":
    main()
