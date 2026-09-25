# Testing

Run from the repository root with the development environment active:

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest
git diff --check
```

Fifty-two tests cover:

| Area | What is checked |
| --- | --- |
| Search | Ranking, literal treatment of query text, prefixes, phrases and excluded words, pagination |
| Scanning | Incremental updates, deletion, exclusions, size limits, unavailable folders, traversal and extraction failures, not rereading unreadable files, batched writes, literal path matching |
| Extraction | Office, PDF, HTML, scripts, ANSI-encoded text, `extra_text_extensions` |
| Mail | `.msg` and `.eml` headers, attachment names, bodies, unreadable messages, received dates |
| Derived fields | Message dates replacing file timestamps, conversation grouping, entity links across file types |
| Migration | Enriching an index created before those fields existed, including the schema upgrade |
| Semantic search | Building, resuming, re-embedding changed documents, dropping removed ones, changing model, chunking, grouping |
| Interfaces | HTTP API guards and endpoints, MCP tools and their registration, `assistant_excludes` |
| Terminal | Every `xtoo` command in-process: output, exit codes, filters, malformed input |

| Module | Area |
| --- | --- |
| `test_search.py` | Searching and scanning |
| `test_extract.py` | Formats and encodings |
| `test_mail.py` | Messages and attachments |
| `test_enrich.py` | Derived fields, migration, filters across both search paths |
| `test_vectors.py` | Semantic search |
| `test_interfaces.py` | HTTP API, browser contract, MCP tools, CLI setup |
| `test_cli.py` | Terminal commands |

Shared fixtures live in `conftest.py` and synthetic data in `helpers.py`.

Two fixtures deserve mention. `tests/outlook_msg.py` builds a real OLE compound
file byte by byte, so `.msg` parsing is exercised against the actual binary
format rather than a mock. The semantic tests pass a deterministic stand-in for
the embedding model, so they measure the pipeline without downloading anything.

Everything uses temporary synthetic data: no work data, no network, no external
service. Tests needing `sqlite-vec` skip themselves when it is absent, and it is
included in the `dev` extra so they normally run. The test that registers the
assistant tools needs the `mcp` extra and skips without it; neither the `dev`
extra nor CI installs it, so run `python -m pip install -e '.[dev,mcp]'` to
include it locally.

GitHub Actions runs `ruff check .` and `pytest` on Python 3.10, 3.11, and 3.12
for pushes and pull requests. The workflow is
[`.github/workflows/tests.yml`](../.github/workflows/tests.yml).
