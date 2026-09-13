# Troubleshooting

| Symptom | Likely cause | Verification | Resolution |
| --- | --- | --- | --- |
| Package requires a different Python | Python is older than 3.10 | `python --version` | Use Python 3.10+ and recreate `.venv`. |
| Server gone after closing the terminal | It was started in the foreground | `pgrep -fa "xtoo serve"` | Start it with `nohup ~/xtoo/.venv/bin/xtoo serve >>~/xtoo.log 2>&1 &`. See [Running Xtoo](deployment.md). |
| Nothing running after a Windows restart | Nothing starts Xtoo automatically | `curl -s localhost:8765/api/status` | Start it again, or add the guarded line to `~/.bashrc` in [Running Xtoo](deployment.md). |
| `xtoo: command not found` | The virtual environment is not active, or leaving it restored an older `PATH` | `which -a xtoo; echo "$PATH"` | Use the full path `~/xtoo/.venv/bin/xtoo`, or `source ~/xtoo/.venv/bin/activate`. |
| `CERTIFICATE_VERIFY_FAILED` from `xtoo embed` | A managed network inspects TLS with its own root certificate | `python -c "import huggingface_hub as h; h.hf_hub_download('minishlab/potion-base-8M','config.json')"` | Set `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` to your organisation's root certificate, or use `xtoo embed --model /path/to/local/model`. See [Semantic search](semantic.md). |
| Meaning toggle missing from the search bar | Vectors are not built, or the `vectors` extra is not installed | `curl -s localhost:8765/api/status \| grep semantic` | `pip install -e '.[vectors]'` then `xtoo embed`. |
| Mail sorted by export date, no links shown | An index built before enrichment | `xtoo search --limit 3` and check the dates | Run `xtoo migrate` once. |
| Folder unavailable | Wrong WSL path or unavailable drive | `ls -ld '/mnt/c/Users/.../Documents'` | Correct `folders`; ensure the drive is mounted. |
| OneDrive content missing | Files are online-only | Check Windows Explorer | Use **Always keep on this device**, then refresh. |
| File absent from results | Unsupported, excluded, oversized, or extraction error | Read scan status/issues | Use a supported format, adjust settings, or inspect the error. |
| Scanned PDF has no matches | PDF contains images | Try selecting text in the PDF | OCR is not implemented; use a text-based copy. |
| Address already in use | Another process owns the port | `ss -ltnp | rg ':8765'` | Stop it or run `xtoo serve --port 8766`. |
| Browser host error | Server stopped or disallowed host | Check terminal and URL | Use `http://localhost:8765`; do not use a machine hostname. |
| Configuration already exists | `init` will not overwrite | `ls -l ~/.config/xtoo/config.toml` | Edit settings deliberately, then restart. |
| Results look stale | Scan incomplete or source unavailable | `curl http://localhost:8765/api/status` | Correct source, wait, or refresh. |

Do not delete the database or source files as a first troubleshooting step.
