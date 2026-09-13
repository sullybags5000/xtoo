# Changelog

## Unreleased

- Added indexing for scripts and configuration-as-code, including `.ps1`,
  `.psm1`, `.bat`, `.cmd`, `.vbs`, `.sh`, `.py`, `.js`, `.sql`, `.tf`, and
  `.ini`. Files are read as text and never executed.
- Added the `extra_text_extensions` configuration key for further plain-text
  extensions.
- Added a `cp1252` decoding fallback for files that are not valid UTF-8.
- Added `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.tox`, `site-packages`,
  `.terraform`, `.idea`, and `.vs` to the default excluded directories.
- Added email indexing for exported `.msg` and `.eml` files, covering headers,
  attachment filenames, and plain-text or HTML bodies.
- Added `scripts/Export-OutlookMail.ps1`, an incremental Outlook export for
  Windows, and the [Email](email.md) guide.
- Added `scripts/mail_coverage.py`, which reports the message count and date
  range of each folder in an existing export so a top-up can start where it ends.
- Added `-Since` to the export script for topping up an existing export.
- Added `olefile` as a runtime dependency for `.msg` parsing.
- Added message dates, so mail sorts by when it was sent rather than when it was
  exported, with `xtoo migrate` to derive them for an existing index.
- Added conversation grouping for replies and forwards, and entity links for tracker
  references, correspondents and addresses across all file types.
- Added `xtoo search` for terminal queries and `xtoo mcp`, a read-only MCP server.
- Added optional semantic search (`xtoo embed`) using local static embeddings stored
  in the index through `sqlite-vec`, with `--model` for a chosen or local model and
  `--rebuild` to start again.
- Added `scripts/mail_estimate.py`, which projects indexing time and index growth
  from a sample before committing to a long run.
- Added `scripts/xtoo.sh` to start, stop, check and restart a background server,
  tracking it by process id so stopping Xtoo cannot stop anything else.
- Grouped search and vector building were rewritten for large indexes: grouping is
  about ten times faster, and embedding twenty thousand documents fell from over
  fifteen minutes to under a minute.

## 0.1.1 — 2026-09-11

- Added Python 3.10 compatibility, including the TOML parser backport.
- Added Python 3.10, 3.11, and 3.12 CI coverage.
- Expanded WSL installation guidance.

## 0.1.0

- Added local WSL browser search.
- Added SQLite FTS5 indexing for local text, HTML, PDF, DOCX, XLSX, and PPTX.
- Added incremental scanning, filters, previews, status reporting, and local API guards.
