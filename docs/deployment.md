# Running Xtoo

There is no production deployment target in this repository. The supported
deployment is one user's WSL environment with a localhost browser session.

Nothing starts Xtoo automatically. Closing the terminal that runs it in the
foreground stops it, and so do a Windows restart and `wsl --shutdown`. Choose one
of the two patterns below.

## For a quick look

```bash
cd ~/xtoo
source .venv/bin/activate
xtoo serve
```

Ctrl+C stops it. The terminal stays occupied, and closing it stops the server.

## To keep it running

```bash
nohup ~/xtoo/.venv/bin/xtoo serve >>~/xtoo.log 2>&1 &
```

This survives closing the terminal. It does not survive a Windows restart or
`wsl --shutdown`.

> [!IMPORTANT]
> Use the full path `~/xtoo/.venv/bin/xtoo` rather than bare `xtoo` in anything
> you automate. A plain `xtoo` depends on the virtual environment being active,
> and leaving a virtual environment can restore a `PATH` from before other tools
> were installed, so the command disappears.

## To start it whenever you open a terminal

Add to `~/.bashrc`:

```bash
# Start Xtoo unless it is already running
pgrep -f "xtoo serve" >/dev/null || (nohup ~/xtoo/.venv/bin/xtoo serve >>~/xtoo.log 2>&1 &)
```

The guard means opening several terminals does not start several servers. This
also covers a Windows restart, since the first terminal you open brings it back.

For a server that starts without any terminal, a Windows Task Scheduler task at
logon can run `wsl.exe` against the distribution directly; find the distribution
name with `wsl -l -q` first. That path is not verified here.

## Checking and stopping

```bash
curl -s http://localhost:8765/api/status        # running, counts, folders, errors
pgrep -fa "xtoo serve"                          # process, or nothing
tail -20 ~/xtoo.log                             # startup errors and tracebacks
pkill -f "xtoo serve"                           # stop it
```

> [!WARNING]
> `pkill -f` matches any process whose whole command line contains the text,
> including a script that merely mentions it. Typed in a terminal it is safe,
> because your shell's command line is just `bash`. Inside a script, kill the
> process by the id from `pgrep` instead.

The UI reports scan progress and folder errors; `~/xtoo.log` holds anything that
happened before the UI could. Xtoo writes no other log.

## Upgrading

```bash
cd ~/xtoo
pkill -f "xtoo serve"
git pull --ff-only
source .venv/bin/activate
python -m pip install -e .
nohup ~/xtoo/.venv/bin/xtoo serve >>~/xtoo.log 2>&1 &
```

Run `python -m pip install -e '.[mcp,vectors]'` instead if you use the
[assistant](assistant.md) or [semantic search](semantic.md) extras. Upgrading
never rebuilds the index; schema changes are applied when the index is opened.

For rollback, stop the server, check out a known commit, reinstall the editable
package, and restart. That changes application code only; it does not restore
source files. Do not delete the index as routine troubleshooting.

## Keeping the index current

| Step | How | Automatic? |
| --- | --- | --- |
| New and changed files | Background scan on `interval_seconds`, or **Refresh index** | Yes |
| Dates, conversations, entity links | Derived as each document is indexed | Yes |
| New mail from Outlook | Re-run the [export](email.md), for example with `-Days 7` | No |
| Semantic vectors | `~/xtoo/.venv/bin/xtoo embed` | No |

Only the last two need you. New mail is keyword-searchable as soon as it is
scanned, but invisible to **Meaning** until `xtoo embed` runs again; it is
incremental, so it only handles what is new.

`xtoo migrate` is a one-off for an index built before dates and links existed. It
never needs running again.
