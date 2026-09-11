"""Text extraction only: never execute macros, scripts, or embedded objects."""

from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml", ".log"}
# Scripts and configuration-as-code are read as plain text and never executed.
SCRIPT_EXTENSIONS = {
    ".ps1",
    ".psm1",
    ".psd1",
    ".bat",
    ".cmd",
    ".vbs",
    ".sh",
    ".bash",
    ".zsh",
    ".ksh",
    ".fish",
    ".awk",
    ".py",
    ".pyw",
    ".pl",
    ".pm",
    ".rb",
    ".lua",
    ".php",
    ".r",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".sql",
    ".mk",
    ".tf",
    ".ini",
    ".cfg",
    ".conf",
    ".toml",
    ".properties",
}
MARKUP_EXTENSIONS = {".html", ".htm"}
# Formats that need a parser and must never be decoded as text.
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}
SUPPORTED = TEXT_EXTENSIONS | SCRIPT_EXTENSIONS | MARKUP_EXTENSIONS | DOCUMENT_EXTENSIONS


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "div", "br", "li", "h1", "h2", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Windows scripts are frequently saved in the legacy ANSI code page.
        return data.decode("cp1252", errors="replace")


def chunks(path: Path, text_extensions: frozenset | None = None):
    suffix = path.suffix.lower()
    if text_extensions is None:
        text_extensions = frozenset(TEXT_EXTENSIONS | SCRIPT_EXTENSIONS)
    # Parser-backed formats win over any caller-supplied text extension list.
    if suffix not in DOCUMENT_EXTENSIONS and (
        suffix in text_extensions or suffix in MARKUP_EXTENSIONS
    ):
        text = decode(path.read_bytes())
        if suffix in MARKUP_EXTENSIONS:
            parser = HTMLText()
            parser.feed(text)
            text = "".join(parser.parts)
        yield text
    elif suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF; unlock a permitted copy before indexing")
        for page in reader.pages:
            yield page.extract_text() or ""
    else:
        # Reject unusually large expanded Office archives before invoking parsers.
        with ZipFile(path) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Expanded Office document exceeds 100 MB")
        if suffix == ".docx":
            from docx import Document

            document = Document(path)
            for paragraph in document.paragraphs:
                yield paragraph.text
            for table in document.tables:
                for row in table.rows:
                    yield "\t".join(cell.text for cell in row.cells)
        elif suffix == ".xlsx":
            from openpyxl import load_workbook

            book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
            try:
                for sheet in book:
                    yield sheet.title
                    for row in sheet.iter_rows(values_only=True):
                        yield "\t".join(str(value) if value is not None else "" for value in row)
            finally:
                book.close()
        elif suffix == ".pptx":
            from pptx import Presentation

            for number, slide in enumerate(Presentation(path).slides, 1):
                yield f"Slide {number}"
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        yield shape.text
                    if shape.has_table:
                        for row in shape.table.rows:
                            yield "\t".join(cell.text for cell in row.cells)
        else:
            raise ValueError(f"Unsupported format: {suffix}")


def extract_text(path: Path, limit: int, text_extensions: frozenset | None = None) -> str:
    parts = []
    remaining = limit
    iterator = chunks(path, text_extensions)
    try:
        for part in iterator:
            part = part.replace("\x00", "")[:remaining]
            parts.append(part)
            remaining -= len(part) + 1
            if remaining <= 0:
                break
    finally:
        iterator.close()
    return "\n".join(parts)[:limit]
