"""LZSS as Okumura's 1989 lzss.c wrote it, the form many PlayStation tools
adopted unchanged.

A flag byte covers the next eight items, low bit first. A set bit copies
one byte. A clear bit reads two bytes: twelve bits of position in a 4096
byte ring and four bits of length, to which 3 is added. The ring starts
out as zeros and is written from position 0xFEE.
"""
from disc.reader import FormatError

RING = 4096
START = 0xFEE


def decompress(data, limit=16 * 1024 * 1024, stop=None):
    """Unpack `data`; with `stop`, only until that many bytes are out, which
    is enough to see what a packed entry is."""
    ring = bytearray(RING)
    at, out, pos, end = START, bytearray(), 0, len(data)
    while pos < end and (stop is None or len(out) < stop):
        flags = data[pos]
        pos += 1
        for bit in range(8):
            if pos >= end:
                break
            if flags >> bit & 1:
                byte = data[pos]
                pos += 1
                out.append(byte)
                ring[at] = byte
                at = (at + 1) & (RING - 1)
            else:
                if pos + 1 >= end:
                    pos = end
                    break
                low, high = data[pos], data[pos + 1]
                pos += 2
                source = low | (high & 0xF0) << 4
                for n in range((high & 15) + 3):
                    byte = ring[(source + n) & (RING - 1)]
                    out.append(byte)
                    ring[at] = byte
                    at = (at + 1) & (RING - 1)
        if len(out) > limit:
            raise FormatError('LZSS output is larger than any resource should be')
    return bytes(out)
