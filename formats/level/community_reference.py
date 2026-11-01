"""Read-only community research snapshot; claims retain their source confidence."""
from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def snapshot():
    return json.loads(Path(__file__).with_name('civ_towns_reference.json').read_text(encoding='utf8'))


def palette_notes():
    """Key claims by all sixteen words, so changed ROM rows never inherit a label."""
    notes = {}
    for cell_row, row in enumerate(snapshot()['sheets']['Palettes'][1:], 2):
        if row[20]:
            words = tuple(int(v, 16) for v in row[26].split())
            claim = f'{row[20]} [{row[21]}; community sheet Palettes!U{cell_row}:W{cell_row}]'
            notes.setdefault(words, []).append(claim)
    return {words: ' / '.join(dict.fromkeys(claims)) for words, claims in notes.items()}


def annotate_palettes(palettes):
    notes = palette_notes()
    return [(label + (' · ' + notes[tuple(map(int, words))] if tuple(map(int, words)) in notes else ''), words)
            for label, words in palettes]


def compare_palette(project, row):
    """Return exact-file comparison and native words without changing either source."""
    import re
    import struct
    area = int(re.search(r'AREA(\d+)', row[0]).group(1))
    path = f'AREA{area:02d}/{row[1]}.GAM'
    entry = project.disc.entries.get(path)
    if entry is None:
        return 'File absent in opened disc', ''
    data = project.payload(entry)
    offset = int(row[2]) * 32
    if offset + 32 > len(data):
        return 'Row outside opened file', ''
    words = struct.unpack_from('<16H', data, offset)
    expected = tuple(int(v, 16) for v in row[26].split())
    return ('Exact 16-word match' if words == expected else 'DIFFERS from opened disc',
            ' '.join(f'{v:04X}' for v in words))
