"""The browser interface, driven in a real browser against a running server.

Needs Playwright and a Chromium it can launch, and skips itself otherwise:
    python -m pip install playwright && python -m playwright install chromium
"""

import socket
import threading
import time

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from xtoo.web import create_app  # noqa: E402


@pytest.fixture
def served(correspondence):
    """The correspondence library behind a real server on a free local port."""
    settings = correspondence[1]
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, background=False),
            host="127.0.0.1",
            port=port,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def page(served):
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except sync_api.Error as error:
            pytest.skip(f"Chromium unavailable: {error.message.splitlines()[0]}")
        page = browser.new_page()
        problems = []
        page.on("console", lambda m: m.type == "error" and problems.append(m.text))
        page.on("pageerror", lambda error: problems.append(str(error)))
        page.goto(served)
        yield page
        browser.close()
    # A content security policy violation or a script error surfaces here.
    assert problems == []


def test_search_preview_links_and_filters(page):
    expect = sync_api.expect
    count = page.locator("#result-count")
    expect(count).to_have_text("3 conversations across 5 documents")

    # Typing searches; replies collapse into one row with a message count.
    page.fill("#query", "upgrade")
    expect(count).to_have_text("1 conversation across 3 documents")
    result = page.locator(".result")
    expect(result).to_have_count(1)
    expect(result.locator(".badge", has_text="3 messages")).to_be_visible()

    # Selecting a result previews its text, with the search words marked.
    result.click()
    expect(page.locator("#preview-document")).to_be_visible()
    expect(page.locator("#preview-content")).to_contain_text("Upgrade fails")
    expect(page.locator("#preview-content mark").first).to_have_text("Upgrade")

    # An entity link gathers everything mentioning it, across file types.
    page.locator("#preview-entities .entity", has_text="PROJ-4821").click()
    expect(page.locator("#entity-filter")).to_be_visible()
    expect(count).to_have_text("1 conversation across 3 documents")  # with the query
    page.fill("#query", "")
    expect(count).to_have_text("2 conversations across 4 documents")  # and the script
    page.click("#entity-clear")
    expect(page.locator("#entity-filter")).to_be_hidden()

    # Every reply, with an excluded phrase. A result may still hold one of its words,
    # which is not what was searched for and is left unmarked.
    page.uncheck("#collapse")
    page.fill("#query", 'upgrade -"over there"')
    expect(count).to_have_text("3 documents found")
    page.locator(".result", has_text="c.msg").click()
    expect(page.locator("#preview-content")).to_contain_text("Over to you")
    marked = page.locator("#preview-content mark").all_inner_texts()
    assert marked and not {text.lower() for text in marked} & {"over", "there"}

    # A date range, and clearing it.
    page.fill("#since", "2026-05-01")
    page.fill("#until", "2026-05-31")
    expect(count).to_have_text("1 document found")
    page.click("#clear-dates")
    expect(count).to_have_text("3 documents found")

    # The file type list is built from what is indexed.
    page.fill("#query", "")
    page.select_option("#kind", "sh")
    expect(count).to_have_text("1 document in your library")

    # A query that matches nothing says so.
    page.select_option("#kind", "")
    page.fill("#query", "nonexistentword")
    expect(page.locator("#results .empty h2")).to_have_text("No matching documents")


def test_slash_focuses_search_and_refresh_requests_a_scan(page):
    expect = sync_api.expect
    page.locator("#results").click()
    page.keyboard.press("/")
    expect(page.locator("#query")).to_be_focused()

    page.click("#refresh")
    expect(page.locator("#notice")).to_have_text(
        "Scan requested. Results will refresh when it finishes."
    )
