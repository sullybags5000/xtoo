# Configuration

The default TOML file is `~/.config/xtoo/config.toml`. Set `XDG_CONFIG_HOME`
to change its parent. `xtoo init` creates it without overwriting an existing
file. See [config.example.toml](../config.example.toml).

| Key | Required | Default | Description | Example |
| --- | --- | --- | --- | --- |
| `folders` | Yes | — | Nonempty list of scan roots; nested roots are de-duplicated. | `['/mnt/c/Users/YOUR_WINDOWS_USER/Documents']` |
| `data_dir` | No | `$XDG_DATA_HOME/xtoo` or `~/.local/share/xtoo` | SQLite index directory. | `'/home/YOUR_LINUX_USER/.local/share/xtoo'` |
| `interval_seconds` | No | `300` | Background interval; minimum `10`. | `600` |
| `max_file_mb` | No | `25` | Files larger than this are skipped; minimum `1`. | `50` |
| `excluded_dirs` | No | `.git`, `.venv`, `venv`, `node_modules`, `AppData`, `$Recycle.Bin`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `.tox`, `site-packages`, `.terraform`, `.idea`, `.vs` | Directory names excluded during traversal. Setting the key replaces the whole default list. | `['.git', 'node_modules']` |
| `extra_text_extensions` | No | empty | Additional extensions read as plain text. Case and a leading dot are normalised. | `['.go', '.java']` |
| `attachment_chars` | No | `0` | Characters to read from inside each mail attachment. `0` indexes filenames only. | `4000` |
| `full_scan_hours` | No | `24` | How often the background scan examines every file rather than only changed folders. | `12` |
| `sync_command` | No | empty | Command `xtoo sync` runs before scanning, typically a Windows export. | `'powershell.exe -File C:\\export.ps1'` |
| `assistant_excludes` | No | empty | Path fragments an [assistant](assistant.md) may not read, even when asked. | `['/Personal/']` |

Fixed limits are one million extracted characters per document, 100 MB expanded
Office archive size, 25 MB per mail attachment, and 100,000 characters returned
in a preview. These are code constants, not TOML keys.

> [!WARNING]
> `sync_command` is run by a shell. It is your own configuration file, but treat
> it as you would a line in `~/.bashrc`, and keep the file private.

> [!IMPORTANT]
> `assistant_excludes` bounds what the [MCP server](assistant.md) can return. It
> does not restrict the browser or the terminal, which search everything indexed.

## Indexed file types

Extensions are defined in `xtoo/extract.py` and filter the traversal before any
file is opened. Everything else is ignored.

| Group | Extensions |
| --- | --- |
| Text | `.txt`, `.md`, `.rst`, `.csv`, `.tsv`, `.json`, `.xml`, `.yaml`, `.yml`, `.log` |
| Scripts and configuration-as-code | `.ps1`, `.psm1`, `.psd1`, `.bat`, `.cmd`, `.vbs`, `.sh`, `.bash`, `.zsh`, `.ksh`, `.fish`, `.awk`, `.py`, `.pyw`, `.pl`, `.pm`, `.rb`, `.lua`, `.php`, `.r`, `.js`, `.mjs`, `.cjs`, `.ts`, `.sql`, `.mk`, `.tf`, `.ini`, `.cfg`, `.conf`, `.toml`, `.properties` |
| Markup | `.html`, `.htm` |
| Parsed documents | `.pdf`, `.docx`, `.xlsx`, `.pptx` |
| Exported mail | `.msg`, `.eml` — see [Email](email.md) |

> [!IMPORTANT]
> Scripts are decoded and stored as text; Xtoo never runs them. Files that are
> not valid UTF-8 fall back to the Windows ANSI code page (`cp1252`), which
> covers most `.bat` and `.ps1` files saved by Windows editors.

Use `extra_text_extensions` for anything else that is plain text, such as
`['.go', '.java']`. Formats with a dedicated parser (`.pdf`, `.docx`, `.xlsx`,
`.pptx`, `.html`, `.htm`, `.msg`, `.eml`) are rejected there. Secret-bearing
files such as `.env`, `.pem`, and `.tfvars` are not indexed by default; add them
only if you accept their contents being stored in the index.

| Variable | Default | Use |
| --- | --- | --- |
| `XDG_CONFIG_HOME` | `~/.config` | Parent of `xtoo/config.toml`. |
| `XDG_DATA_HOME` | `~/.local/share` | Parent of the default index. |

There are no credential variables in this release. Run `xtoo index` to validate
both TOML and source access. Use `xtoo --config /absolute/path/settings.toml index`
for a custom file.
