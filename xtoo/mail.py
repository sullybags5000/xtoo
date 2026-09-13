"""Exported mail is parsed as data: no mail client, no network, no attachment is opened."""

from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from pathlib import Path

from .text import decode, html_to_text

EMAIL_EXTENSIONS = {".eml", ".msg"}
HEADER_FIELDS = ("Subject", "From", "To", "Cc", "Date")

# MAPI property identifiers as they appear in Outlook .msg stream names.
SUBJECT = "0037"
SENDER_NAME = "0C1A"
SENDER_SMTP = "5D01"
SENDER_ADDRESS = "0C1F"
DISPLAY_TO = "0E04"
DISPLAY_CC = "0E03"
BODY = "1000"
HTML_BODY = "1013"
ATTACH_NAME = "__substg1.0_3707"
ATTACH_DATA = "__substg1.0_3701"
# Formats worth reading inside a message. Images and archives are listed by name only,
# and an attached message is left alone rather than expanded.
ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".txt",
    ".log",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".md",
    ".htm",
    ".html",
    ".ini",
    ".cfg",
    ".conf",
}
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
PROPERTIES = "__properties_version1.0"
DELIVERY_TIME = 0x0E060040
SUBMIT_TIME = 0x00390040
FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)


def header_block(fields) -> str:
    return "\n".join(f"{name}: {value}" for name, value in fields.items() if value)


def text_value(data, name: str) -> str:
    """Decode one MAPI string stream; the name's type suffix selects the encoding."""
    if not data:
        return ""
    text = (
        data.decode("utf-16-le", errors="replace") if name[-4:].lower() == "001f" else decode(data)
    )
    return text.replace("\x00", "").strip()


def filetime(properties):
    """Read the first available timestamp from a fixed-width MAPI property stream."""
    properties = properties or b""
    for tag in (DELIVERY_TIME, SUBMIT_TIME):
        for offset in range(32, len(properties) - 15, 16):
            if int.from_bytes(properties[offset : offset + 4], "little") != tag:
                continue
            value = int.from_bytes(properties[offset + 8 : offset + 16], "little")
            if 0 < value < 2**62:
                try:
                    return FILETIME_EPOCH + timedelta(microseconds=value // 10)
                except OverflowError:
                    continue
    return None


def timestamp(properties) -> str:
    moment = filetime(properties)
    return moment.strftime("%Y-%m-%d %H:%M UTC") if moment else ""


def received(path: Path):
    """Return when a message was received, for reporting on an export's coverage."""
    if path.suffix.lower() == ".msg":
        import olefile

        with olefile.OleFileIO(path) as container:
            for entry in container.listdir():
                if len(entry) == 1 and entry[0].lower() == PROPERTIES:
                    with container.openstream(entry) as stream:
                        return filetime(stream.read())
        return None
    header = message_from_bytes(path.read_bytes(), policy=policy.default).get("Date")
    try:
        return header.datetime if header is not None else None
    except (AttributeError, ValueError):
        return None


def message_chunks(listing, read):
    """Yield text for one .msg. `listing` gives stream paths; `read` returns their bytes."""
    entries = {tuple(part.lower() for part in entry): entry for entry in listing}

    def value(tag):
        for suffix in ("001F", "001E", "0102"):
            name = f"__substg1.0_{tag}{suffix}"
            entry = entries.get((name.lower(),))
            if entry is not None and (data := read(entry)):
                return text_value(data, name)
        return ""

    sender = value(SENDER_NAME)
    address = value(SENDER_SMTP) or value(SENDER_ADDRESS)
    if address and address.lower() not in sender.lower():
        sender = f"{sender} <{address}>".strip()
    properties = entries.get((PROPERTIES,))
    yield header_block(
        {
            "Subject": value(SUBJECT),
            "From": sender,
            "To": value(DISPLAY_TO),
            "Cc": value(DISPLAY_CC),
            "Date": timestamp(read(properties) if properties is not None else None),
        }
    )
    names = sorted(
        name
        for key, entry in entries.items()
        if len(key) == 2
        and key[1].startswith(ATTACH_NAME)
        and (name := text_value(read(entry), entry[1]))
    )
    if names:
        yield "Attachments: " + ", ".join(names)
    yield value(BODY) or html_to_text(value(HTML_BODY))


def attachment_text(name: str, data: bytes, limit: int):
    """Text inside one attachment, read through the ordinary extractors.

    The parsers take a path, so the bytes are written to a private temporary file and
    removed immediately. Nothing is executed and the file is never opened by anything
    but Xtoo's own extraction.
    """
    import tempfile

    from .extract import extract_text

    suffix = Path(name).suffix.lower()
    if suffix not in ATTACHMENT_EXTENSIONS or not data or len(data) > MAX_ATTACHMENT_BYTES:
        return ""
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        handle.write(data)
        handle.close()
        return extract_text(Path(handle.name), limit)
    except Exception:
        # One unreadable attachment must not cost the message it arrived with.
        return ""
    finally:
        Path(handle.name).unlink(missing_ok=True)


def outlook_chunks(path: Path, attachments: int = 0):
    import olefile

    with olefile.OleFileIO(path) as container:

        def read(entry):
            with container.openstream(entry) as stream:
                return stream.read()

        yield from message_chunks(container.listdir(), read)
        if attachments <= 0:
            return
        entries = {tuple(part.lower() for part in entry): entry for entry in container.listdir()}
        for key, entry in sorted(entries.items()):
            if len(key) != 2 or not key[1].startswith(ATTACH_DATA):
                continue
            named = entries.get((key[0], f"{ATTACH_NAME}001f")) or entries.get(
                (key[0], f"{ATTACH_NAME}001e")
            )
            name = text_value(read(named), named[1]) if named else ""
            text = attachment_text(name, read(entry), attachments)
            if text:
                yield f"Attachment {name}:"
                yield text


def rfc822_chunks(data: bytes, attachments: int = 0):
    message = message_from_bytes(data, policy=policy.default)
    yield header_block({name: str(message.get(name, "")).strip() for name in HEADER_FIELDS})
    names = sorted({part.get_filename() for part in message.walk() if part.get_filename()})
    if names:
        yield "Attachments: " + ", ".join(names)
    body = message.get_body(preferencelist=("plain", "html"))
    if body is None:
        if attachments > 0:
            yield from rfc822_attachments(message, attachments)
        return
    try:
        text = body.get_content()
    except (LookupError, ValueError):
        # Unknown or broken charset; fall back to a best-effort decode.
        text = decode(body.get_payload(decode=True) or b"")
    yield html_to_text(text) if body.get_content_subtype() == "html" else text
    if attachments > 0:
        yield from rfc822_attachments(message, attachments)


def rfc822_attachments(message, limit: int):
    for part in message.walk():
        name = part.get_filename()
        if not name or part.get_content_maintype() == "multipart":
            continue
        text = attachment_text(name, part.get_payload(decode=True) or b"", limit)
        if text:
            yield f"Attachment {name}:"
            yield text


def chunks(path: Path, attachments: int = 0):
    if path.suffix.lower() == ".msg":
        yield from outlook_chunks(path, attachments)
    else:
        yield from rfc822_chunks(path.read_bytes(), attachments)
