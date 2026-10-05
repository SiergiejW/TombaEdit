"""What is inside a file that packs other files.

Games rarely ship loose resources; each wraps them in an archive of its
own. Six table layouts are read directly, and whatever follows none of
them is searched for the stock PlayStation formats (TIM, VAB, SEQ, TMD),
which keep their own headers wherever they are stored.

The layouts, by where they were met:

  pairs     a table of (offset, length), the first offset being the length
            of the table itself. The sampler's LPK and APK files, whose LPK
            entries are LZSS-packed, and ANGEL.BIN.
  offsets   a table of ascending offsets, the first again its own length.
  counted   a count, the file's length, then (offset, length) per entry.
            PUYO3's DAT files; unused entries are FFFFFFFF.
  sectors   (sector, length) pairs with no count: MEL2's FAR.
  LVL       a header naming each file with its sector and length: the
            archives of Abe's Oddysee, marked `Indx`.
  RAQ       32-byte records of name, sector and sector count behind a
            copyright line: MEL2.
"""
from dataclasses import dataclass
import struct
from disc.reader import FormatError
from formats.archive import bpe, lzss
from formats.audio import seq, sfx, vab
from formats.images import tim
from formats.models import tmd

SECTOR = 2048


@dataclass
class Item:
    name: str
    kind: str           # 'TIM', 'VAB', 'VAB header', 'SEQ', 'TMD', 'MIDI', 'Save icon', 'EXE' or 'Data'
    offset: int         # in the file it came from
    size: int           # bytes it takes there
    data: bytes = b''   # its contents, unpacked
    note: str = ''
    packed: str = ''    # how it is stored if not as it is: 'LZSS' or 'LZSD'
    loader: object = None

    def load(self):
        """The contents, unpacking them the first time they are wanted."""
        if self.loader is not None:
            self.data, self.loader = self.loader(), None
            self.note = self.note or describe(self.kind, self.data)
        return self.data


def sniff(data):
    """The stock format `data` starts with, or 'Data'."""
    head = bytes(data[:16])
    if head[:4] == b'\x10\0\0\0':
        try:
            tim.parse(data)
            return 'TIM'
        except FormatError:
            pass
    if head[:4] == sfx.MAGIC and vab.header_size(data):
        return 'VAB' if vab.whole(data) else 'VAB header'
    if head[:4] == seq.MAGIC:
        return 'SEQ'
    if head[:4] == b'MThd':
        return 'MIDI'
    if head[:4] == b'\x41\0\0\0' and tmd.objects(data) is not None:
        return 'TMD'
    if head[:2] == b'SC' and head[2] in (0x11, 0x12, 0x13) and len(data) >= 0x100:
        return 'Save icon'
    if head[:8] == b'PS-X EXE':
        return 'EXE'
    return 'Data'


def by_magic(head):
    """What a file probably is from its first bytes alone; used before a
    packed entry has been unpacked in full."""
    for magic, kind in ((b'\x10\0\0\0', 'TIM'), (sfx.MAGIC, 'VAB header'), (seq.MAGIC, 'SEQ'),
                        (b'MThd', 'MIDI'), (b'\x41\0\0\0', 'TMD'), (b'PS-X', 'EXE')):
        if head[:4] == magic:
            return kind
    return 'Save icon' if head[:2] == b'SC' and head[2:3] in (b'\x11', b'\x12', b'\x13') else 'Data'


def sequence(data, at=0):
    """(the SEQ at `at` as version 1, bytes it takes there), or (b'', 0).

    Version 1 is the header and the events. Version 0 puts a 32-bit length
    between the two; it is dropped so that one reader serves both."""
    if data[at:at + 4] != seq.MAGIC or at + seq.HEADER + 4 > len(data):
        return b'', 0
    version = int.from_bytes(data[at + 4:at + 8], 'big')
    if version > 1 or not 0 < int.from_bytes(data[at + 8:at + 10], 'big') <= 960:
        return b'', 0
    if version == 0:
        length = int.from_bytes(data[at + seq.HEADER:at + seq.HEADER + 4], 'big')
        start = at + seq.HEADER + 4
        if not 4 <= length <= len(data) - start:
            return b'', 0
        return (seq.MAGIC + b'\0\0\0\1' + bytes(data[at + 8:at + seq.HEADER]) + bytes(data[start:start + length]),
                seq.HEADER + 4 + length)
    size = seq.length(data, at)
    return (bytes(data[at:at + size]), size) if size > seq.HEADER + 4 else (b'', 0)


def describe(kind, data):
    """A line about one item's contents."""
    try:
        if kind == 'TIM':
            return tim.parse(data).describe()
        if kind in ('VAB', 'VAB header'):
            programs, tones, waves = struct.unpack_from('<HHH', data, 18)
            return f'{programs} programs, {tones} tones, {waves} waveforms'
        if kind == 'SEQ':
            resolution, tempo = seq.header(data, 0)
            return f'{len(seq.events(data, 0))} events, {60000000 / tempo:.0f} BPM'
        if kind == 'TMD':
            table = tmd.objects(data)
            return f'{len(table)} objects, {sum(t[5] for t in table)} primitives'
        if kind == 'Save icon':
            from formats.images.save_icon import title
            return title(data)
    except (FormatError, struct.error, ValueError):
        pass
    return ''


# --- table layouts ----------------------------------------------------------

def lvl(data):
    if data[8:12] != b'Indx' or len(data) < 0x20:
        return None
    count = struct.unpack_from('<I', data, 16)[0]
    out = []
    for n in range(min(count, (len(data) - 0x20) // 24)):
        name, sector, _sectors, size = struct.unpack_from('<12s3I', data, 0x20 + n * 24)
        name = name.split(b'\0')[0].decode('ascii', 'replace')
        if not name or sector * SECTOR + size > len(data):
            break
        out.append((name, sector * SECTOR, size))
    return out or None


def raq(data):
    if not bytes(data[8:26]).startswith(b'Copyright by TENKY'):
        return None
    sectors, count = struct.unpack_from('<II', data)
    out = []
    for n in range(min(count, (sectors * SECTOR - 0x20) // 32)):
        name, _part, sector, length, _stamp, _zero = struct.unpack_from('<12s5I', data, 0x20 + n * 32)
        name = name.split(b'\0')[0].decode('ascii', 'replace')
        start = (sectors + sector) * SECTOR
        if not name or start + length * SECTOR > len(data):
            continue
        out.append((name, start, length * SECTOR))
    return out or None


def counted(data):
    if len(data) < 16:
        return None
    count, total = struct.unpack_from('<II', data)
    if not 0 < count <= 8192 or total != len(data) or 8 + count * 8 > len(data):
        return None
    out = []
    for n in range(count):
        offset, size = struct.unpack_from('<II', data, 8 + n * 8)
        if offset == 0xFFFFFFFF or not size:
            continue
        if offset + size > len(data):
            return None
        out.append((f'{n:04d}', offset, size))
    return out or None


def pairs(data):
    if len(data) < 16:
        return None
    table = struct.unpack_from('<I', data)[0]
    if table < 8 or table % 8 or table > min(len(data), 0x10000):
        return None
    out, last = [], table
    for n in range(table // 8):
        offset, size = struct.unpack_from('<II', data, n * 8)
        if not size:
            continue
        # Entries follow one another, directly or from the next sector.
        if offset not in (last, -(-last // SECTOR) * SECTOR) or offset + size > len(data):
            return None
        out.append((f'{n:04d}', offset, size))
        last = offset + size
    return out if len(out) >= 2 else None


def sectors(data):
    out, last = [], 0
    for n in range(0, min(len(data), SECTOR) - 8, 8):
        sector, size = struct.unpack_from('<II', data, n)
        if sector * SECTOR < last or not size or sector * SECTOR + size > len(data):
            break
        out.append((f'{n // 8:04d}', sector * SECTOR, size))
        last = sector * SECTOR + size
    # The table has to fit before the first entry and be more than chance.
    return out if len(out) >= 4 and out[0][1] >= (len(out) + 1) * 8 else None


def offsets(data):
    if len(data) < 12:
        return None
    table = struct.unpack_from('<I', data)[0]
    if table < 8 or table % 4 or table > min(len(data), 0x4000):
        return None
    starts = struct.unpack_from(f'<{table // 4}I', data)
    if list(starts) != sorted(set(starts)) or starts[-1] > len(data):
        return None
    ends = starts[1:] + (len(data),)
    return [(f'{n:04d}', a, b - a) for n, (a, b) in enumerate(zip(starts, ends)) if b > a] if len(starts) > 1 else None


LAYOUTS = (('LVL', lvl), ('RAQ', raq), ('counted', counted), ('pairs', pairs),
           ('sectors', sectors), ('offsets', offsets))


def layout(data):
    """(layout name, [(name, offset, size)]) of an archive, or (None, [])."""
    for name, read in LAYOUTS:
        try:
            found = read(data)
        except struct.error:
            found = None
        if found:
            return name, found
    return None, []


# --- contents ---------------------------------------------------------------

def scan(data, prefix='', base=0, limit=4096):
    """Stock resources found by their headers anywhere in `data`."""
    view, found = bytes(data), []
    for picture in tim.find(view, limit):
        found.append(Item(f'{prefix}+{base + picture.offset:06X}', 'TIM', base + picture.offset, picture.size,
                          view[picture.offset:picture.offset + picture.size]))
    at = view.find(sfx.MAGIC)
    while at >= 0 and len(found) < limit:
        length = vab.header_size(view, at)
        if length:
            # The waveforms follow the header, at once or after padding.
            body, wanted = vab.find_body(view, at), vab.body_size(view, at)
            if body >= 0:
                found.append(Item(f'{prefix}+{base + at:06X}', 'VAB', base + at, body + wanted - at,
                                  view[at:at + length] + view[body:body + wanted]))
            else:
                found.append(Item(f'{prefix}+{base + at:06X}', 'VAB header', base + at, length,
                                  view[at:at + length]))
        at = view.find(sfx.MAGIC, at + max(4, length))
    at = view.find(seq.MAGIC)
    while at >= 0 and len(found) < limit:
        music, size = sequence(view, at)
        if music:
            found.append(Item(f'{prefix}+{base + at:06X}', 'SEQ', base + at, size, music))
        at = view.find(seq.MAGIC, at + 4)
    at = view.find(b'\x41\0\0\0')
    while at >= 0 and len(found) < limit:
        if at % 4 == 0 and tmd.objects(view, at) is not None:
            size = tmd.size(view, at)
            if size > 12 + tmd.RECORD:
                found.append(Item(f'{prefix}+{base + at:06X}', 'TMD', base + at, size, view[at:at + size]))
                at += size - 4
        at = view.find(b'\x41\0\0\0', at + 4)
    found.sort(key=lambda item: item.offset)
    return found


def contents(data, limit=4096):
    """(layout name or None, [Item]) for a file.

    The file is searched for stock resources once. Where a table layout is
    recognised its entries name what was found inside them, an entry that
    holds several is listed as each of them, and one that holds none is
    unpacked if it is LZSS and otherwise listed as data. Anything found
    outside every entry is listed by its offset."""
    name, entries = layout(data)
    view = bytes(data)
    found = scan(view, limit=limit)
    if not entries:
        return None, found
    items, at, known = [], 0, False
    bodies = [(item.offset, item.offset + item.size, item.name) for item in found if item.kind == 'VAB']
    for label, offset, size in sorted(entries, key=lambda entry: entry[1]):
        while at < len(found) and found[at].offset < offset:
            items.append(found[at])         # between entries
            at += 1
        inside = []
        while at < len(found) and found[at].offset < offset + size:
            inside.append(found[at])
            at += 1
        if len(inside) == 1 and inside[0].offset == offset:
            inside[0].name = label
        for item in inside:
            if item.name.startswith('+'):
                item.name = f'{label} +{item.offset - offset:06X}'
        if inside:
            items.extend(inside)
            known = True
            continue
        raw, kind, packed, loader = view[offset:offset + size], 'Data', '', None
        if raw[:4] == bpe.MAGIC:
            # Unpacked in full only when it is opened, or now if something
            # else in the archive may need it: a bank's header or music.
            kind, packed, known = by_magic(bpe.expand(raw, stop=16)), 'LZSD', True
            if kind in ('TIM', 'TMD', 'Data'):
                loader, raw = (lambda packed=raw: bpe.expand(packed)), b''
            else:
                raw = bpe.expand(raw)
                kind = sniff(raw)
        elif name == 'pairs' and size < 1 << 20 and looks_packed(raw):
            unpacked = lzss.decompress(raw)
            if sniff(unpacked) != 'Data':
                raw, kind, packed, known = unpacked, sniff(unpacked), 'LZSS', True
        if kind == 'Data' and loader is None:
            bare = tim.wrap(raw)
            if bare:
                raw, kind, known = bare, 'TIM', True
        note = ''
        if kind == 'Data':
            # The waveforms of a bank whose header is the entry before.
            owner = next((who for start, end, who in bodies if start < offset and offset + size <= end + SECTOR), '')
            if owner:
                kind, note = 'VAB body', f'Waveforms of {owner}'
        items.append(Item(label, kind, offset, size, raw, note, packed=packed, loader=loader))
    items.extend(found[at:])
    # A table read out of bytes that are not one names nothing stock; the
    # search alone is then the better answer.
    if not known and name in ('pairs', 'sectors', 'offsets'):
        return None, found
    pair_banks(items)
    for item in items:
        if item.loader is None:
            item.note = item.note or describe(item.kind, item.data)
    return name, items[:limit]


def looks_packed(raw):
    """Whether the start of an entry unpacks to a stock header."""
    try:
        head = lzss.decompress(raw[:64], stop=12)
    except (FormatError, IndexError):
        return False
    return head[:4] in (b'\x10\0\0\0', b'\x41\0\0\0', sfx.MAGIC, seq.MAGIC) or head[:2] == b'SC'


def pair_banks(items):
    """Join each bare VAB header with its body. Archives keep the two as
    separate entries, the way the .VH and .VB files they came from sat in
    a folder: under the same name where entries are named, and one after
    the other where they are not."""
    named = {item.name.upper(): item for item in items if item.kind == 'Data'}
    for n, item in enumerate(items):
        if item.kind != 'VAB header':
            continue
        sizes = vab.waveform_sizes(item.data)
        stem = item.name.rsplit('.', 1)[0].upper()
        candidates = [named.get(stem + '.VB')] + [later for later in items[n + 1:n + 2] if later.kind == 'Data']
        for body in candidates:
            if body is not None and len(body.data) >= sum(sizes) and vab.is_body(body.data, sizes):
                item.kind = 'VAB'
                item.data = item.data[:vab.header_size(item.data)] + body.data[:sum(sizes)]
                item.note = ''
                body.kind, body.note = 'VAB body', f'Waveforms of {item.name}'
                break
