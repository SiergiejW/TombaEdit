"""Standard MIDI files, turned into Sony's SEQ so the same player takes them.

A SEQ is one MIDI track behind a fifteen-byte header: `pQES`, a version,
the ticks per quarter note, the first tempo and the time signature. Its
events are MIDI's own, running status included; the only meta events kept
are tempo changes, written without their length byte, and the end of the
track. A MIDI file with several tracks is merged into that one track by
time.
"""
import struct
from disc.reader import FormatError

MAGIC = b'MThd'


def vlq(value):
    out = [value & 127]
    while value >> 7:
        value >>= 7
        out.insert(0, value & 127 | 128)
    return bytes(out)


def tracks(data):
    """(ticks per quarter, [[(tick, status, bytes)]]) of a MIDI file."""
    if data[:4] != MAGIC or len(data) < 14:
        raise FormatError('Not a MIDI file')
    length, _format, count, division = struct.unpack_from('>IHHH', data, 4)
    if division & 0x8000:
        raise FormatError('MIDI files timed in frames are not supported')
    pos, out = 8 + length, []
    for _ in range(count):
        if data[pos:pos + 4] != b'MTrk':
            break
        end = pos + 8 + struct.unpack_from('>I', data, pos + 4)[0]
        pos, tick, running, events = pos + 8, 0, 0, []
        while pos < min(end, len(data)):
            delta = 0
            while True:
                byte = data[pos]
                pos += 1
                delta = delta << 7 | byte & 127
                if not byte & 128:
                    break
            tick += delta
            status = data[pos]
            if status & 0x80:
                pos += 1
            else:
                status = running
            if status == 0xFF:
                kind = data[pos]
                size, used = 0, 1
                while True:
                    byte = data[pos + used]
                    used += 1
                    size = size << 7 | byte & 127
                    if not byte & 128:
                        break
                body = bytes(data[pos + used:pos + used + size])
                pos += used + size
                if kind == 0x51 and size == 3:
                    events.append((tick, 0xFF, body))
                elif kind == 0x2F:
                    break
            elif status in (0xF0, 0xF7):
                size = 0
                while True:
                    byte = data[pos]
                    pos += 1
                    size = size << 7 | byte & 127
                    if not byte & 128:
                        break
                pos += size
            elif status >= 0x80:
                running = status
                size = 1 if status & 0xF0 in (0xC0, 0xD0) else 2
                events.append((tick, status, bytes(data[pos:pos + size])))
                pos += size
            else:
                raise FormatError('MIDI track has data without a status byte')
        out.append(events)
        pos = end
    return division or 480, out


def to_seq(data):
    """The MIDI file as SEQ bytes."""
    try:
        division, parts = tracks(data)
    except IndexError:
        raise FormatError('MIDI file is cut off') from None
    merged = sorted((event for part in parts for event in part), key=lambda event: event[0])
    tempo = next((body for _, status, body in merged if status == 0xFF), b'\x07\xa1\x20')
    out = bytearray(b'pQES' + b'\0\0\0\1' + struct.pack('>H', division) + tempo + b'\x04\x02')
    tick = 0
    for at, status, body in merged:
        out += vlq(at - tick)
        tick = at
        # Tempo is the one meta event a SEQ has, and it has no length byte.
        out += (b'\xff\x51' + body) if status == 0xFF else bytes((status,)) + body
    return bytes(out + b'\0\xff\x2f\0')
