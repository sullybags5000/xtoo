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

The server exposes four tools. All parameters are optional unless noted.

### search_documents

Full-text search across the index. Returns matching documents with id, title, date,
path, kind, and an excerpt.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `query` | string | required | Words to search for. Every word must match. Use `"quoted phrase"` for exact phrases or `-word` to exclude. |
| `kind` | string | empty | Restrict to one file type, such as `msg`, `pdf`, `py`. |
| `limit` | integer | 10 | Maximum results to return, capped at 50. |
| `collapse` | boolean | true | Group email conversations; false lists every message. |
| `since` | string | empty | `YYYY-MM-DD` lower bound on document date. |
| `until` | string | empty | `YYYY-MM-DD` upper bound on document date. |
| `people` | boolean | false | Exclude mail from automated senders. |

Uses semantic search automatically when vectors are built, except for exact
identifier queries where it would add nothing.

### read_document

Read the full text of one document found by `search_documents`.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `document_id` | integer | required | The id from a `search_documents` result. |
| `max_characters` | integer | 4000 | Maximum characters to return, capped at 50,000. |

Returns title, kind, date, path, entities, content, and whether the content was
truncated. Email arrives as a Subject/From/To/Date header block followed by the body.

### find_by_entity

Find every document linked to one identifier across mail, scripts and documents.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | required | Ticket reference, person name, or email address. |
| `limit` | integer | 20 | Maximum results to return, capped at 50. |

This is the fastest way to assemble the history of a ticket or correspondent. The
name must match exactly as it appears in the index; use `list_entities` to find the
correct spelling.

### list_entities

List identifiers in the index that begin with a prefix, with document counts.

| Parameter | Type | Default | Description |
| --- | --- | --- | --- |
| `prefix` | string | required | Text that entity names must start with. |

Returns entries in the format `kind:name (count)`, such as `ticket:PROJ-4821 (4)` or
`person:Lee, Sam (12)`. Use this before `find_by_entity` to confirm the exact spelling.

## Keeping folders private

```toml
assistant_excludes = ["/Personal/", "/Private/"]
```

Any indexed path containing one of those fragments is invisible to every tool
here, even if the assistant is asked for it directly. The browser and the
terminal are unaffected: this bounds what leaves the machine, not what you can
find yourself.

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

## Troubleshooting

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `ImportError: No module named 'mcp'` | The `mcp` extra is not installed | Run `python -m pip install -e '.[mcp]'` |
| Client cannot start the server | Path to `xtoo` is relative or uses shell expansion | Use the absolute path to the virtual environment's `xtoo` |
| Server exits with an error | Configuration file is missing or invalid | Run `xtoo index` to validate configuration |
| Tools return no results | Index is empty or paths are excluded | Run `xtoo sync` or check `assistant_excludes` in configuration |
| Semantic search not working | Vectors have not been built | Run `xtoo embed` to build vectors |
| Query returns unexpected results | Check for quoted phrases or excluded words | Use `"exact phrase"` for exact matches or `-word` to exclude terms |
