"""Estimate how long a large mail export takes to index, and how much index it produces.

Run from the repository with the virtual environment active:

    python scripts/mail_estimate.py /mnt/c/Users/YOU/Documents/Outlook_MSG_Export

A random sample is extracted and written to a throwaway index, so the rate includes
both extraction and SQLite work. Counting the files themselves is the slow part on a
Windows drive; pass --total to skip it if you already know the count.
"""

import argparse
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xtoo.extract import extract_text  # noqa: E402
from xtoo.mail import EMAIL_EXTENSIONS  # noqa: E402
from xtoo.store import Store  # noqa: E402


def duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} seconds"
    if seconds < 5400:
        return f"{seconds / 60:.0f} minutes"
    return f"{seconds / 3600:.1f} hours"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--sample", type=int, default=200, help="Messages to measure")
    parser.add_argument("--total", type=int, help="Known message count, to skip counting")
    arguments = parser.parse_args()
    if not arguments.root.is_dir():
        parser.exit(2, f"Not a directory: {arguments.root}\n")

    total = arguments.total
    if total is None:
        print("Counting messages, which is slow on a Windows drive...", flush=True)
        total = sum(
            1 for path in arguments.root.rglob("*") if path.suffix.lower() in EMAIL_EXTENSIONS
        )
    if not total:
        parser.exit(1, f"No .msg or .eml files under {arguments.root}\n")

    print(f"Sampling {arguments.sample} of {total:,} messages...", flush=True)
    found = []
    for path in arguments.root.rglob("*"):
        if path.suffix.lower() in EMAIL_EXTENSIONS:
            found.append(path)
            if len(found) >= arguments.sample * 40:
                break
    sample = random.sample(found, min(arguments.sample, len(found)))

    directory = Path(tempfile.mkdtemp())
    try:
        store = Store(directory)
        characters = failures = 0
        started = time.monotonic()
        for path in sample:
            try:
                content = extract_text(path, 1_000_000)
            except Exception:
                failures += 1
                continue
            characters += len(content)
            store.upsert(
                path=str(path),
                root=str(arguments.root),
                title=path.name,
                kind=path.suffix.lower()[1:],
                modified_ns=0,
                size=0,
                content=content,
            )
        elapsed = time.monotonic() - started
        index_bytes = sum(f.stat().st_size for f in directory.glob("index.sqlite3*"))
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    rate = len(sample) / elapsed
    print(f"\n{rate:.0f} messages/second, {characters / len(sample):,.0f} characters each")
    if failures:
        print(f"{failures} of {len(sample)} could not be parsed")
    print(f"Full run:   about {duration(total / rate)} for {total:,} messages")
    print(f"Index size: roughly {index_bytes / len(sample) * total / 1e9:.1f} GB")
    print("\nRates vary across folders, and a rescan of unchanged files is much faster.")


if __name__ == "__main__":
    main()
