import pytest
from helpers import bag_of_words

from xtoo import vectors
from xtoo.query import Query as Ask


def test_semantic_vectors_build_resume_and_rank(correspondence):
    pytest.importorskip("sqlite_vec")

    root, _, store, indexer = correspondence
    built = vectors.build(store, encode=bag_of_words)
    assert built["documents"] == 5 and built["chunks"] >= 5
    assert vectors.build(store, encode=bag_of_words)["documents"] == 0  # resumes, does not redo

    found = vectors.similar(store, "restart vpxd", encode=bag_of_words)
    script = store.search("workaround")["items"][0]["id"]
    assert script in found

    fused = vectors.search(store, Ask(text="vpxd", limit=5, collapse=False), encode=bag_of_words)
    assert fused["total"] >= 1
    assert all(item["snippet"] for item in fused["items"])

    # Editing a file makes its vectors stale, and only that document is redone.
    (root / "fix.sh").write_text("#!/bin/bash\n# replaced entirely\n")
    indexer.scan()
    assert vectors.build(store, encode=bag_of_words)["documents"] == 1

    # Deleting a file clears its vectors rather than leaving them to be matched.
    (root / "fix.sh").unlink()
    indexer.scan()
    vectors.build(store, encode=bag_of_words)
    assert script not in vectors.similar(store, "restart vpxd", encode=bag_of_words)


def test_changing_the_embedding_model_rebuilds_every_vector(correspondence):
    pytest.importorskip("sqlite_vec")

    _, _, store, _ = correspondence
    vectors.build(store, encode=bag_of_words, model_name="first/model")
    with store.connect() as db:
        vectors.prepare(db)
        assert vectors.model_of(db) == "first/model"
    assert vectors.build(store, encode=bag_of_words, model_name="first/model")["documents"] == 0
    # Vectors from two models are not comparable, so the index is rebuilt, not mixed.
    rebuilt = vectors.build(store, encode=bag_of_words, model_name="second/model")
    assert rebuilt["documents"] == 5
    with store.connect() as db:
        vectors.prepare(db)
        assert vectors.model_of(db) == "second/model"


def test_semantic_results_group_conversations_too(correspondence):
    pytest.importorskip("sqlite_vec")

    _, _, store, _ = correspondence
    vectors.build(store, encode=bag_of_words)
    expanded = vectors.search(
        store, Ask(text="upgrade", limit=20, collapse=False), encode=bag_of_words
    )
    grouped = vectors.search(
        store, Ask(text="upgrade", limit=20, collapse=True), encode=bag_of_words
    )
    assert grouped["total"] < expanded["total"]
    assert grouped["matched"] == expanded["total"]  # the documents behind the groups
    leader = next(item for item in grouped["items"] if item["thread_size"] > 1)
    assert leader["thread_size"] == 3
    assert sum(item["thread_size"] for item in grouped["items"]) == expanded["total"]


def test_text_with_no_words_is_never_stored_as_a_vector(library):
    """A zero vector is equidistant from everything, so it outranks unrelated text."""
    import re

    pytest.importorskip("sqlite_vec")
    from xtoo import vectors

    root, _, store, indexer = library
    (root / "real.txt").write_text("the cluster upgrade failed on node three")
    # Words, then a run of replacement characters from a failed decode. They survive
    # stripping, unlike whitespace, and the model cannot tokenise them, so the second
    # window has no direction at all. This is what a binary-ish file leaves behind.
    padding = ("word " * 350) + ("\ufffd" * 2000)
    (root / "padding.txt").write_text(padding)
    indexer.scan()
    assert len(vectors.pieces("padding.txt", padding)) == 2

    def encode(texts):
        # Mirrors the real model: text it cannot tokenise comes back as zeros.
        return [
            [0.0] * 256 if not re.search(r"[A-Za-z0-9]", text) else bag_of_words([text])[0]
            for text in texts
        ]

    built = vectors.build(store, encode=encode)
    assert built["documents"] == 2
    assert built["chunks"] == 2  # three windows in total, one with nothing to embed
    assert vectors.build(store, encode=encode)["documents"] == 0  # not retried forever

    assert store.search("padding")["total"] == 1, "still indexed and findable by words"
    assert vectors.pack([0.0] * 256) is None


def test_chunking_covers_the_start_of_a_long_document():
    pytest.importorskip("sqlite_vec")

    assert vectors.pieces("title", "") == ["title"]
    windows = vectors.pieces("report", "word " * 4000)
    assert len(windows) == vectors.MAX_CHUNKS
    assert all(len(window) <= vectors.CHUNK for window in windows)
    assert windows[0].startswith("report")
    # Windows overlap, so a phrase on a boundary is not lost.
    assert windows[0][-vectors.OVERLAP :] in windows[1]
