import json

import pytest

from xtoo.config import Settings, load_settings
from xtoo.web import create_app


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


def test_quick_scan_trusts_folders_whose_timestamp_has_not_moved(library):
    root, _, store, indexer = library
    (root / "notes").mkdir()
    (root / "notes/one.txt").write_text("first")
    assert indexer.scan()["indexed"] == 1

    # A quick scan does not re-examine a folder that has not changed.
    quick = indexer.scan(full=False)
    assert quick["indexed"] == 0 and quick["unchanged"] == 1
    assert store.search("first")["total"] == 1

    # A new file changes the folder, so a quick scan still finds it.
    (root / "notes/two.txt").write_text("second")
    assert indexer.scan(full=False)["indexed"] == 1
    assert store.search("second")["total"] == 1

    # A deletion changes the folder too, so nothing is left behind.
    (root / "notes/one.txt").unlink()
    assert indexer.scan(full=False)["removed"] == 1
    assert store.search("first")["total"] == 0

    # Editing a file does not change its folder, so only a full scan sees it.
    (root / "notes/two.txt").write_text("rewritten entirely")
    assert indexer.scan(full=False)["indexed"] == 0
    assert store.search("rewritten")["total"] == 0
    assert indexer.scan(full=True)["indexed"] == 1
    assert store.search("rewritten")["total"] == 1


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
