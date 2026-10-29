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
    extend, append = out.extend, out.append
    end = len(data)
    pos = 8
    done = 0                          # len(out), kept by hand: it is asked for per token
    while done < size:
        if pos + 2 > end:
            raise FormatError(f"Truncated GAM command at 0x{pos:X}")
        flags = data[pos] | data[pos + 1] << 8
        pos += 2
        for _ in range(16):
            if done >= size:
                break
            if flags & 1:
                if pos + 2 > end:
                    raise FormatError("Truncated GAM back-reference")
                distance, count = data[pos], data[pos + 1]
                pos += 2
                if not distance or distance > done or not count:
                    raise FormatError(f"Invalid GAM back-reference at 0x{pos - 2:X}")
                if count > size - done:
                    count = size - done
                start = done - distance
                if count <= distance:
                    extend(out[start:start + count])
                else:
                    # An overlapping match repeats the preceding window.
                    window = out[start:]
                    extend((window * ((count + distance - 1) // distance))[:count])
                done += count
            else:
                if pos >= end:
                    raise FormatError("Truncated GAM literal")
                append(data[pos])
                pos += 1
                done += 1
            flags >>= 1
    return bytes(out)
