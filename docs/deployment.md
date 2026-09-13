# Running Xtoo

There is no production deployment target in this repository. The supported
deployment is one user's WSL environment with a localhost browser session.

Nothing starts Xtoo automatically. Closing the terminal that runs it in the
foreground stops it, and so do a Windows restart and `wsl --shutdown`.

## The short version

```bash
~/xtoo/scripts/xtoo.sh start      # or status, stop, restart
```

That starts Xtoo in the background on `http://localhost:8765`, leaves an already
running server alone, and writes to `~/xtoo.log`. It records the process id in
`~/.xtoo.pid` rather than matching command lines, so stopping Xtoo cannot stop
anything else. `status` reports what the index holds:

```text
Running (pid 4121) on http://localhost:8765
  422,220 documents: 421,004 msg, 812 txt, 210 pdf, 94 py
  last scan 2026-09-13T09:14:02+00:00
  semantic search ready
```

Put this line in `~/.bashrc` to have it running whenever you open a terminal:

```bash
~/xtoo/scripts/xtoo.sh start >/dev/null
```

`XTOO_PORT`, `XTOO_LOG`, `XTOO_PID` and `XTOO_CONFIG` override the defaults. The
rest of this page is what the script does, for when you want to do it by hand.

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
~/xtoo/scripts/xtoo.sh start >/dev/null
```

Opening several terminals does not start several servers, and this also covers a
Windows restart, since the first terminal you open brings Xtoo back.

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
git pull --ff-only
source .venv/bin/activate
python -m pip install -e .
~/xtoo/scripts/xtoo.sh restart
```

Run `python -m pip install -e '.[mcp,vectors]'` instead if you use the
[assistant](assistant.md) or [semantic search](semantic.md) extras. Upgrading
never rebuilds the index; schema changes are applied when the index is opened.

For rollback, stop the server, check out a known commit, reinstall the editable
package, and restart. That changes application code only; it does not restore
source files. Do not delete the index as routine troubleshooting.

## Keeping the index current

One command does all of it:

```bash
~/xtoo/.venv/bin/xtoo sync
```

It runs `sync_command` from your configuration — typically the Windows export —
then scans, then embeds whatever is new if the index already has vectors. Put it
on a schedule, or run it when you want to be current.

| Step | How | Covered by `sync` |
| --- | --- | --- |
| New mail from Outlook | `sync_command`, for example the export with `-Days 7` | Yes |
| New and changed files | Background scan, or **Refresh index** | Yes |
| Dates, conversations, senders, entity links | Derived as each document is indexed | Always |
| Semantic vectors | `xtoo embed` | Yes, if vectors exist |

Scanning comes in two depths. A quick scan trusts a folder whose timestamp has
not moved, which finds new and deleted files in seconds on a large export; a full
scan examines every file and is the only one that notices a file edited in place.
The background indexer runs quick scans and a full scan every `full_scan_hours`,
so `interval_seconds` can be minutes rather than a day.

`xtoo migrate` is a one-off for an index built before dates and links existed. It
never needs running again.
