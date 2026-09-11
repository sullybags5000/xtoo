# Xtoo

Xtoo is a local Python search application for indexed documents in WSL, with a
browser UI, full-text search, filters, and text previews.

> [!NOTE]
> The current release indexes local Windows folders only. Mail is indexed from
> `.msg` and `.eml` files exported to one of those folders; see
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
| Local development | [Development](docs/development.md) |
| Test suite and checks | [Testing](docs/testing.md) |
| Local deployment and upgrades | [Deployment](docs/deployment.md) |
| Common failures | [Troubleshooting](docs/troubleshooting.md) |
| Data protection and localhost boundary | [Security](docs/security.md) |
| Contributions | [Contributing](docs/contributing.md) |
| Release history | [Changelog](docs/changelog.md) |

## Status and boundaries

This is a single-user local application, not an enterprise deployment. The
index contains extracted text and paths under `~/.local/share/xtoo` by default;
it is not encrypted by Xtoo. Do not put work documents, credentials, or the
index in Git. The repository has no declared open-source license.

Last verified against commit `ce78ccc`.
