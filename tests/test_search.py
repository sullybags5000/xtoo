import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from xtoo.config import Settings, load_settings
from xtoo.extract import extract_text
from xtoo.indexer import Indexer
from xtoo.store import Store
from xtoo.web import create_app


@pytest.fixture
def library(tmp_path):
    documents = tmp_path / "OneDrive - Example Company"
    documents.mkdir()
    settings = Settings(folders=(documents,), data_dir=tmp_path / "index")
    store = Store(settings.data_dir)
    return documents, settings, store, Indexer(settings, store)


def test_search_updates_deletes_and_prefixes(library):
    root, _, store, indexer = library
    file = root / "Quarterly planning.txt"
    file.write_text("The migration schedule is approved.")
    assert indexer.scan()["indexed"] == 1
    assert store.search("migr sched")["total"] == 1
    assert store.search("quarterly")["total"] == 1
    assert store.search("migration missing")["total"] == 0
    assert store.search("migration", "pdf")["total"] == 0
    assert indexer.scan()["unchanged"] == 1
    file.write_text("Completely different revised budget.")
    assert indexer.scan()["indexed"] == 1
    assert store.search("migration")["total"] == 0
    assert store.search("budget")["total"] == 1
    file.unlink()
    assert indexer.scan()["removed"] == 1
    assert store.search()["total"] == 0


def test_literal_queries_and_pagination(library):
    root, _, store, indexer = library
    for i in range(5):
        (root / f"document-{i}.txt").write_text("OR project café")
    indexer.scan()
    assert store.search('"project" OR (cafe)*')["total"] == 5
    assert store.search("'")["total"] == 0
    assert store.search("' DROP TABLE documents; --")["total"] == 0
    page1 = store.search("project", limit=2)
    page2 = store.search("project", offset=2, limit=2)
    assert page1["total"] == 5
    assert len(page2["items"]) == 2
    assert not {d["id"] for d in page1["items"]} & {d["id"] for d in page2["items"]}


def test_exclusions_symlinks_and_size_limit(library):
    root, settings, store, indexer = library
    (root / "AppData").mkdir()
    (root / "AppData/private.txt").write_text("excluded")
    outside = root.parent / "outside.txt"
    outside.write_text("outside")
    (root / "link.txt").symlink_to(outside)
    (root / "linked-dir").symlink_to(root.parent, target_is_directory=True)
    (root / "~$temporary.docx").write_text("ignore office lock")
    large = root / "large.txt"
    large.write_text("previously indexed")
    indexer.scan()
    assert store.search()["total"] == 1
    with large.open("wb") as handle:
        handle.truncate(settings.max_file_mb * 1024 * 1024 + 1)
    result = indexer.scan()
    assert result["skipped"] == 1
    assert store.search()["total"] == 0


def test_missing_root_keeps_cache_and_removed_source_purges(library):
    root, settings, store, indexer = library
    (root / "note.txt").write_text("cached")
    indexer.scan()
    root.rename(root.with_name("temporarily-unmounted"))
    assert indexer.scan()["error_count"] == 1
    assert store.search("cached")["total"] == 1
    create_app(Settings(folders=(), data_dir=settings.data_dir), background=False)
    assert store.search()["total"] == 0


def test_traversal_error_does_not_purge_existing_files(library, monkeypatch):
    root, _, store, indexer = library
    (root / "note.txt").write_text("keep")
    indexer.scan()

    def failed_walk(path, onerror, followlinks):
        onerror(PermissionError(13, "Permission denied", str(path)))
        return iter(())

    monkeypatch.setattr("xtoo.indexer.os.walk", failed_walk)
    assert indexer.scan()["error_count"] == 1
    assert store.search("keep")["total"] == 1


def test_failed_extraction_discards_old_content_and_recovers(library, monkeypatch):
    root, _, store, indexer = library
    path = root / "file.txt"
    path.write_text("old text")
    indexer.scan()
    path.write_text("new content after edit")

    def fail(*args):
        raise PermissionError("File temporarily unreadable")

    with monkeypatch.context() as context:
        context.setattr("xtoo.indexer.extract_text", fail)
        assert indexer.scan()["error_count"] == 1
        assert store.search()["total"] == 0
    assert indexer.scan()["indexed"] == 1
    assert store.search("new")["total"] == 1


def test_scripts_are_indexed_as_text(library):
    root, _, store, indexer = library
    scripts = {
        "Deploy-Cluster.ps1": "Write-Host 'restart the broker service'",
        "cleanup.bat": "@echo off\nrem purge the broker cache",
        "rotate-logs.sh": "#!/bin/bash\n# archive the broker logs",
        "report.py": "def main():\n    print('broker summary')",
        "schema.sql": "SELECT * FROM broker_events;",
    }
    for name, text in scripts.items():
        (root / name).write_text(text)
    (root / "tool.exe").write_bytes(b"MZ binary payload")
    assert indexer.scan()["indexed"] == len(scripts)
    assert store.search("broker")["total"] == len(scripts)
    assert store.search("Write-Host")["total"] == 1
    assert store.search("restart", "ps1")["total"] == 1
    assert set(store.stats()) == {"ps1", "bat", "sh", "py", "sql"}


def test_ansi_encoded_script_is_readable(library):
    root, _, store, indexer = library
    # Windows scripts are often saved in the legacy ANSI code page, not UTF-8.
    (root / "backup.bat").write_bytes("rem sauvegarde du caf\xe9".encode("cp1252"))
    indexer.scan()
    assert store.search("sauvegarde")["total"] == 1
    assert store.document(store.search("sauvegarde")["items"][0]["id"])["content"].endswith("café")


def test_extra_text_extensions_extend_and_protect_parsers(tmp_path):
    config = tmp_path / "settings.toml"
    root = tmp_path / "documents"
    root.mkdir()
    config.write_text(
        f"folders = {json.dumps([str(root)])}\n"
        f"data_dir = {json.dumps(str(tmp_path / 'index'))}\n"
        'extra_text_extensions = ["GO", ".java"]\n'
    )
    settings = load_settings(config)
    assert settings.extra_text_extensions == (".go", ".java")
    assert {".go", ".java", ".ps1", ".py"} <= settings.text_extensions
    assert not settings.text_extensions & {".pdf", ".docx"}
    (root / "main.go").write_text("package main // deployment helper")
    store = Store(settings.data_dir)
    assert Indexer(settings, store).scan()["indexed"] == 1
    assert store.search("deployment")["total"] == 1
    for text in ('extra_text_extensions = ".py"', 'extra_text_extensions = [".docx"]'):
        config.write_text(f"folders = {json.dumps([str(root)])}\n{text}\n")
        with pytest.raises(ValueError):
            load_settings(config)


def test_configuration_validation_and_nested_roots(tmp_path):
    config = tmp_path / "settings.toml"
    root = tmp_path / "documents"
    config.write_text(f"folders = {json.dumps([str(root), str(root / 'nested'), str(root)])}\n")
    assert load_settings(config).folders == (root,)
    for text in (
        "folders = []",
        "folders = [1]",
        'folders = ["/tmp"]\ninterval_seconds = 0',
        'folders = ["/tmp"]\nmisspelled = 1',
    ):
        config.write_text(text)
        with pytest.raises(ValueError):
            load_settings(config)


def test_office_and_html_extraction(tmp_path):
    from docx import Document
    from openpyxl import Workbook
    from pptx import Presentation
    from pptx.util import Inches

    doc = Document()
    doc.add_paragraph("Paragraph sample")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "Table sample"
    path = tmp_path / "example.docx"
    doc.save(path)
    assert "Paragraph sample" in extract_text(path, 1000)
    assert "Table sample" in extract_text(path, 1000)

    book = Workbook()
    book.active.append(["Invoice", 42])
    path = tmp_path / "example.xlsx"
    book.save(path)
    book.close()
    assert "Invoice\t42" in extract_text(path, 1000)

    slides = Presentation()
    slide = slides.slides.add_slide(slides.slide_layouts[6])
    slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text = "Roadmap slide"
    path = tmp_path / "example.pptx"
    slides.save(path)
    assert "Roadmap slide" in extract_text(path, 1000)

    path = tmp_path / "example.html"
    path.write_text(
        '<p>Visible &amp; useful</p><script>alert("hidden")</script><style>hidden{}</style>'
    )
    text = extract_text(path, 1000)
    assert "Visible & useful" in text
    assert "hidden" not in text


def test_pdf_and_truncation(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 50 700 Td (Searchable PDF example) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    path = tmp_path / "example.pdf"
    writer.write(path)
    assert "Searchable PDF example" in extract_text(path, 1000)
    writer.encrypt("password")
    writer.write(path)
    with pytest.raises(ValueError, match="Encrypted"):
        extract_text(path, 1000)
    path = tmp_path / "text.txt"
    path.write_text("a" * 100)
    assert len(extract_text(path, 20)) == 20
    path.write_bytes("Unicode café".encode("utf-16"))
    assert extract_text(path, 100) == "Unicode café"


def test_api_search_preview_and_request_guards(library):
    root, settings, _, indexer = library
    (root / "report.txt").write_text('<script>alert("example")</script> budget')
    indexer.scan()
    with TestClient(create_app(settings, background=False), base_url="http://localhost") as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert client.get("/static/app.js").status_code == 200
        result = client.get("/api/search", params={"q": "budg"}).json()
        assert result["total"] == 1
        doc = client.get(f"/api/documents/{result['items'][0]['id']}").json()
        assert "<script>" in doc["content"]  # JSON; UI uses text nodes, never HTML.
        assert not doc["preview_truncated"]
        assert client.get("/api/documents/9999").status_code == 404
        assert client.get("/api/search?offset=-1").status_code == 422
        assert client.get("/api/search?limit=1000").status_code == 422
        assert client.get("/api/status").json()["total_documents"] == 1
        assert client.get("/api/search", headers={"Host": "attacker.example"}).status_code == 400
        assert client.post("/api/index").status_code == 403
        headers = {"X-Xtoo-Request": "1", "Origin": "https://attacker.example"}
        assert client.post("/api/index", headers=headers).status_code == 403
        headers["Origin"] = "http://localhost"
        assert client.post("/api/index", headers=headers).status_code == 202
        preflight = client.options(
            "/api/index",
            headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in preflight.headers


def test_background_scan_starts_and_stops(library):
    import time

    root, settings, _, _ = library
    (root / "note.txt").write_text("background")
    app = create_app(settings)
    with TestClient(app, base_url="http://localhost") as client:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if client.get("/api/status").json()["last_finished"]:
                break
            time.sleep(0.02)
        assert client.get("/api/search?q=background").json()["total"] == 1
        (root / "note.txt").unlink()
        client.post("/api/index", headers={"X-Xtoo-Request": "1"})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if client.get("/api/search").json()["total"] == 0:
                break
            time.sleep(0.02)
        assert client.get("/api/search").json()["total"] == 0
    assert not app.state.indexer._thread.is_alive()


def test_cli_init_keeps_configuration_outside_checkout(tmp_path):
    folder = tmp_path / "Documents with spaces"
    folder.mkdir()
    env = {
        **os.environ,
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }
    command = [sys.executable, "-m", "xtoo.cli", "init", "--folder", str(folder)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    config = tmp_path / "config/xtoo/config.toml"
    assert load_settings(config).folders == (folder,)
    assert config.stat().st_mode & 0o077 == 0
    assert subprocess.run(command, env=env, capture_output=True).returncode == 2
    result = subprocess.run(
        [sys.executable, "-m", "xtoo.cli", "index"], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["error_count"] == 0
