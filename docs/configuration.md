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
| `excluded_dirs` | No | `.git`, `.venv`, `venv`, `node_modules`, `AppData`, `$Recycle.Bin`, `__pycache__` | Directory names excluded during traversal. | `['.git', 'node_modules']` |

Fixed limits are one million extracted characters per document, 100 MB expanded
Office archive size, and 100,000 characters returned in a preview. These are
code constants, not TOML keys.

| Variable | Default | Use |
| --- | --- | --- |
| `XDG_CONFIG_HOME` | `~/.config` | Parent of `xtoo/config.toml`. |
| `XDG_DATA_HOME` | `~/.local/share` | Parent of the default index. |

There are no credential variables in this release. Run `xtoo index` to validate
both TOML and source access. Use `xtoo --config /absolute/path/settings.toml index`
for a custom file.
