"""Structure derived from indexed text: document dates, conversations, and entities.

Everything here reads the text already stored in the index, so existing documents can
be enriched in place without reopening or re-extracting the original files.
"""

import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime

EMAIL_KINDS = {"msg", "eml"}
HEADER_LIMIT = 4000
MAX_ENTITIES = 64

# "RE:", "FW:", "FWD:", "AW:", "SV:", "RE[2]:", repeated and in any mixture.
REPLY_PREFIX = re.compile(r"^\s*(?:re|fw|fwd|aw|sv|tr|vs)\s*(?:\[\d+\])?\s*:", re.IGNORECASE)
SPACING = re.compile(r"\s+")
SUBJECT_LINE = re.compile(r"^Subject:[ \t]*(.+)$", re.MULTILINE)
DATE_LINE = re.compile(r"^Date:[ \t]*(.+)$", re.MULTILINE)
PARTICIPANT_LINE = re.compile(r"^(?:From|To|Cc):[ \t]*(.+)$", re.MULTILINE)
ADDRESS_IN_NAME = re.compile(r"<[^>]*>")

TICKET = re.compile(r"\b([A-Z][A-Z0-9]{1,9})-(\d{1,6})\b")
ADDRESS = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
# Standards, encodings and algorithms that share the shape of a tracker reference.
NOT_TICKETS = {
    "AES",
    "ANSI",
    "ASCII",
    "DIN",
    "EIA",
    "EN",
    "IEC",
    "IEEE",
    "IPV",
    "ISO",
    "ITU",
    "JPEG",
    "MD",
    "MP",
    "MPEG",
    "PDF",
    "RFC",
    "RSA",
    "SHA",
    "SSL",
    "TLS",
    "UTF",
    "WINDOWS",
}


def thread_key(content: str, title: str, kind: str) -> str:
    """A conversation key shared by every reply and forward of one subject."""
    if kind not in EMAIL_KINDS:
        return ""
    match = SUBJECT_LINE.search(content[:HEADER_LIMIT])
    subject = match.group(1) if match else title
    while True:
        stripped = REPLY_PREFIX.sub("", subject, count=1)
        if stripped == subject:
            break
        subject = stripped
    subject = SPACING.sub(" ", subject).strip().strip("-–—:").strip().lower()
    # Very short subjects would merge unrelated conversations.
    return subject if len(subject) >= 3 else ""


def document_date(content: str, kind: str):
    """Nanoseconds for the Date header of an indexed message, or None."""
    if kind not in EMAIL_KINDS:
        return None
    match = DATE_LINE.search(content[:HEADER_LIMIT])
    if not match:
        return None
    value = match.group(1).strip()
    try:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            moment = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    if not 1990 <= moment.year <= 2200:
        return None
    return int(moment.timestamp()) * 1_000_000_000


def participants(content: str, kind: str):
    """Display names on the From, To and Cc lines of an indexed message."""
    for match in PARTICIPANT_LINE.finditer(content[:HEADER_LIMIT]):
        value = match.group(1)
        if kind == "msg":
            # Outlook writes "Surname, Forename; Surname, Forename", so only ; separates.
            names = ADDRESS_IN_NAME.sub("", value).split(";")
        else:
            names = [name for name, _ in getaddresses([value])]
        for name in names:
            name = SPACING.sub(" ", name).strip().strip("'\"").strip()
            if name and "@" not in name:
                yield name


def entities(content: str, kind: str):
    """Identifiers worth linking documents by, most specific first."""
    groups = {"ticket": [], "person": [], "address": []}
    seen = set()

    def add(entity_kind, name, cap):
        if not 2 <= len(name) <= 120 or (entity_kind, name) in seen:
            return
        if len(groups[entity_kind]) < cap:
            seen.add((entity_kind, name))
            groups[entity_kind].append((entity_kind, name))

    for match in TICKET.finditer(content):
        if match.group(1) not in NOT_TICKETS:
            add("ticket", match.group(0), 32)
    for name in participants(content, kind):
        add("person", name, 32)
    for match in ADDRESS.finditer(content):
        add("address", match.group(0).lower(), 16)
    return (groups["ticket"] + groups["person"] + groups["address"])[:MAX_ENTITIES]


def enrichment(content: str, title: str, kind: str, fallback_ns: int):
    """Every derived field for one document."""
    return {
        "document_ns": document_date(content, kind) or fallback_ns,
        "thread": thread_key(content, title, kind),
        "entities": entities(content, kind),
    }
