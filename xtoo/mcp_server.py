"""Read-only access to the index for an MCP client such as Claude Code.

The tools search and read; nothing here indexes, writes, or reaches the network. Answers
are drawn from documents already on this machine, and whatever an assistant retrieves
through these tools leaves the machine with the conversation, so treat it as you would
pasting the text yourself.
"""

from datetime import datetime, timezone

from .store import Store

INSTRUCTIONS = """Search the user's own indexed documents, scripts and exported email.

Prefer this over guessing when a question concerns their work: colleagues, projects,
tickets, incidents, decisions, or anything they wrote or received. Start with
search_documents, then read_document for the full text of a promising result.
find_by_entity is the fastest route when a ticket reference, person or address is
already known."""

READ_LIMIT = 50_000


def when(document_ns: int) -> str:
    if not document_ns:
        return ""
    return datetime.fromtimestamp(document_ns / 1e9, timezone.utc).strftime("%Y-%m-%d")


def result(item: dict) -> dict:
    trimmed = {
        "id": item["id"],
        "title": item["title"],
        "kind": item["kind"],
        "date": when(item["document_ns"]),
        "path": item["path"],
        "excerpt": (item.get("snippet") or "").strip()[:400],
    }
    if item.get("thread_size", 1) > 1:
        trimmed["messages_in_conversation"] = item["thread_size"]
    return trimmed


def search(store: Store, query: str, kind: str = "", limit: int = 10, collapse: bool = True):
    from . import vectors

    limit = max(1, min(limit, 50))
    if query.strip() and vectors.ready(store):
        # Meaning and keywords combined, so a paraphrase still finds the document.
        found = vectors.search(store, query, kind=kind, limit=limit)
    else:
        found = store.search(query, kind=kind, limit=limit, collapse=collapse)
    return {"total": found["total"], "results": [result(item) for item in found["items"]]}


def read(store: Store, document_id: int, max_characters: int = 4000):
    item = store.document(document_id)
    if item is None:
        return {"error": f"No document with id {document_id}"}
    limit = max(200, min(max_characters, READ_LIMIT))
    content = item["content"]
    return {
        "title": item["title"],
        "kind": item["kind"],
        "date": when(item["document_ns"]),
        "path": item["path"],
        "entities": [f"{entity['kind']}:{entity['name']}" for entity in item["entities"]],
        "truncated": len(content) > limit,
        "content": content[:limit],
    }


def by_entity(store: Store, name: str, limit: int = 20):
    found = store.search(entity=name, limit=max(1, min(limit, 50)))
    return {"total": found["total"], "results": [result(item) for item in found["items"]]}


def names(store: Store, prefix: str):
    return {
        "names": [f"{row['kind']}:{row['name']} ({row['count']})" for row in store.entities(prefix)]
    }


def build(store: Store):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name="xtoo", instructions=INSTRUCTIONS)

    @server.tool(
        description=(
            "Full-text search across the user's indexed documents, scripts and email. "
            "Every word must match; words match from the start, so 'migr' finds "
            "'migration'. Optionally restrict to one file type with kind, such as 'msg' "
            "for Outlook mail, 'pdf', or 'py'. collapse shows one row per email "
            "conversation instead of every reply; turn it off to see each message."
        )
    )
    def search_documents(
        query: str, kind: str = "", limit: int = 10, collapse: bool = True
    ) -> dict:
        return search(store, query, kind, limit, collapse)

    @server.tool(
        description=(
            "Read the text of one document found by search_documents, using its id. "
            "Email arrives as a Subject/From/To/Date header block followed by the body."
        )
    )
    def read_document(document_id: int, max_characters: int = 4000) -> dict:
        return read(store, document_id, max_characters)

    @server.tool(
        description=(
            "Every document linked to one identifier: a ticket reference such as "
            "'PROJ-4821', a person as written in mail headers such as 'Lee, Sam', or "
            "an email address. Returns mail, scripts and documents together, which is the "
            "quickest way to assemble the history of a ticket or a correspondent."
        )
    )
    def find_by_entity(name: str, limit: int = 20) -> dict:
        return by_entity(store, name, limit)

    @server.tool(
        description=(
            "Identifiers in the index beginning with the given text, with how many "
            "documents mention each. Use it to find the exact spelling of a ticket key or "
            "a person's name before calling find_by_entity."
        )
    )
    def list_entities(prefix: str) -> dict:
        return names(store, prefix)

    return server


def serve(data_dir):
    build(Store(data_dir)).run("stdio")
