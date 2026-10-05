"""VAB sound banks as Sony's tools write them.

A bank is a header (`pBAV`, the program and tone tables and a table of
waveform sizes) and a body of SPU waveforms laid end to end. They ship as
one .VAB file, or as a .VH header and a .VB body, which some games rename
(.VA) or pack into their own archives. The decoder shared with the WVD
banks wants the header, one empty block, then the body; `canonical` puts
any of those shapes into that form.
"""
import struct
from formats.audio import sfx


def header_size(data, at=0):
    """Length of the VAB header at `at`, or 0 if there is none."""
    if data[at:at + 4] != sfx.MAGIC or at + sfx.HEADER > len(data):
        return 0
    programs, _tones, vags = struct.unpack_from('<HHH', data, at + 18)
    length = sfx.header_length(programs)
    return length if programs <= 128 and vags <= 255 and at + length <= len(data) else 0


def waveform_sizes(data, at=0):
    """Byte length of each waveform the header at `at` lists."""
    length = header_size(data, at)
    if not length:
        return []
    vags = struct.unpack_from('<H', data, at + 22)[0]
    table = struct.unpack_from('<256H', data, at + length - sfx.SIZE_TABLE)
    return [size * 8 for size in table[1:vags + 1]]


def body_size(data, at=0):
    """Bytes of waveforms the header at `at` describes."""
    return sum(waveform_sizes(data, at))


def is_body(data, sizes, at=0):
    """Whether waveforms of these sizes start at `at`. Every waveform opens
    with an empty block and closes, in its last block or the one before,
    with the end flag; padding between two files has the first and never
    the second."""
    for size in sizes[:6]:
        if at + size > len(data) or any(data[at:at + sfx.BLOCK]):
            return False
        if size >= 2 * sfx.BLOCK and not (data[at + size - sfx.BLOCK + 1] | data[at + size - 2 * sfx.BLOCK + 1]) & sfx.END:
            return False
        at += size
    return bool(sizes)


def canonical(head, body):
    """Header and body as one bank in the form the sample decoder reads."""
    return bytes(head[:header_size(head)]) + bytes(sfx.BLANK) + bytes(body)


def whole(data, at=0):
    """The bank whose header is at `at` when its body follows directly,
    else None. Returns (canonical bank, bytes it takes in `data`)."""
    length, sizes = header_size(data, at), waveform_sizes(data, at)
    body = sum(sizes)
    if not length or not body or at + length + body > len(data) or not is_body(data, sizes, at + length):
        return None
    return canonical(data[at:at + length], data[at + length:at + length + body]), length + body


def find_body(data, at=0, reach=4096):
    """Where the waveforms of the header at `at` start when they are not
    right behind it, or -1. Files that keep both in one piece often pad the
    header to a sector first."""
    length, sizes = header_size(data, at), waveform_sizes(data, at)
    if not length or not sizes:
        return -1
    for start in range(at + length, min(len(data) - sum(sizes), at + length + reach) + 1, 4):
        if is_body(data, sizes, start):
            return start
    return -1


def summary(bank):
    """Counts of a canonical bank: (programs, tones, waveforms)."""
    return struct.unpack_from('<HHH', bank, 18)
