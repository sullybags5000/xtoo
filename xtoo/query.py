"""One description of a search, and one place that decides how to answer it.

Every interface — the browser, the terminal and the assistant — builds a `Query` and
calls `run`. Keeping the decision in one place is what stops an option working in one
way of searching and silently doing nothing in another.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

DAY_NS = 86_400_000_000_000
# A tracker reference, an address on the network or a version: exact strings that
# full-text search answers precisely and that meaning cannot improve.
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9]{1,9}-\d{1,6}$")
NUMERIC = re.compile(r"^\d+(\.\d+)+$")


@dataclass(frozen=True)
class Query:
    text: str = ""
    kind: str = ""
    entity: str = ""
    since: int = 0
    until: int = 0
    collapse: bool = True
    meaning: bool = False
    people_only: bool = False
    exclude: tuple = field(default_factory=tuple)
    offset: int = 0
    limit: int = 40

    def narrowing(self):
        """The predicates, without the text, for filtering a ranking built elsewhere."""
        return {
            "kind": self.kind,
            "entity": self.entity,
            "since": self.since,
            "until": self.until,
            "people_only": self.people_only,
            "exclude": self.exclude,
        }


def moment(value: str, end_of_day: bool = False) -> int:
    """Nanoseconds for a YYYY-MM-DD date, or 0 when there is nothing to parse."""
    value = (value or "").strip()
    if not value:
        return 0
    try:
        day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError(f"Dates are written as YYYY-MM-DD, not {value!r}") from error
    stamp = int(day.timestamp()) * 1_000_000_000
    return stamp + DAY_NS - 1 if end_of_day else stamp


def exact(text: str) -> bool:
    """Whether a query is an exact string that semantic search cannot improve on."""
    words = text.split()
    return len(words) == 1 and bool(IDENTIFIER.match(words[0]) or NUMERIC.match(words[0]))


def run(store, query: Query, encode=None):
    """Answer a query, using meaning as well as words when that can help."""
    if query.meaning and query.text.strip() and not exact(query.text):
        from . import vectors

        if vectors.ready(store):
            return vectors.search(store, query, encode=encode)
    return store.search(
        query.text,
        kind=query.kind,
        offset=query.offset,
        limit=query.limit,
        entity=query.entity,
        collapse=query.collapse,
        since=query.since,
        until=query.until,
        people_only=query.people_only,
        exclude=query.exclude,
    )
