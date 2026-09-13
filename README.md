# Xtoo

Xtoo is a local search application for your own documents, scripts and exported
mail. It runs entirely in WSL as one process over one SQLite file, with a browser
interface, a terminal command, and an optional assistant interface.

```bash
xtoo init --folder /mnt/c/Users/YOUR_WINDOWS_USER/Documents
xtoo serve                                    # http://localhost:8765
~/xtoo/scripts/xtoo.sh start                  # or leave it running in the background
```

Nothing starts it automatically; see [Running Xtoo](docs/deployment.md) for
keeping it up after a terminal closes or Windows restarts.

## What it indexes

| Group | Formats |
| --- | --- |
| Text and markup | `.txt`, `.md`, `.rst`, `.csv`, `.tsv`, `.json`, `.xml`, `.yaml`, `.log`, `.html` |
| Documents | `.pdf`, `.docx`, `.xlsx`, `.pptx` |
| Scripts and configuration-as-code | `.ps1`, `.bat`, `.cmd`, `.vbs`, `.sh`, `.py`, `.js`, `.sql`, `.tf`, `.ini` and more |
| Exported mail | `.msg`, `.eml` — headers, attachment names and body |

Scripts and mail are read as text: nothing is executed, and no attachment is
opened. Add further plain-text extensions with `extra_text_extensions`.

## What it does

- **One index for everything.** A hostname or an error string finds the script
  that sets it, the document that describes it and the mail thread that argued
  about it, in one result list.
- **Real message dates.** Exported mail is dated by when it was sent, not by when
  the export tool wrote the file, so results sort by when things happened.
- **Conversations.** Replies and forwards collapse to one row with a message
  count, which matters when a tracker sends an update per comment.
- **Entity links.** Documents are linked by the identifiers they mention —
  tracker references, correspondents, addresses — so one click assembles
  everything touching a ticket or a person, across file types.
- **Semantic search**, optional. A local static embedding model finds documents
  that mean the same thing in different words, combined with full-text ranking
  rather than replacing it. See [Semantic search](docs/semantic.md).
- **Assistant access**, optional. A read-only MCP server lets a client such as
  Claude Code search and read the index. See [Assistant](docs/assistant.md).
- **Terminal search.** `xtoo search WORDS`, with `--kind`, `--entity`,
  `--meaning` and `--json`.

Scanning is incremental: unchanged files are skipped, deleted files are removed,
and an unreachable folder keeps its cached results rather than emptying them.

> [!NOTE]
> Xtoo indexes local folders only. Mail is indexed from `.msg` and `.eml` files
> exported into one of them, for which a Windows export script is included; see
> [Email](docs/email.md). Live Outlook/Microsoft 365 and Confluence connectors
> are planned and are not implemented.

## Documentation

| Topic | Guide |
| --- | --- |
| System design and data flow | [Architecture](docs/architecture.md) |
| WSL installation | [Installation](docs/installation.md) |
| TOML and storage reference | [Configuration](docs/configuration.md) |
| Operating the UI and CLI | [Usage](docs/usage.md) |
| Indexing Outlook and other mail | [Email](docs/email.md) |
| Dates, conversations and links | [Usage](docs/usage.md#conversations-and-links) |
| Assistant and terminal access | [Assistant](docs/assistant.md) |
| Meaning-aware search | [Semantic search](docs/semantic.md) |
| Local development | [Development](docs/development.md) |
| Test suite and checks | [Testing](docs/testing.md) |
| Running it, restarting, staying current | [Running Xtoo](docs/deployment.md) |
| Common failures | [Troubleshooting](docs/troubleshooting.md) |
| Data protection and localhost boundary | [Security](docs/security.md) |
| Contributions | [Contributing](docs/contributing.md) |
| Release history | [Changelog](docs/changelog.md) |

## Status and boundaries

This is a single-user local application, not an enterprise deployment. It binds
to `127.0.0.1` and has no authentication.

The index holds extracted text and paths under `~/.local/share/xtoo` by default
and is not encrypted by Xtoo. Indexed mail and scripts routinely contain
hostnames, connection strings and credentials, so treat the index as work data.
Nothing is sent to a service: semantic search runs its model locally, and the
only exception is the optional assistant interface, where whatever an assistant
retrieves leaves the machine with the conversation.

Do not put work documents, credentials, or the index in Git. The repository has
no declared open-source license.

Last verified against commit `5576572`.
