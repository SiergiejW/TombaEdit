"""WVD: offset tables for SPU sample bodies and matching VAB headers."""
import struct
from disc.reader import FormatError
from formats.audio import sfx


def spans(data, start, end):
    if start + 4 > end:
        raise FormatError('Truncated WVD table')
    first = struct.unpack_from('<I', data, start)[0]
    if first < 8 or first % 4 or start + first > end:
        raise FormatError('Invalid WVD offset table')
    offsets = struct.unpack_from(f'<{first // 4}I', data, start)
    if offsets != tuple(sorted(offsets)) or start + offsets[-1] > end:
        raise FormatError('WVD offsets exceed container')
    return [(start+a, start+b) for a,b in zip(offsets,offsets[1:])]


def banks(data):
    sections = spans(data, 0, len(data))
    if len(sections) != 2:
        raise FormatError('WVD needs sample and instrument sections')
    bodies, headers = (spans(data, *section) for section in sections)
    if len(bodies) != len(headers):
        raise FormatError('WVD sample/header bank count differs')
    result = []
    for (ba,bb),(ha,hb) in zip(bodies,headers):
        head = data[ha:hb]
        if head[:4] != sfx.MAGIC or len(head) < sfx.HEADER:
            raise FormatError('WVD bank is missing its VAB header')
        programs, _, vags = struct.unpack_from('<HHH',head,18)
        length = sfx.header_length(programs)
        if vags > 255 or len(head) < length:
            raise FormatError('Truncated WVD VAB header')
        # Canonical header + body layout lets the shared Tomba2Edit decoder
        # and synthesizer work without Tomba1-specific offsets.
        canonical = head[:length] + bytes(sfx.BLANK) + data[ba:bb]
        info = dict(offset=0,programs=programs,vags=vags)
        if sum(sfx.sizes(canonical,info)) > bb-ba:
            raise FormatError('WVD sample size table exceeds body')
        result.append(canonical)
    return result


def midi(data, at=0):
    """Sony SEQ events as a standard format-0 MIDI track."""
    from formats.audio import seq
    def vlq(value):
        out = [value & 127]
        while value >> 7:
            value >>= 7; out.insert(0, (value & 127) | 128)
        return bytes(out)
    resolution, tempo = seq.header(data,at)
    track = bytearray(b'\0\xff\x51\x03' + tempo.to_bytes(3,'big'))
    for delta,status,a,b in seq.events(data,at):
        track.extend(vlq(delta))
        if status == 0xff:
            track.extend(b'\xff\x51\x03'+a.to_bytes(3,'big'))
        else:
            track.extend(bytes((status,a)))
            if status & 0xf0 not in (0xc0,0xd0):
                track.append(b)
    track.extend(b'\0\xff\x2f\0')
    return b'MThd'+struct.pack('>IHHH',6,0,1,resolution)+b'MTrk'+struct.pack('>I',len(track))+track
