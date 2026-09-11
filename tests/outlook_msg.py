"""Build a minimal Outlook .msg (OLE compound file) so the parser is tested on real bytes.

Every stream is padded to the 4,096-byte mini-stream cutoff, which keeps all data in
ordinary sectors and avoids implementing the mini FAT.
"""

import struct

SECTOR = 512
STREAM_SIZE = 4096
SECTORS_PER_STREAM = STREAM_SIZE // SECTOR
FREE, END, FAT_MARK = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
STORAGE, STREAM, ROOT = 1, 2, 5


def directory_entry(node) -> bytes:
    name = node["name"].encode("utf-16-le") + b"\x00\x00"
    return (
        name.ljust(64, b"\x00")
        + struct.pack("<HBB", len(name), node["kind"], 1)  # name bytes, type, black
        + struct.pack("<III", FREE, node["sibling"], node["child"])
        + b"\x00" * 16  # CLSID
        + struct.pack("<I", 0)  # state bits
        + b"\x00" * 16  # creation and modification times
        + struct.pack("<IQ", node["start"], node["size"])
    )


def build(tree: dict) -> bytes:
    """Create a compound file. Values are bytes for a stream or a dict for a storage."""
    nodes = []

    def visit(name, value, kind):
        node = {"name": name, "kind": kind, "child": FREE, "sibling": FREE, "data": b""}
        nodes.append(node)
        index = len(nodes) - 1
        if isinstance(value, dict):
            children = [
                visit(key, item, STORAGE if isinstance(item, dict) else STREAM)
                for key, item in value.items()
            ]
            if children:
                nodes[index]["child"] = children[0]
                for current, following in zip(children, children[1:]):
                    nodes[current]["sibling"] = following
        else:
            node["data"] = value
        return index

    visit("Root Entry", tree, ROOT)
    directory_sectors = -(-len(nodes) // 4)
    next_sector = 1 + directory_sectors
    payload = b""
    for node in nodes:
        stored = node["kind"] == STREAM
        node["start"] = next_sector if stored else END
        node["size"] = STREAM_SIZE if stored else 0
        if stored:
            payload += node["data"].ljust(STREAM_SIZE, b"\x00")[:STREAM_SIZE]
            next_sector += SECTORS_PER_STREAM

    fat = [FREE] * (SECTOR // 4)
    fat[0] = FAT_MARK
    first_stream = 1 + directory_sectors
    for sector in range(1, next_sector):
        ends_chain = sector == first_stream - 1 or (
            sector >= first_stream
            and (sector - first_stream) % SECTORS_PER_STREAM == SECTORS_PER_STREAM - 1
        )
        fat[sector] = END if ends_chain else sector + 1

    header = (
        b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # signature
        + b"\x00" * 16  # CLSID
        + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6)  # versions, order, sector shifts
        + b"\x00" * 6  # reserved
        + struct.pack("<II", 0, 1)  # directory sector count (v3: 0), FAT sector count
        + struct.pack("<II", 1, 0)  # first directory sector, transaction signature
        + struct.pack("<II", STREAM_SIZE, END)  # mini stream cutoff, first mini FAT
        + struct.pack("<II", 0, END)  # mini FAT count, first DIFAT sector
        + struct.pack("<II", 0, 0)  # DIFAT count, DIFAT[0] is the single FAT sector
        + struct.pack("<I", FREE) * 108
    )
    directory = b"".join(directory_entry(node) for node in nodes)
    return (
        header
        + struct.pack(f"<{len(fat)}I", *fat)
        + directory.ljust(directory_sectors * SECTOR, b"\x00")
        + payload
    )
