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

`xtoo init` exits `2` for an existing configuration or invalid input. Do not
expose the server through a tunnel or shared proxy.

## HTTP API

The local API has no authentication and is intended for the bundled UI.

| Endpoint | Inputs | Response |
| --- | --- | --- |
| `GET /api/search` | `q`, `kind`, `offset`, `limit` (`limit` 1–100) | Results and pagination fields |
| `GET /api/documents/{id}` | Numeric ID | Metadata and up to 100,000 characters |
| `GET /api/status` | None | Scan state, counts, folders, errors |
| `POST /api/index` | `X-Xtoo-Request: 1`; same-origin `Origin` if supplied | `202` scan request |

```bash
curl 'http://localhost:8765/api/search?q=budget&limit=10'
curl http://localhost:8765/api/status
curl -X POST -H 'X-Xtoo-Request: 1' http://localhost:8765/api/index
```

Invalid document IDs return `404`; invalid query parameters return `422`; a
refresh without the header or with a different origin returns `403`.
