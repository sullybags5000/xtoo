# Deployment and operations

There is no production deployment target in this repository. The supported
deployment is one user's WSL environment with a localhost browser session.

Run from `~/xtoo` in WSL to upgrade:

```bash
source .venv/bin/activate
git pull --ff-only
python -m pip install -e .
xtoo serve
```

Stop the current server with Ctrl+C before upgrading. Check status in the UI or
with `curl http://localhost:8765/api/status`; scan failures print in the
terminal. Xtoo does not configure a log file. The index and SQLite WAL files
are under `data_dir`.

For rollback, stop the server, check out a known repository commit, reinstall
the editable package, and restart. This changes application code only; it does
not restore source files. Do not delete the index as routine troubleshooting.
