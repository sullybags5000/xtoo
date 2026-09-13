# Development

Run from the repository root with Python 3.10–3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Add `'.[dev,mcp,vectors]'` instead to work on the [assistant](assistant.md) or
[semantic search](semantic.md) features; both are dormant without their extra.

The package is editable. Browser assets are plain files under `xtoo/static`; no
frontend build step is defined. `~/xtoo/scripts/xtoo.sh restart` reloads a
background server after a change, or run `xtoo serve` in the foreground.

Helpers under `scripts/` are operational rather than part of the package:

| Script | Purpose |
| --- | --- |
| `xtoo.sh` | Start, stop, check and restart a background server |
| `Export-OutlookMail.ps1` | Export Outlook mail on Windows for indexing |
| `mail_coverage.py` | Report what an existing mail export already covers |
| `mail_estimate.py` | Project indexing time and index growth from a sample |

Keep work documents, configuration, indexes, credentials, and generated files
out of the checkout. Add tests under `tests/` using temporary synthetic data
only, and invent every name, path and identifier that appears anywhere in the
repository — see [AGENTS.md](../AGENTS.md).

See [Architecture](architecture.md) for module responsibilities.
