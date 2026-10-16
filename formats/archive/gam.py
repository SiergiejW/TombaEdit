"""Bounded GAM LZ decoder; does not silently repair truncated streams."""
import struct
from disc.reader import FormatError


def decompress(data, max_size=64 * 1024 * 1024):
    if not data.startswith(b"GAM\0"):
        return data
    if len(data) < 8:
        raise FormatError("Truncated GAM header")
    size = struct.unpack_from("<I", data, 4)[0]
    if size > max_size:
        raise FormatError(f"GAM output size exceeds {max_size:,} byte limit")
    out = bytearray()
    pos = 8
    while len(out) < size:
        if pos + 2 > len(data):
            raise FormatError(f"Truncated GAM command at 0x{pos:X}")
        flags = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        for bit in range(16):
            if len(out) >= size:
                break
            if flags & (1 << bit):
                if pos + 2 > len(data):
                    raise FormatError("Truncated GAM back-reference")
                distance, count = data[pos:pos + 2]
                pos += 2
                if not distance or distance > len(out) or not count:
                    raise FormatError(f"Invalid GAM back-reference at 0x{pos - 2:X}")
                count = min(count, size - len(out))
                start = len(out) - distance
                if count <= distance:
                    out.extend(out[start:start + count])
                else:
                    # An overlapping match repeats the preceding window.
                    window = out[start:]
                    out.extend((window * ((count + distance - 1) // distance))[:count])
            else:
                if pos >= len(data):
                    raise FormatError("Truncated GAM literal")
                out.append(data[pos])
                pos += 1
    return bytes(out)
