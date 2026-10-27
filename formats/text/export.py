"""Gather the text of a disc and write it out.

Text is kept in WFM banks: a font of glyph bitmaps and a list of entries,
each a run of glyph numbers and control words. A bank is one of a load
group's resources, or a file of its own on the disc. `collect` reads every
bank a disc has, once each, with the area and load group it belongs to;
the writers turn what it returns into one document or a folder of them.

An entry is written three ways. The script keeps every control word as a
tag on a line of its own, which is what is needed to put a translation back.
The plain text keeps only what is read on screen: a line break where the
game breaks the line and an empty line where it clears the box. The tokens
are the raw words, for tools.
"""
import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from formats.archive.ldar import table_name
from game.areas import language_name
from formats.text.wfm import Wfm, MAGICS, CONTROLS, EARLY_CONTROLS, corner, composed
from disc.reader import FormatError

FORMATS = {
    'json': ('JSON', '.json'),
    'script': ('Script with control codes', '.txt'),
    'plain': ('Plain text', '.txt'),
    'csv': ('CSV table', '.csv'),
}
LAYOUTS = {
    'one': 'One file',
    'area': 'One file for each area',
    'bank': 'One file for each text bank',
}
NAMES = {**EARLY_CONTROLS, **CONTROLS}


def plain(dialogue, unknown='[g{:03X}]'):
    """What an entry reads as on screen. `unknown` formats the number of a
    glyph no character is known for."""
    if getattr(dialogue, 'layout', None):
        # An event title: its spaces and line breaks are in the overlays.
        from formats.text.titles import text
        return composed(text(dialogue, dialogue.layout, lambda word: dialogue.letter(word, unknown)))
    out = []
    for word, _ in dialogue.tokens:
        names = getattr(dialogue, 'controls', None) or NAMES
        name = names.get(word, ('', 0))[0]
        if name == 'NEWLINE':
            out.append('\n')
        elif name == 'CLEAR':
            out.append('\n\n')
        elif word < 0xFF00 and not corner(word):
            number = word & 0xFFF
            character = dialogue.characters[number] if number < len(dialogue.characters) else None
            out.append(character if character is not None else unknown.format(number))
    return composed(''.join(out)).strip('\n')


def tokens(dialogue):
    """The raw words of an entry: glyph numbers, and control names with
    their arguments."""
    out = []
    for word, args in dialogue.tokens:
        if word >= 0xFF00:
            names = getattr(dialogue, 'controls', None) or NAMES
            out.append({'control': names.get(word, (f'UNKNOWN_{word:04X}', 0))[0], 'word': f'{word:04X}',
                        'arguments': [f'{a:04X}' for a in args]})
        else:
            number = word & 0xFFF
            item = {'glyph': number,
                    'character': dialogue.characters[number] if number < len(dialogue.characters) else None}
            if word & 0xF000:
                item['flags'] = f'{word & 0xF000:04X}'
            out.append(item)
    return out


@dataclass
class Bank:
    """One WFM bank and where it is."""
    name: str               # the resource or file it is, as the disc tree lists it
    source: str             # the disc file its bytes are in
    offset: int             # and where in that file's decoded bytes
    table: str = ''         # the load table that names it, if one does
    group: int = -1
    area: int = -1
    language: int | None = None
    version: str = ''
    wfm: object = field(default=None, repr=False)

    @property
    def unknown(self):
        """Glyphs the text uses that no character is known for."""
        used = {word & 0xFFF for d in self.wfm.dialogues for word, _ in d.tokens if word < 0xFF00 and not corner(word)}
        return sum(1 for number in used if number < len(self.wfm.characters) and self.wfm.characters[number] is None)

    @property
    def place(self):
        if self.area >= 0:
            return f'AREA{self.area:02d}' + ('' if self.language is None else ' ' + language_name(self.language))
        if self.table:
            return 'SYSTEM' + ('' if self.language is None else ' ' + language_name(self.language))
        return 'files'


def collect(project, area=None, language=None, progress=None):
    """Every text bank on the disc, each once: [Bank]. `area` keeps the
    banks of one area and `language` those of one language of a disc that
    has several. `progress(done, total)` is called as banks are read."""
    wanted, seen = [], set()
    for path, groups in sorted(project.ldars.items()):
        tongue, number = table_name(path)
        if (area is not None and number != area) or (language is not None and tongue not in (None, language)):
            continue
        for group in groups:
            for asset in group.assets:
                if asset.kind != 'WFM' or asset.source is None:
                    continue
                key = (asset.source.path, asset.offset)
                if key in seen:
                    continue
                seen.add(key)
                wanted.append((asset, path, group.index, number, tongue))
    banks = []
    for done, (asset, path, group, number, tongue) in enumerate(wanted):
        if progress:
            progress(done, len(wanted))
        try:
            data = project.asset_data(asset)
            if data.startswith(b'PS-X EXE'):
                from formats.text.prepre8 import bank
                wfm = bank(project)
                if wfm is None:
                    continue
            else:
                wfm = Wfm(data)
        except (FormatError, ValueError):
            continue
        from formats.text.titles import attach
        if wfm.version != b'PP8':
            attach(wfm, project, tongue)
        banks.append(Bank(f'WFM {asset.code:04X}', asset.source.path, asset.offset, path, group, number, tongue,
                          wfm.version.decode('ascii', 'replace'), wfm))
    if area is None:
        # Banks that are files of their own and that no load table names.
        # Include assets in excluded languages too: a language filter must
        # not reintroduce those banks as supposedly standalone files.
        named = {a.source.path for groups in project.ldars.values() for group in groups
                 for a in group.assets if a.kind == 'WFM' and a.source is not None}
        for entry in project.disc.files:
            if entry.path in named or not entry.path.upper().endswith('.WFM'):
                continue
            from formats.text.titles import language_of
            tongue = language_of(entry.path)
            if language is not None and tongue not in (None, language):
                continue
            try:
                data = project.disc.read(entry)
                if bytes(data[:4]) not in MAGICS:
                    continue
                wfm = Wfm(data)
            except (FormatError, ValueError, OSError):
                continue
            from formats.text.titles import attach, language_of
            attach(wfm, project, language_of(entry.path))
            banks.append(Bank(Path(entry.path).name, entry.path, 0, language=tongue, version=wfm.version.decode('ascii', 'replace'),
                              wfm=wfm))
    return banks


def entries(bank, controls=True, unknown='[g{:03X}]', raw=False):
    """An entry of a bank as a dictionary, for each of its entries."""
    for index, dialogue in enumerate(bank.wfm.dialogues):
        item = {'index': index, 'offset': f'{dialogue.offset:04X}', 'text': plain(dialogue, unknown)}
        if controls:
            item['script'] = dialogue.script()
        if raw:
            item['tokens'] = tokens(dialogue)
        if dialogue.warning:
            item['warning'] = dialogue.warning
        if getattr(dialogue, 'usage', None):
            item['usage'] = dialogue.usage
        yield item


def describe(bank):
    """What says which bank this is, as a dictionary."""
    out = {'name': bank.name, 'file': bank.source, 'offset': f'{bank.offset:X}', 'format': bank.version,
           'entries': len(bank.wfm.dialogues), 'glyphs': len(bank.wfm.glyphs), 'unknown_glyphs': bank.unknown}
    if bank.table:
        out.update(load_table=bank.table, load_group=bank.group)
    if bank.area >= 0:
        out['area'] = bank.area
    if bank.language is not None:
        out['language'] = language_name(bank.language)
    return out


def render(banks, kind, title='', controls=True, unknown='[g{:03X}]', raw=False):
    """The banks as one document of the given kind ('json', 'script',
    'plain' or 'csv'): the text of the file to write."""
    if kind == 'json':
        return json.dumps({'disc': title, 'banks': [
            {**describe(bank), 'text': list(entries(bank, controls, unknown, raw))} for bank in banks]},
            ensure_ascii=False, indent=1) + '\n'
    if kind == 'csv':
        out = io.StringIO()
        writer = csv.writer(out, lineterminator='\n')
        writer.writerow(['place', 'file', 'offset', 'bank', 'entry', 'entry offset', 'text'] + (['script'] if controls else []))
        for bank in banks:
            for item in entries(bank, controls, unknown):
                writer.writerow([bank.place, bank.source, f'{bank.offset:X}', bank.name, item['index'], item['offset'],
                                 item['text']] + ([item['script']] if controls else []))
        return out.getvalue()
    parts = []
    for bank in banks:
        head = f'{bank.place} | {bank.name} | {bank.source} +{bank.offset:06X} | {len(bank.wfm.dialogues)} entries'
        parts.append('=' * 78 + f'\n{head}\n' + '=' * 78)
        for item in entries(bank, kind == 'script', unknown):
            parts.append(f'[{item["index"]:03d} @ {item["offset"]}]\n' + (item['script'] if kind == 'script' else item['text']))
    return '\n\n'.join(parts) + '\n'


def write(banks, target, kind, layout='one', title='', controls=True, unknown='[g{:03X}]', raw=False):
    """Write the banks out and return the paths written. `target` is the
    file for the 'one' layout and the folder for the others."""
    target = Path(target)
    suffix = FORMATS[kind][1]
    if layout == 'one':
        target.write_text(render(banks, kind, title, controls, unknown, raw), 'utf-8', newline='\n')
        return [target]
    target.mkdir(parents=True, exist_ok=True)
    sets = {}
    for bank in banks:
        if layout == 'area':
            name = bank.place
        else:
            name = f'{bank.place} {Path(bank.source).stem} {bank.offset:06X} {bank.name}'
        sets.setdefault(''.join(c if c.isalnum() or c in ' -_.' else '_' for c in name), []).append(bank)
    written = []
    for name, group in sets.items():
        path = target / (name + suffix)
        path.write_text(render(group, kind, title, controls, unknown, raw), 'utf-8', newline='\n')
        written.append(path)
    return written


def render_translated(banks, translations, model='', kind='json'):
    """Export English alongside originals, including honest partial-job status."""
    from formats.text.translation import translatable, TranslationError
    output = []
    for bank in banks:
        messages = []
        for item in entries(bank, controls=False):
            original = item.pop('text')
            translated = translations.get(original)
            status = 'translated' if translated is not None else 'pending'
            if translated is None:
                try:
                    if not translatable(original):
                        translated, status = original, 'original'
                except TranslationError:
                    status = 'unknown glyphs'
            messages.append({**item, 'original': original, 'translation': translated, 'status': status})
        output.append({**describe(bank), 'text': messages})
    document = dict(model=str(model), target_language='en', banks=output)
    if kind == 'json':
        return json.dumps(document, ensure_ascii=False, indent=1) + '\n'
    parts = [f'English machine translation | Model: {model}']
    for bank in output:
        parts.append(f'\n{bank["name"]} | {bank["file"]} +{bank["offset"]}')
        for item in bank['text']:
            parts.append(f'[{item["index"]:03d} @ {item["offset"]}]\nOriginal:\n{item["original"]}'
                         f'\nEnglish:\n{item["translation"] if item["translation"] is not None else "[" + item["status"] + "]"}')
    return '\n\n'.join(parts) + '\n'
