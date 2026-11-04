import struct
from types import SimpleNamespace

from formats.archive.ldar import parse_ldar


def test_packed_continuation_starts_after_alignment():
    # A five-byte first piece needs three padding bytes before the WMD.
    record = struct.pack('<IHHIII', 3, 1, 0x7000, 0, 5, 0)
    continuation = struct.pack('<IHHIII', 0xFFFFFFFF, 0, 0x5000, 0, 4, 0)
    end = struct.pack('<IHHIII', 0, 0xFFFF, 0, 0, 0, 0)
    footer = struct.pack('<II', 0, 0x80010000)
    source = SimpleNamespace(path='AREA01/TEST.GAM')
    group = parse_ldar(record + continuation + end + footer, 'test', SimpleNamespace(links={1: source}))[0]
    assert [(a.kind, a.offset, a.size) for a in group.assets] == [('WHM', 0, 5), ('WMD', 8, 4)]
