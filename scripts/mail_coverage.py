"""Report what an exported mail tree already covers, so a top-up export can start there.

Run from the repository with the virtual environment active:

    python scripts/mail_coverage.py /mnt/c/Users/YOU/Documents/Outlook_MSG_Export

Each directory is reported separately, because Outlook folders are usually exported
one per directory and each stops at a different date. Messages that cannot be parsed
are counted as unreadable rather than silently ignored.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from xtoo.mail import EMAIL_EXTENSIONS, received  # noqa: E402


def survey(root: Path):
    folders = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EMAIL_EXTENSIONS:
            continue
        group = folders.setdefault(
            path.parent, {"count": 0, "unreadable": 0, "first": None, "last": None}
        )
        group["count"] += 1
        try:
            moment = received(path)
        except Exception:
            group["unreadable"] += 1
            continue
        if moment is None:
            group["unreadable"] += 1
            continue
        moment = moment.replace(tzinfo=None)
        group["first"] = min(group["first"] or moment, moment)
        group["last"] = max(group["last"] or moment, moment)
    return folders


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="Directory holding exported .msg/.eml files")
    arguments = parser.parse_args()
    if not arguments.root.is_dir():
        parser.exit(2, f"Not a directory: {arguments.root}\n")

    folders = survey(arguments.root)
    if not folders:
        parser.exit(1, f"No .msg or .eml files under {arguments.root}\n")

    width = max(len(folder.name) for folder in folders)
    print(f"{'folder'.ljust(width)}  {'messages':>8}  {'earliest':>10}  {'latest':>10}  unreadable")
    total = unreadable = 0
    latest = None
    for folder, group in sorted(folders.items(), key=lambda item: str(item[0])):
        first = group["first"].date().isoformat() if group["first"] else "-"
        last = group["last"].date().isoformat() if group["last"] else "-"
        print(
            f"{folder.name.ljust(width)}  {group['count']:>8}  {first:>10}  {last:>10}"
            f"  {group['unreadable'] or '':>10}"
        )
        total += group["count"]
        unreadable += group["unreadable"]
        if group["last"]:
            latest = max(latest or group["last"], group["last"])
    print(f"\n{total} messages in {len(folders)} folders, {unreadable} unreadable")
    if latest:
        print(f"Newest message: {latest:%Y-%m-%d}")
        print(f"Top up with:   -Since '{latest:%Y-%m-%d}'   (per folder, use its own latest date)")


if __name__ == "__main__":
    main()
