import struct

from helpers import build_msg, utf16

from xtoo import mail
from xtoo.extract import extract_text


def test_outlook_msg_extraction_and_search(library):
    root, _, store, indexer = library
    # PR_MESSAGE_DELIVERY_TIME as a MAPI FILETIME property.
    properties = b"\x00" * 32 + struct.pack("<IIQ", 0x0E060040, 6, 133000000000000000)
    (root / "Upgrade window_20260909_101402.msg").write_bytes(
        build_msg(
            {
                "__substg1.0_0037001F": utf16("Cluster upgrade window"),
                "__substg1.0_0C1A001F": utf16("Jane Doe"),
                "__substg1.0_5D01001F": utf16("jane.doe@example.com"),
                "__substg1.0_0E04001F": utf16("Sam Lee; Platform Team"),
                "__substg1.0_1013001F": utf16("<p>Approve the window</p><script>bad()</script>"),
                "__properties_version1.0": properties,
                "__attach_version1.0_#00000000": {"__substg1.0_3707001F": utf16("runbook.pdf")},
            }
        )
    )
    assert indexer.scan()["indexed"] == 1
    content = store.document(store.search("upgrade")["items"][0]["id"])["content"]
    assert "Subject: Cluster upgrade window" in content
    assert "From: Jane Doe <jane.doe@example.com>" in content
    assert "Date: 2022-06-18" in content  # FILETIME is decoded, not left as raw bytes
    assert "Attachments: runbook.pdf" in content
    assert "Approve the window" in content and "bad()" not in content
    for query in ("jane.doe", "platform", "runbook", "approve"):
        assert store.search(query)["total"] == 1, query
    assert store.search("cluster", "msg")["total"] == 1


def test_msg_attachment_text_is_indexed_when_asked(tmp_path):

    message = tmp_path / "with-attachment.msg"
    message.write_bytes(
        build_msg(
            {
                "__substg1.0_0037001F": utf16("Logs from the failed run"),
                "__substg1.0_1000001F": utf16("See attached."),
                "__attach_version1.0_#00000000": {
                    "__substg1.0_3707001F": utf16("node3.log"),
                    "__substg1.0_37010102": b"heap allocation failed on node3",
                },
                "__attach_version1.0_#00000001": {
                    "__substg1.0_3707001F": utf16("screenshot.png"),
                    "__substg1.0_37010102": b"\x89PNG\r\n not really an image",
                },
            }
        )
    )
    # Off by default: filenames only, as before.
    plain = extract_text(message, 5000)
    assert "Attachments: node3.log, screenshot.png" in plain
    assert "heap allocation" not in plain

    opened = extract_text(message, 20000, attachments=4000)
    assert "Attachment node3.log:" in opened
    assert "heap allocation failed on node3" in opened
    # An image is named, never decoded, and an unreadable one costs nothing.
    assert "Attachment screenshot.png:" not in opened


def test_eml_attachment_is_parsed_by_its_own_extractor(tmp_path):
    import base64

    from docx import Document

    written = Document()
    written.add_paragraph("The lockbox was empty during the upgrade")
    document = tmp_path / "report.docx"
    written.save(document)
    encoded = base64.encodebytes(document.read_bytes())

    message = tmp_path / "reply.eml"
    message.write_bytes(
        b"From: Lee, Sam <sam@example.com>\r\nSubject: Report\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n--b1\r\n'
        b"Content-Type: text/plain\r\n\r\nAttached.\r\n--b1\r\n"
        b'Content-Disposition: attachment; filename="report.docx"\r\n'
        b"Content-Transfer-Encoding: base64\r\n\r\n" + encoded + b"\r\n--b1--\r\n"
    )
    assert "lockbox" not in extract_text(message, 5000)
    opened = extract_text(message, 20000, attachments=4000)
    assert "Attachment report.docx:" in opened
    assert "The lockbox was empty during the upgrade" in opened


def test_eml_extraction_and_unreadable_message(library):
    root, _, store, indexer = library
    (root / "reply.eml").write_bytes(
        b"From: Bob Smith <bob@example.com>\r\n"
        b"To: dave@example.com\r\n"
        b"Subject: Re: cluster upgrade window\r\n"
        b"Date: Wed, 9 Sep 2026 10:14:02 +0100\r\n"
        b'Content-Type: multipart/mixed; boundary="b1"\r\n\r\n'
        b"--b1\r\n"
        b'Content-Type: text/html; charset="utf-8"\r\n\r\n'
        b"<p>Approved &amp; scheduled.</p><style>hidden{}</style>\r\n"
        b"--b1\r\n"
        b'Content-Disposition: attachment; filename="change-request.pdf"\r\n\r\n'
        b"ABC\r\n--b1--\r\n"
    )
    (root / "truncated.msg").write_bytes(b"not a compound file")
    result = indexer.scan()
    assert result["indexed"] == 1
    assert result["error_count"] == 1  # the unreadable message is reported, not indexed
    content = store.document(store.search("scheduled")["items"][0]["id"])["content"]
    assert "Subject: Re: cluster upgrade window" in content
    assert "Attachments: change-request.pdf" in content
    assert "Approved & scheduled." in content and "hidden" not in content
    assert store.search("bob@example.com")["total"] == 1
    assert store.search("", "eml")["total"] == 1


def test_received_dates_report_export_coverage(tmp_path):
    properties = b"\x00" * 32 + struct.pack("<IIQ", 0x0E060040, 6, 133000000000000000)
    message = tmp_path / "export.msg"
    message.write_bytes(build_msg({"__properties_version1.0": properties}))
    assert mail.received(message).strftime("%Y-%m-%d") == "2022-06-18"

    reply = tmp_path / "reply.eml"
    reply.write_bytes(b"Subject: hi\r\nDate: Wed, 9 Sep 2026 10:14:02 +0100\r\n\r\nbody\r\n")
    assert mail.received(reply).strftime("%Y-%m-%d") == "2026-09-09"

    undated = tmp_path / "undated.eml"
    undated.write_bytes(b"Subject: hi\r\n\r\nbody\r\n")
    assert mail.received(undated) is None
    assert mail.received(tmp_path / "export.msg") is not None
