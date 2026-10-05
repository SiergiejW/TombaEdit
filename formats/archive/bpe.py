"""Byte pair encoding as Philip Gage published it in 1994, behind the
`LZSD` header MEL2's archives put on a packed file.

The header is the four letters and a 32-bit count of the bytes from that
count to the end of the packed data. Blocks follow. A block is a table that
gives some byte values a pair of bytes to stand for, then a 16-bit
big-endian length and that many bytes of data in which each value is either
itself or its pair, the pair's halves being expanded in turn.

The table is run-length coded: a count above 127 skips that many values
less 127, leaving them literal; any other count is followed by that many
entries plus one, each a left byte and, unless the value stands for itself,
a right byte.
"""
from disc.reader import FormatError

MAGIC = b'LZSD'


def expand(data, limit=16 * 1024 * 1024, stop=None):
    """The contents of an `LZSD` file; with `stop`, its first bytes only."""
    if data[:4] != MAGIC or len(data) < 8:
        raise FormatError('Not an LZSD file')
    end = min(len(data), 4 + int.from_bytes(data[4:8], 'little'))
    pos, out = 8, bytearray()
    try:
        while pos < end:
            left, right = list(range(256)), [0] * 256
            count, value = data[pos], 0
            pos += 1
            while True:
                if count > 127:
                    value += count - 127
                    count = 0
                if value == 256:
                    break
                for _ in range(count + 1):
                    left[value] = data[pos]
                    pos += 1
                    if left[value] != value:
                        right[value] = data[pos]
                        pos += 1
                    value += 1
                if value == 256:
                    break
                count = data[pos]
                pos += 1
            size = data[pos] << 8 | data[pos + 1]
            pos += 2
            stack = []
            for byte in data[pos:pos + size]:
                if stop is not None and len(out) >= stop:
                    return bytes(out)
                stack.append(byte)
                while stack:
                    value = stack.pop()
                    if left[value] == value:
                        out.append(value)
                    else:
                        stack.append(right[value])
                        stack.append(left[value])
                        if len(stack) > 4096:
                            raise FormatError('LZSD pair table refers to itself')
            pos += size
            if len(out) > limit:
                raise FormatError('LZSD output is larger than any resource should be')
    except IndexError:
        raise FormatError('LZSD data is cut off') from None
    return bytes(out)
