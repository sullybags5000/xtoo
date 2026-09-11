# Development

Run from the repository root with Python 3.10–3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

The package is editable. Browser assets are plain files under `xtoo/static`; no
frontend build step is defined. Use `xtoo serve` while developing. Keep work
documents, configuration, indexes, credentials, and generated files out of the
checkout. Add tests under `tests/` using temporary synthetic data only.

See [Architecture](architecture.md) for module responsibilities.
