# Usage

Start from any WSL directory with the virtual environment active:

```bash
xtoo serve
```

Open `http://localhost:8765`. The first scan starts automatically. Every search
word must match; partial words match the start of indexed words. Filter by file
extension, select a result for a text preview, or use **Refresh index** for an
immediate scan. Documents and scripts share one index, so the **All file types**
filter can be narrowed to `PS1`, `SH`, `PY`, or any other indexed extension.
Press `/` to focus search. The status line reports progress, counts, skipped
files, and indexing issues.

| Command | Behavior |
| --- | --- |
| `xtoo init --folder PATH` | Creates the configuration; repeat `--folder` for more roots. |
| `xtoo index` | One scan and JSON status; exits `1` if scan errors occur. |
| `xtoo serve` | Local UI on `127.0.0.1:8765` until Ctrl+C. |
| `xtoo serve --port 8766` | Uses a port from 1024 through 65535. |
| `xtoo --config PATH serve` | Uses an explicit TOML file. |
| `xtoo search WORDS` | Searches from the terminal; `--kind`, `--entity`, `--limit`, `--expand`, `--meaning`, `--json`. |
| `xtoo migrate` | Derives dates, conversations and entity links for documents indexed earlier. |
| `xtoo embed` | Builds [semantic](semantic.md) vectors; `--model`, `--rebuild`. Needs the `vectors` extra. |
| `xtoo mcp` | Serves the index to an [MCP client](assistant.md) over stdio. |

`xtoo init` exits `2` for an existing configuration or invalid input. Do not
expose the server through a tunnel or shared proxy.

## Conversations and links

Indexed mail carries the date it was sent, not the date it was exported, so results
sort by when things actually happened. Replies and forwards of one subject share a
conversation, and **Group replies** in the search bar shows one row per conversation
with the number of messages in it; clear the tick to see every reply.

Grouping reads the best 2,000 matches rather than the whole index, so on a large
library the conversation count is capped at that while the document count beside it
stays exact. The alternative would be a grouping pass over every match on each
keystroke.

Documents are also linked by the identifiers they mention — tracker references such as
`PROJ-4821`, correspondents as written in mail headers, and email addresses. Selecting
a result lists its links, and choosing one shows every document that mentions it,
across mail, scripts and documents alike. **Clear link** returns to the whole library.

An index built by an earlier version has none of this until it is derived, which reads
the text already stored rather than reopening any file:

```bash
xtoo migrate
```

It reports progress, can be interrupted, and skips what it has already done. Run it
once after upgrading; new documents are enriched as they are indexed.

## HTTP API

The local API has no authentication and is intended for the bundled UI.

| Endpoint | Inputs | Response |
| --- | --- | --- |
| `GET /api/search` | `q`, `kind`, `offset`, `limit` (`limit` 1–100), `entity`, `collapse`, `meaning` | Results and pagination fields |
| `GET /api/entities` | `prefix` (empty lists the most mentioned) | Identifiers with document counts |
| `GET /api/documents/{id}` | Numeric ID | Metadata and up to 100,000 characters |
| `GET /api/status` | None | Scan state, counts, folders, errors, whether semantic search is ready |
| `POST /api/index` | `X-Xtoo-Request: 1`; same-origin `Origin` if supplied | `202` scan request |

```bash
curl 'http://localhost:8765/api/search?q=budget&limit=10'
curl 'http://localhost:8765/api/search?entity=PROJ-4821'
curl 'http://localhost:8765/api/entities?prefix=VX'
curl http://localhost:8765/api/status
curl -X POST -H 'X-Xtoo-Request: 1' http://localhost:8765/api/index
```

Invalid document IDs return `404`; invalid query parameters return `422`; a
refresh without the header or with a different origin returns `403`.
