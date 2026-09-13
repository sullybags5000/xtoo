"""Synthetic data shared by the tests. Every name and identifier here is invented."""

import re
import struct
import zlib
from datetime import datetime, timezone

from outlook_msg import build as build_msg

__all__ = ["build_msg", "utf16", "bag_of_words", "conversation"]


def utf16(value):
    return value.encode("utf-16-le")


def bag_of_words(texts):
    """A deterministic stand-in for the embedding model: no download, no network.

    crc32 rather than hash(), which is seeded differently in every process and would
    make distances, and therefore the relevance limit, vary between runs.
    """
    encoded = []
    for text in texts:
        vector = [0.0] * 256
        for word in set(re.findall(r"\w+", text.lower())):
            vector[zlib.crc32(word.encode()) % 256] += 1.0
        scale = sum(value * value for value in vector) ** 0.5 or 1.0
        encoded.append([value / scale for value in vector])
    return encoded


def conversation(
    root,
    name,
    subject,
    body,
    when,
    to="Ford, Alex; Lee, Sam",
    sender="Jane Doe",
    address="jane.doe@example.com",
):
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    ticks = int((when - epoch).total_seconds() * 10_000_000)
    (root / name).write_bytes(
        build_msg(
            {
                "__substg1.0_0037001F": utf16(subject),
                "__substg1.0_0C1A001F": utf16(sender),
                "__substg1.0_5D01001F": utf16(address),
                "__substg1.0_0E04001F": utf16(to),
                "__substg1.0_1000001F": utf16(body),
                "__properties_version1.0": b"\x00" * 32 + struct.pack("<IIQ", 0x0E060040, 6, ticks),
            }
        )
    )
