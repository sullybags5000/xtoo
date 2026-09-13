import json
import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from xtoo import mcp_server
from xtoo.config import load_settings
from xtoo.web import create_app


def test_mcp_tools_search_read_and_link(correspondence):
    _, _, store, _ = correspondence
    found = mcp_server.search(store, "upgrade", limit=5)
    assert found["total"] == 1 and found["results"][0]["messages_in_conversation"] == 3
    assert found["results"][0]["date"] == "2026-03-02"
    document = mcp_server.read(store, found["results"][0]["id"], max_characters=200)
    assert "ticket:PROJ-4821" in document["entities"] and document["truncated"] is False
    assert mcp_server.by_entity(store, "PROJ-4821")["total"] == 4
    assert "ticket:PROJ-4821 (4)" in mcp_server.names(store, "PROJ")["names"]
    assert mcp_server.read(store, 99999)["error"]


def test_api_exposes_conversations_and_entity_links(correspondence):
    _, settings, _, _ = correspondence
    with TestClient(create_app(settings, background=False), base_url="http://localhost") as client:
        grouped = client.get("/api/search", params={"q": "upgrade", "collapse": "true"}).json()
        assert grouped["total"] == 1
        assert grouped["items"][0]["thread_size"] == 3
        assert client.get("/api/search", params={"q": "upgrade"}).json()["total"] == 3
        linked = client.get("/api/search", params={"entity": "PROJ-4821"}).json()
        assert linked["total"] == 4
        names = client.get("/api/entities", params={"prefix": "PROJ"}).json()["items"]
        assert names[0] == {"kind": "ticket", "name": "PROJ-4821", "count": 4}
        assert client.get("/api/entities").json()["items"]  # no prefix browses the busiest
        document = client.get(f"/api/documents/{linked['items'][0]['id']}").json()
        assert {"kind": "ticket", "name": "PROJ-4821"} in document["entities"]


def test_api_answers_what_the_interface_asks_for(correspondence):
    """The browser reads these fields and sends these parameters; both are a contract."""

    _, settings, _, _ = correspondence
    static = Path(__file__).resolve().parent.parent / "xtoo" / "static"
    script = (static / "app.js").read_text()
    markup = (static / "index.html").read_text()
    for element in sorted(set(re.findall(r'\$\("([a-z-]+)"\)', script))):
        assert f'id="{element}"' in markup, element

    with TestClient(create_app(settings, background=False), base_url="http://localhost") as client:
        sent = {
            "q": "upgrade",
            "kind": "msg",
            "entity": "",
            "collapse": "true",
            "meaning": "false",
            "people": "false",
            "since": "2026-01-01",
            "until": "2026-12-31",
            "offset": 0,
            "limit": 40,
        }
        found = client.get("/api/search", params=sent).json()
        assert set(found) == {"items", "total", "matched", "offset", "limit"}
        for item in found["items"]:
            assert {"id", "title", "path", "kind", "size", "document_ns", "thread_size"} <= set(
                item
            )
            assert "snippet" in item
        document = client.get(f"/api/documents/{found['items'][0]['id']}").json()
        assert {"content", "document_ns", "modified_ns", "entities", "preview_truncated"} <= set(
            document
        )
        assert client.get("/api/status").json().keys() >= {"kinds", "folders", "semantic"}
        assert client.get("/api/search", params={"since": "yesterday"}).status_code == 422


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
