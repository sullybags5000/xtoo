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

## 0.1.1 — 2026-09-11

- Added Python 3.10 compatibility, including the TOML parser backport.
- Added Python 3.10, 3.11, and 3.12 CI coverage.
- Expanded WSL installation guidance.

## 0.1.0

- Added local WSL browser search.
- Added SQLite FTS5 indexing for local text, HTML, PDF, DOCX, XLSX, and PPTX.
- Added incremental scanning, filters, previews, status reporting, and local API guards.
