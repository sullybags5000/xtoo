# Installation

Xtoo supports Python 3.10, 3.11, and 3.12 under WSL. Keep the checkout,
virtual environment, and index in the WSL Linux filesystem; source documents
can be exposed through `/mnt/c`.

Run in a WSL terminal:

```bash
sudo apt update
sudo apt install python3 python3-venv git
python3 --version
git clone git@github.com:sullybags5000/xtoo.git
cd xtoo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For the optional features, install the extras instead of the last line above:

```bash
python -m pip install -e '.[mcp,vectors]'
```

`mcp` adds [assistant access](assistant.md) and `vectors` adds
[semantic search](semantic.md). Neither changes behaviour until enabled, and the
core install needs neither.

Package downloads use the configured Python package index. If work networking
blocks downloads, use the organization-approved mirror or installation route.

> [!NOTE]
> A network that inspects TLS presents its own certificate, and downloads then
> fail with a certificate error even though the site is reachable. Give each tool
> your organisation's root certificate through its own configuration, which is
> scoped to that tool:
>
> ```bash
> pip config set global.cert /absolute/path/to/root.pem
> npm config set cafile /absolute/path/to/root.pem
> ```
>
> For a one-off command that needs it, set the variable for that command alone:
> `SSL_CERT_FILE=/absolute/path/to/root.pem xtoo embed`. Use absolute paths; a
> relative one fails with `invalid path`.

> [!WARNING]
> Do not export `SSL_CERT_FILE` or `REQUESTS_CA_BUNDLE` from a shell profile.
> They *replace* the trust store rather than adding to it, so every program that
> reads them can then verify only the sites your proxy intercepts, and fails
> against everything else. The symptom is unrelated tools suddenly receiving an
> HTML error page from the proxy instead of the service they asked for.

Configure paths visible from WSL. Replace the placeholders; quote paths with
spaces:

```bash
ls /mnt/c/Users
xtoo init \
  --folder '/mnt/c/Users/YOUR_WINDOWS_USER/Documents' \
  --folder '/mnt/c/Users/YOUR_WINDOWS_USER/OneDrive - YOUR COMPANY'
xtoo serve
```

Open `http://localhost:8765` in Windows. For OneDrive, mark selected folders
**Always keep on this device** and wait for download. `xtoo init` refuses to
overwrite an existing configuration. Stop the server with Ctrl+C, or use
`scripts/xtoo.sh` to run it in the background — see [Running Xtoo](deployment.md).

Validate from the repository root with the environment active:

```bash
xtoo index
pytest
```
