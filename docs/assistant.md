# Assistant access

Xtoo can serve the index to an MCP client such as Claude Code, so an assistant can
search your own documents, scripts and mail instead of guessing. The server is
read-only: it searches and reads, and never indexes, writes or reaches the network.

> [!IMPORTANT]
> Whatever an assistant retrieves leaves this machine with the conversation, exactly
> as if you had pasted the text yourself. Mail and internal documents are the most
> sensitive content in the index. Decide whether that is acceptable before connecting
> a client, and see [Security](security.md).

## Install

```bash
cd ~/xtoo
source .venv/bin/activate
python -m pip install -e '.[mcp]'
```

The server is started by the client, not by you, and it reads the same
configuration file as the rest of Xtoo. It opens the index directly, so `xtoo serve`
does not have to be running.

## Connect Claude Code

```bash
claude mcp add xtoo -- /home/YOUR_LINUX_USER/xtoo/.venv/bin/xtoo mcp
```

Use the absolute path to the virtual environment's `xtoo`, because the client starts
the command without your shell's environment. Add `--scope user` to make it available
in every project rather than the current one. Confirm with `claude mcp list`, or with
`/mcp` inside a session.

To check the server by hand before connecting a client:

```bash
xtoo mcp < /dev/null
```

It should exit silently. An `ImportError` means the `mcp` extra is not installed.

## Tools

| Tool | Purpose |
| --- | --- |
| `search_documents` | Full-text search, optionally restricted to one file type. Returns id, title, date, path and an excerpt. Uses semantic search as well when vectors are built. |
| `read_document` | The text of one result by id, up to a character limit. |
| `find_by_entity` | Every document linked to a ticket reference, a person or an address, across mail, scripts and documents together. |
| `list_entities` | Identifiers beginning with some text, with how many documents mention each, for finding the exact spelling before `find_by_entity`. |

The useful shape of a question is "what did we decide about X", "what has this ticket
touched", or "what did this person send me about Y". The assistant searches, reads the
promising results, and answers from them.

## Terminal search

The same queries work without an assistant:

```bash
xtoo search cluster upgrade
xtoo search --entity PROJ-4821
xtoo search --kind msg --limit 20 budget
xtoo search --json --limit 5 migration | jq '.items[].path'
```

Conversations are grouped by default; `--expand` lists every message. `--meaning`
adds semantic search, which needs [vectors](semantic.md).
