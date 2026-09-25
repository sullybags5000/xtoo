"""The terminal commands, run in-process so every branch counts towards coverage."""

import json
import os
import sqlite3
import sys

import pytest

from xtoo import cli


@pytest.fixture
def xtoo(correspondence, tmp_path, monkeypatch, capsys):
    """Run `xtoo ARGS` against the shared correspondence library; return the exit
    code and what was printed."""
    root, settings, _, _ = correspondence
    config = tmp_path / "settings.toml"
    config.write_text(
        f"folders = {json.dumps([str(root)])}\ndata_dir = {json.dumps(str(settings.data_dir))}\n"
    )
    # main() tightens the umask for the files it creates; keep that inside the test.
    umask = os.umask(0o022)
    os.umask(umask)

    def run(*args, config_path=config):
        monkeypatch.setattr(sys, "argv", ["xtoo", "--config", str(config_path), *args])
        try:
            cli.main()
            code = 0
        except SystemExit as exit:
            code = exit.code or 0
        finally:
            os.umask(umask)
        out, err = capsys.readouterr()
        return code, out, err

    run.config = config
    return run


def test_search_prints_grouped_results_and_snippets(xtoo):
    code, out, _ = xtoo("search", "upgrade")
    assert code == 0
    assert out.startswith("1 matching documents")
    assert "(+2 in conversation)" in out and "[msg]" in out

    code, out, _ = xtoo("search", "upgrade", "--expand")
    assert out.startswith("3 matching documents")


def test_search_json_and_filters(xtoo):
    code, out, _ = xtoo("search", "--json", "--entity", "PROJ-4821", "--kind", "sh")
    found = json.loads(out)
    assert code == 0 and found["total"] == 1
    assert found["items"][0]["title"] == "fix.sh"

    _, out, _ = xtoo("search", "--json", "--since", "2026-04-01", "--until", "2026-04-30")
    assert {item["title"] for item in json.loads(out)["items"]} == {"b.msg"}

    _, out, _ = xtoo("search", "--json", "--limit", "500", "upgrade -root")
    assert json.loads(out)["limit"] == 100  # clamped, and the exclusion applied
    assert json.loads(out)["total"] == 1


def test_search_rejects_a_malformed_date(xtoo):
    code, _, err = xtoo("search", "upgrade", "--since", "March")
    assert code == 2 and "YYYY-MM-DD" in err


def test_index_reports_json_and_fails_on_errors(xtoo, correspondence):
    root = correspondence[0]
    code, out, _ = xtoo("index")
    assert code == 0 and json.loads(out)["unchanged"] == 5

    code, out, _ = xtoo("index", "--quick")
    assert code == 0 and json.loads(out)["error_count"] == 0

    root.rename(root.with_name("unmounted"))
    code, out, _ = xtoo("index")
    assert code == 1 and json.loads(out)["error_count"] == 1


def test_sync_runs_the_export_then_scans(xtoo, correspondence, tmp_path):
    root = correspondence[0]
    exported = root / "exported.txt"
    command = f"printf 'fresh export' > {json.dumps(str(exported))}"
    xtoo.config.write_text(xtoo.config.read_text() + f"sync_command = {json.dumps(command)}\n")
    code, out, _ = xtoo("sync")
    assert code == 0
    assert "Scanned: 1 indexed, 5 unchanged, 0 removed, 0 errors" in out
    assert exported.exists()

    # A failed export is reported, and what is there is still indexed.
    xtoo.config.write_text(xtoo.config.read_text().replace(json.dumps(command), '"exit 3"'))
    code, out, _ = xtoo("sync", "--quick")
    assert code == 0 and "Export exited 3" in out


def test_sync_extends_existing_vectors_only(xtoo, correspondence, monkeypatch):
    built = []
    monkeypatch.setattr("xtoo.vectors.ready", lambda store: True)
    monkeypatch.setattr("xtoo.vectors.build", lambda store: built.append(store) or {"documents": 0})
    code, out, _ = xtoo("sync")
    assert code == 0 and built and "Embedded 0 new documents" in out


def test_backup_writes_a_copy_once(xtoo, tmp_path):
    target = tmp_path / "copies/index-copy.sqlite3"
    code, out, _ = xtoo("backup", str(target))
    assert code == 0 and "Wrote" in out
    with sqlite3.connect(target) as copy:
        assert copy.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 5
    code, _, err = xtoo("backup", str(target))
    assert code == 2 and "already exists" in err


def test_migrate_embed_and_mcp_dispatch(xtoo, monkeypatch):
    code, out, _ = xtoo("migrate")
    assert code == 0 and "Enriched 0 documents." in out

    calls = {}
    monkeypatch.setattr(
        "xtoo.vectors.build",
        lambda store, report, model_name, rebuild: (
            calls.update(model=model_name, rebuild=rebuild) or {"documents": 5, "chunks": 7}
        ),
    )
    code, out, _ = xtoo("embed", "--model", "local/model", "--rebuild")
    assert code == 0 and "Embedded 5 documents as 7 chunks." in out
    assert calls == {"model": "local/model", "rebuild": True}

    monkeypatch.setattr("xtoo.mcp_server.serve", lambda settings: calls.update(mcp=settings))
    assert xtoo("mcp")[0] == 0 and "mcp" in calls


def test_serve_binds_to_localhost_and_checks_the_port(xtoo, monkeypatch):
    started = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **options: started.update(options))
    code, out, _ = xtoo("serve", "--port", "8766")
    assert code == 0 and "http://localhost:8766" in out
    assert started["host"] == "127.0.0.1" and started["port"] == 8766

    code, _, err = xtoo("serve", "--port", "80")
    assert code == 2 and "--port" in err


def test_missing_configuration_points_to_init(xtoo, tmp_path):
    code, _, err = xtoo("index", config_path=tmp_path / "absent.toml")
    assert code == 2 and "xtoo init --folder" in err
