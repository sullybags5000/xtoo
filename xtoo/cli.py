import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import config_path, data_path, load_settings


def main():
    parser = argparse.ArgumentParser(description="Xtoo local desktop search")
    parser.add_argument(
        "--config", type=Path, default=config_path(), help="Path to configuration TOML"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a configuration outside the repository")
    init.add_argument(
        "--folder", action="append", required=True, help="Folder to index; repeat for more"
    )
    serve = commands.add_parser("serve", help="Start local web UI and background indexing")
    serve.add_argument("--port", type=int, default=8765)
    commands.add_parser("index", help="Scan configured folders once, without starting the web UI")
    find = commands.add_parser("search", help="Search the index from the terminal")
    find.add_argument("query", nargs="*", help="Words to find; every word must match")
    find.add_argument("--kind", default="", help="Restrict to one file type, such as msg or pdf")
    find.add_argument(
        "--entity", default="", help="Documents linked to a ticket, person or address"
    )
    find.add_argument("--limit", type=int, default=10)
    find.add_argument("--expand", action="store_true", help="List every message in a conversation")
    find.add_argument("--json", action="store_true", help="Print results as JSON")
    find.add_argument(
        "--meaning", action="store_true", help="Combine full-text with semantic search"
    )
    commands.add_parser("migrate", help="Backfill dates, conversations and entities in the index")
    embed = commands.add_parser("embed", help="Build semantic vectors for the index")
    embed.add_argument(
        "--model",
        default=None,
        help="Embedding model name, or a local directory when downloads are blocked",
    )
    embed.add_argument(
        "--rebuild", action="store_true", help="Discard existing vectors and start again"
    )
    commands.add_parser("mcp", help="Serve the index to an MCP client over stdio")
    args = parser.parse_args()
    # Index content is private to this Linux user by default, including SQLite sidecars.
    os.umask(0o077)
    try:
        if args.command == "init":
            folders = [str(Path(p).expanduser().resolve()) for p in args.folder]
            args.config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with args.config.open("x", encoding="utf-8") as handle:
                handle.write(
                    "# Xtoo local settings. Keep this file out of Git.\n"
                    f"folders = {json.dumps(folders, ensure_ascii=False)}\n"
                    f"data_dir = {json.dumps(str(data_path()), ensure_ascii=False)}\n"
                    "interval_seconds = 300\nmax_file_mb = 25\n"
                )
            print(f"Created {args.config}. Run: xtoo serve")
            return
        settings = load_settings(args.config)
        if args.command == "search":
            from .store import Store

            store = Store(settings.data_dir)
            limit = max(1, min(args.limit, 100))
            if args.meaning:
                from .vectors import search as fused

                found = fused(
                    store,
                    " ".join(args.query),
                    kind=args.kind,
                    limit=limit,
                    collapse=not args.expand,
                )
            else:
                found = store.search(
                    " ".join(args.query),
                    kind=args.kind,
                    limit=limit,
                    entity=args.entity,
                    collapse=not args.expand,
                )
            if args.json:
                print(json.dumps(found, indent=2))
                return
            print(f"{found['total']} matching documents")
            for item in found["items"]:
                when = datetime.fromtimestamp(item["document_ns"] / 1e9, timezone.utc).date()
                thread = (
                    f" (+{item['thread_size'] - 1} in conversation)"
                    if item["thread_size"] > 1
                    else ""
                )
                print(f"\n{when}  [{item['kind']}]  {item['title']}{thread}\n  {item['path']}")
                if snippet := " ".join((item["snippet"] or "").split()):
                    print(f"  {snippet[:200]}")
            return
        if args.command == "migrate":
            from .migrate import enrich_documents
            from .store import Store

            print(
                f"Enriched {enrich_documents(Store(settings.data_dir), report=print):,} documents."
            )
            return
        if args.command == "embed":
            from .store import Store
            from .vectors import MODEL, build

            built = build(
                Store(settings.data_dir),
                report=print,
                model_name=args.model or MODEL,
                rebuild=args.rebuild,
            )
            print(f"Embedded {built['documents']:,} documents as {built['chunks']:,} chunks.")
            return
        if args.command == "mcp":
            from .mcp_server import serve

            serve(settings.data_dir)
            return
        if args.command == "index":
            from .indexer import Indexer
            from .store import Store

            result = Indexer(settings, Store(settings.data_dir)).scan()
            print(json.dumps(result, indent=2))
            if result["error_count"]:
                raise SystemExit(1)
        else:
            if not 1024 <= args.port <= 65535:
                parser.error("--port must be between 1024 and 65535")
            import uvicorn

            from .web import create_app

            print(f"Open http://localhost:{args.port} in your Windows browser.")
            uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)
    except FileExistsError:
        parser.exit(2, f"Configuration already exists: {args.config}. Edit it to change folders.\n")
    except (OSError, ValueError) as exc:
        parser.exit(
            2, f"{exc}\nUse 'xtoo init --folder /path/to/documents' to create configuration.\n"
        )


if __name__ == "__main__":
    main()
