"""Fixtures shared by every test module."""

from datetime import datetime, timezone

import pytest
from helpers import conversation

from xtoo.config import Settings
from xtoo.indexer import Indexer
from xtoo.store import Store


@pytest.fixture
def library(tmp_path):
    documents = tmp_path / "OneDrive - Example Company"
    documents.mkdir()
    settings = Settings(folders=(documents,), data_dir=tmp_path / "index")
    store = Store(settings.data_dir)
    return documents, settings, store, Indexer(settings, store)


@pytest.fixture
def correspondence(library):
    root, settings, store, indexer = library
    moment = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)
    conversation(root, "a.msg", "[JIRA] (PROJ-4821) Upgrade fails", "First report", moment)
    conversation(
        root,
        "b.msg",
        "RE: [JIRA] (PROJ-4821) Upgrade fails",
        "Root cause",
        moment.replace(month=4),
    )
    conversation(
        root,
        "c.msg",
        "FW: RE: [JIRA] (PROJ-4821) Upgrade fails",
        "Over to you",
        moment.replace(month=5),
    )
    conversation(root, "d.msg", "Lab notice", "UTF-8 and SHA-1 are not tickets", moment)
    (root / "fix.sh").write_text("#!/bin/bash\n# workaround for PROJ-4821\nrestart vpxd\n")
    indexer.scan()
    return root, settings, store, indexer
