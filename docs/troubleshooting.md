# Troubleshooting

| Symptom | Likely cause | Verification | Resolution |
| --- | --- | --- | --- |
| Package requires a different Python | Python is older than 3.10 | `python --version` | Use Python 3.10+ and recreate `.venv`. |
| Folder unavailable | Wrong WSL path or unavailable drive | `ls -ld '/mnt/c/Users/.../Documents'` | Correct `folders`; ensure the drive is mounted. |
| OneDrive content missing | Files are online-only | Check Windows Explorer | Use **Always keep on this device**, then refresh. |
| File absent from results | Unsupported, excluded, oversized, or extraction error | Read scan status/issues | Use a supported format, adjust settings, or inspect the error. |
| Scanned PDF has no matches | PDF contains images | Try selecting text in the PDF | OCR is not implemented; use a text-based copy. |
| Address already in use | Another process owns the port | `ss -ltnp | rg ':8765'` | Stop it or run `xtoo serve --port 8766`. |
| Browser host error | Server stopped or disallowed host | Check terminal and URL | Use `http://localhost:8765`; do not use a machine hostname. |
| Configuration already exists | `init` will not overwrite | `ls -l ~/.config/xtoo/config.toml` | Edit settings deliberately, then restart. |
| Results look stale | Scan incomplete or source unavailable | `curl http://localhost:8765/api/status` | Correct source, wait, or refresh. |

Do not delete the database or source files as a first troubleshooting step.
