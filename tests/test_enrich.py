import sqlite3
from datetime import datetime, timezone

import pytest
from helpers import bag_of_words, conversation

from xtoo import vectors
from xtoo.enrich import entities, thread_key
from xtoo.migrate import enrich_documents
from xtoo.store import Store


def test_message_dates_replace_file_timestamps(correspondence):
    _, _, store, _ = correspondence
    dates = {
        item["title"]: datetime.fromtimestamp(item["document_ns"] / 1e9, timezone.utc).date()
        for item in store.search()["items"]
    }
    assert str(dates["a.msg"]) == "2026-03-02"
    assert str(dates["c.msg"]) == "2026-05-02"
    # A file with no message date keeps its filesystem timestamp.
    assert dates["fix.sh"] >= datetime(2025, 1, 1).date()
    assert [item["title"] for item in store.search()["items"]][:2] == ["fix.sh", "c.msg"]


def test_replies_collapse_into_one_conversation(correspondence):
    _, _, store, _ = correspondence
    assert store.search("upgrade")["total"] == 3
    collapsed = store.search("upgrade", collapse=True)
    assert collapsed["total"] == 1
    assert collapsed["items"][0]["thread_size"] == 3
    # Documents outside a conversation are never merged together.
    assert store.search(collapse=True)["total"] == 3
    assert thread_key("Subject: RE: FW: Budget\n", "x.msg", "msg") == "budget"
    assert thread_key("Subject: Hi\n", "x.msg", "txt") == ""


def test_entities_link_mail_and_scripts(correspondence):
    _, _, store, _ = correspondence
    linked = store.search(entity="PROJ-4821")
    assert {item["title"] for item in linked["items"]} == {"a.msg", "b.msg", "c.msg", "fix.sh"}
    assert store.search(entity="Lee, Sam")["total"] == 4
    assert store.search(entity="jane.doe@example.com")["total"] == 4
    assert store.entities("PROJ")[0] == {"kind": "ticket", "name": "PROJ-4821", "count": 4}
    assert store.entities("%") == []  # wildcards are escaped, not interpreted
    found = {name for _, name in entities("UTF-8 SHA-1 PDF-2 see OPS-77", "txt")}
    assert found == {"OPS-77"}


def test_migrate_enriches_an_index_built_before_enrichment(tmp_path):
    directory = tmp_path / "index"
    directory.mkdir()
    legacy = sqlite3.connect(directory / "index.sqlite3")
    legacy.executescript(
        """CREATE TABLE documents (id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE,
        root TEXT NOT NULL, title TEXT NOT NULL, kind TEXT NOT NULL, modified_ns INTEGER NOT NULL,
        size INTEGER NOT NULL, content TEXT NOT NULL);
        CREATE VIRTUAL TABLE search_index USING fts5(title, content, content='documents',
        content_rowid='id');
        CREATE TRIGGER documents_insert AFTER INSERT ON documents BEGIN
        INSERT INTO search_index(rowid, title, content) VALUES (new.id, new.title, new.content);
        END;"""
    )
    legacy.execute(
        "INSERT INTO documents(path, root, title, kind, modified_ns, size, content) "
        "VALUES ('/m/one.msg', '/m', 'one.msg', 'msg', 1700000000000000000, 10, ?)",
        (
            "Subject: RE: Cluster upgrade\nFrom: Jane Doe <jane.doe@example.com>\n"
            "To: Lee, Sam\nDate: 2026-03-02 09:00 UTC\nSee PROJ-4821 for detail.",
        ),
    )
    legacy.commit()
    legacy.close()

    store = Store(directory)  # opening an old index adds the new columns
    before = store.search("cluster")["items"][0]
    assert before["document_ns"] == 1700000000000000000  # falls back to the file timestamp
    assert enrich_documents(store) == 1
    after = store.search("cluster")["items"][0]
    assert datetime.fromtimestamp(after["document_ns"] / 1e9, timezone.utc).date().isoformat() == (
        "2026-03-02"
    )
    assert after["thread"] == "cluster upgrade"
    assert store.search(entity="PROJ-4821")["total"] == 1
    assert enrich_documents(store) == 0  # nothing left to do on a second run


@pytest.mark.parametrize("meaning", [False, True])
def test_every_filter_applies_in_both_search_paths(correspondence, meaning):
    """The guard against an option working one way of searching and not the other."""
    pytest.importorskip("sqlite_vec")
    from xtoo.query import Query, moment, run

    root, _, store, indexer = correspondence
    conversation(
        root,
        "robot.msg",
        "[tracker] Upgrade job finished",
        "Automated upgrade notice",
        datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc),
        sender="Tracker (Jira)",
        address="do-not-reply@example.com",
    )
    indexer.scan()
    vectors.build(store, encode=bag_of_words)

    def ask(**options):
        return run(store, Query(text="upgrade", meaning=meaning, **options), encode=bag_of_words)

    everything = ask(collapse=False)
    assert everything["total"] > 1

    assert {item["kind"] for item in ask(kind="msg", collapse=False)["items"]} == {"msg"}
    assert ask(kind="sh", collapse=False)["total"] == 0

    linked = ask(entity="PROJ-4821", collapse=False)
    assert 0 < linked["total"] < everything["total"]

    dated = ask(since=moment("2026-04-01"), until=moment("2026-04-30", True), collapse=False)
    assert dated["total"] >= 1
    for item in dated["items"]:
        assert moment("2026-04-01") <= item["document_ns"] <= moment("2026-04-30", True)

    people = ask(people_only=True, collapse=False)
    assert "robot.msg" not in {item["title"] for item in people["items"]}
    assert "robot.msg" in {item["title"] for item in everything["items"]}

    assert "robot.msg" not in {item["title"] for item in ask(exclude=("robot",))["items"]}

    grouped = ask(collapse=True)
    assert grouped["total"] < everything["total"]
    assert grouped["matched"] >= grouped["total"]
    assert max(item["thread_size"] for item in grouped["items"]) > 1


def test_dates_and_exact_queries_are_understood():
    from xtoo.query import exact, moment

    assert moment("2026-03-02") < moment("2026-03-02", end_of_day=True) < moment("2026-03-03")
    assert moment("") == 0
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        moment("2 March 2026")
    # An identifier gains nothing from meaning, so the semantic arm is skipped.
    assert exact("PROJ-4821") and exact("8.0.300")
    assert not exact("why did the upgrade fail") and not exact("upgrade")


def test_automated_senders_are_recognised():
    from xtoo.enrich import automated

    for sender in ("Tracker (Jira)", "no-reply@example.com", "notifications@example.com"):
        assert automated(f"Subject: x\nFrom: {sender}\n", "msg"), sender
    assert not automated("Subject: x\nFrom: Lee, Sam <sam@example.com>\n", "msg")
    assert not automated("From: no-reply@example.com", "txt")  # only mail is judged
