# Contributing

Keep changes within the local-first scope unless the repository owner expands
it. Explain the user-visible or operational reason for each change.

Run from the repository root before opening a pull request:

```bash
source .venv/bin/activate
python -m pip install -e '.[dev]'
ruff check .
pytest
git diff --check
```

Do not commit documents, indexes, credentials, generated caches, screenshots,
or personal configuration. Update relevant documentation when behavior,
formats, CLI arguments, configuration, security boundaries, or operations
change. Pull requests should state the change, validation performed, and manual
checks still needed. The repository has no declared license or code-of-conduct
policy; confirm terms with the owner before distributing changes.
