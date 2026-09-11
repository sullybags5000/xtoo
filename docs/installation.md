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

Package downloads use the configured Python package index. If work networking
blocks downloads, use the organization-approved mirror or installation route.

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
overwrite an existing configuration. Stop the server with Ctrl+C.

Validate from the repository root with the environment active:

```bash
xtoo index
pytest
```
