# Xtoo

A local desktop search application built in Python, with a browser interface for
WSL. Search selected Windows folders, filter by file type, and preview extracted
text. Your documents and search index stay on your laptop; no AI service is used.

**Current version:** local document search. Outlook/Microsoft 365 and Confluence
connectors are planned, not implemented. This is an initial single-user application,
not a complete replacement for X1 or an enterprise deployment.

## Run on your work laptop

Use Python 3.11 or newer inside WSL. Keep the checkout and virtual environment
under your Linux home directory, even when documents live on the Windows drive.
On Ubuntu 24.04, Python 3.12 is available from the standard packages:

```bash
sudo apt update
sudo apt install python3 python3-venv git
python3 --version
git clone git@github.com:sullybags5000/xtoo.git
cd xtoo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Use an organization-approved Python 3.11+ installation if your WSL distribution
ships an older version. Cloning this private repository requires GitHub access;
HTTPS is also available: `https://github.com/sullybags5000/xtoo.git`.

Choose your source folders. Replace `YOUR_WINDOWS_USER` and the company folder
name with the names shown under `/mnt/c/Users`:

```bash
xtoo init \
  --folder '/mnt/c/Users/YOUR_WINDOWS_USER/Documents' \
  --folder '/mnt/c/Users/YOUR_WINDOWS_USER/OneDrive - YOUR COMPANY'
xtoo serve
```

Open **http://localhost:8765** in your Windows browser. The first scan starts
automatically. Leave the terminal running; Ctrl+C stops the application.
WSL localhost forwarding must be enabled for the Windows browser to reach it.
The server binds to `127.0.0.1`; do not expose it through a tunnel or shared proxy.

The UI shows scan progress, file counts, and errors. Type words to search; all
words must match, and partial words match the start of indexed words. Results
favor matches in the filename. Select a result to preview its extracted text.
Use **Copy path** to copy its WSL path. `/` focuses the search box.

### Folder and OneDrive setup

- Start with a small Documents folder, then add sources as needed.
- A quoted path supports spaces, including work OneDrive folder names.
- This connector reads files already accessible through WSL. For OneDrive,
  select **Always keep on this device** in Windows and wait for the download
  to finish. Online-only placeholder files may fail to read; listing a filename
  does not guarantee its contents are available locally.
- Index your selected document folders, not the entire `C:` drive or Windows
  profile. Protected Windows system files and `AppData` are not needed.
- Folder aliases/junctions may overlap. Configure the actual folder once where
  possible. Linux symbolic links are skipped, and nested configured roots are
  deduplicated. WSL's handling of Windows reparse points can vary.

## Configuration and storage

`xtoo init` creates `~/.config/xtoo/config.toml`, never overwriting an existing
file. Edit it and restart the application to change sources or limits.
See [config.example.toml](config.example.toml). XDG configuration/data directory
environment variables are supported.

The index lives at `~/.local/share/xtoo/index.sqlite3`. Keep it in WSL's Linux
filesystem for performance. It contains **copies of extracted document text**,
filenames, and paths, so treat it as work data. CLI-created files are private to
your Linux user by default; the database is not encrypted by the application.
Use your organization's approved device and storage protections.

Only source code belongs in this repository. Local configuration, environments,
databases, and a `data/` directory are ignored by Git. Do not put work documents,
tokens, or credentials in the checkout, even if the repository is private.

```bash
xtoo index                            # One scan, no web server; JSON status output
xtoo serve --port 8766                 # Alternative local port
xtoo --config /path/settings.toml serve
```

The default scan interval is five minutes. The scanner checks file modification
time and size, re-extracts changed files, and removes deleted files after a
successful folder traversal. If a folder is unavailable or cannot be traversed,
cached results are retained and an issue is shown; these results may be stale.
A file whose extraction fails loses any previous indexed text and is retried
next scan. Removing a source from configuration removes its cached documents
on the next start/scan. These are index changes only; source files are never
modified. SQLite deletion is not a guarantee of forensic erasure from disk or backups.

## Supported files and current limits

| Type | Extracted content |
| --- | --- |
| TXT, Markdown, RST, CSV, TSV, JSON, XML, YAML, logs | Text, decoded as UTF-8 or BOM-marked UTF-16 |
| HTML | Text, with scripts and styles omitted |
| PDF | Embedded text; no OCR for scanned pages |
| DOCX | Paragraphs and tables |
| XLSX | Worksheet names and cell values; formulas use cached values |
| PPTX | Slide text and tables |

This version provides text previews, not native document rendering. It does not
read Outlook OST/PST caches, legacy DOC/XLS/PPT files, password-protected
documents, handwriting, or images. Some Office content such as comments,
headers, and embedded objects is not extracted. Empty/scanned documents remain
searchable by filename.

Files above 25 MB are skipped by default. Extracted text is limited to the first
1,000,000 characters per document; previews show at most 100,000 characters.
Office archives over 100 MB expanded size are rejected. These limits do not
constitute a parser sandbox or enforce a hard execution-time/memory limit.
The first scan of a large collection, especially across `/mnt/c`, can take time;
there are no enterprise-scale performance claims for this initial version.

The application has no login and is intended for a single user's localhost
session. It restricts hostnames, avoids cross-origin API access, escapes preview
content, and requires a custom header for manual scan requests. These controls
do not isolate it from other processes/users already able to reach localhost.
Use of an internally maintained application and its data access remains subject
to your organization's normal approval process.

## Next connectors

1. **Outlook / Microsoft 365:** Microsoft Graph, delegated sign-in with MFA and
   `Mail.Read`, approved Entra app registration, incremental mailbox sync, and
   attachment extraction. No mail sending or modification is needed. Tenant
   policy determines whether administrator consent is required.
2. **Confluence:** an approved API authentication method, an explicit space/page
   allowlist, page updates and deletions, and links back to original pages.
3. Richer filters, document-opening integration, and optional semantic search.

Source access and permissions need to be settled before implementing the cloud
connectors. No Microsoft or Confluence credentials are needed for this release.

## Update and develop

Stop the running server before updating:

```bash
cd ~/xtoo
git pull --ff-only
source .venv/bin/activate
python -m pip install -e .
xtoo serve
```

For development:

```bash
python -m pip install -e '.[dev]'
pytest
ruff check .
```

The test suite uses temporary synthetic documents; it does not need work data
or credentials. Python dependency ranges are bounded in `pyproject.toml`; a
fully locked organizational deployment environment is a future packaging step.
No redistribution license is granted by this initial private repository.
