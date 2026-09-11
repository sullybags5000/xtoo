# Testing

Run from the repository root with the development environment active:

```bash
python -m pip install -e '.[dev]'
ruff check .
pytest
git diff --check
```

The tests cover SQLite search, literal queries, incremental updates/deletion,
exclusions and large files, unavailable folders, extraction failures,
configuration validation, Office/PDF/HTML extraction, API guards, background
scan lifecycle, and CLI setup. They use temporary files and no work data or
external services.

GitHub Actions runs `ruff check .` and `pytest` on Python 3.10, 3.11, and 3.12
for pushes and pull requests. The workflow is
[`.github/workflows/tests.yml`](../.github/workflows/tests.yml).
