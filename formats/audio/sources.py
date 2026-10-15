"""What the sound viewer can play, behind one interface.

A source is something with rows: the waveforms of a bank, the clips of an
XA stream, the programs a sequence calls for. The viewer lists its rows,
asks it for the details of one and for the sound to play, and does not need
to know which kind it has. Rendering runs on a worker thread, so a source
keeps only bytes and paths and touches no widget.
"""
from dataclasses import dataclass
from pathlib import Path
import struct
from disc.reader import FormatError
from formats.audio import seq, sfx, vab, wvd, xa
from game.labels import content_key


@dataclass
class Row:
    cells: tuple            # text for each column after the number
    preview: object = None  # () -> samples for a small waveform, or None
    key: str = ''           # what a name given to this row is stored against
    kind: str = ''          # label kind


class Source:
    name = ''               # as listed among the other sources
    summary = ''            # one line about it
    caption = 'Entries'     # what its rows are
    headers = ()
    numbered = True         # rows get a number column
    rate_adjustable = False     # the viewer's preview rate applies
    autoplay = False        # choosing a row plays it
    whole = False           # plays as one piece whichever row is chosen

    def rows(self):
        return []

    def details(self, row):
        """[(name, value)] for the row, or for the source if row is None."""
        return []

    def text(self):
        """Anything long worth reading beside the details."""
        return ''

    def title(self, row):
        return self.name

    def play(self, row, rate):
        """WAV bytes of the row (of everything, for a `whole` source)."""
        raise NotImplementedError

    def midi(self):
        return None


def clock(seconds):
    return f'{int(seconds // 60)}:{seconds % 60:04.1f}'


# --- sample banks -----------------------------------------------------------

class BankSource(Source):
    """The waveforms of one VAB, in the header-blank-body form."""
    caption = 'Waveforms'
    headers = ('Waveform', 'Preview', 'Samples', 'Bytes', 'Loop', 'Used by')
    rate_adjustable = True
    autoplay = True

    def __init__(self, name, bank, labels=None):
        self.name, self.bank, self.labels = name, bank, labels
        self.samples = sfx.samples(bank)
        try:
            self.programs = seq.instruments(bank, 0)
        except (struct.error, IndexError):
            self.programs = {}
        self.users = {}
        for program, (_volume, _pan, tones) in self.programs.items():
            for tone in tones:
                self.users.setdefault(tone.vag, []).append((program, tone))
        programs, tones, waves = vab.summary(bank)
        self.summary = f'{len(self.samples)} waveforms, {programs} programs, {tones} tones'

    def raw(self, row):
        _bank, _number, offset, size = self.samples[row]
        return self.bank[offset:offset + size]

    def default_name(self, row):
        return f'Waveform {self.samples[row][1]:03d}'

    def pitch_choices(self, row):
        """Audition the VAB's own tone mappings, preserving alternate uses.

        A single-key tone supplies a definite key. A ranged instrument has
        no single game pitch, so audition its centre within its key range.
        """
        from formats.audio.pitch import sample_rate
        number = self.samples[row][1]
        choices = []
        for program, tone in self.users.get(number, ()):
            note = tone.low if tone.low == tone.high else max(tone.low, min(tone.high, tone.center))
            rate = sample_rate(note, tone.center, tone.shift)
            use = 'fixed key' if tone.low == tone.high else f'audition, keys {tone.low}-{tone.high}'
            choices.append((f'P{program}, key {note} ({use})', rate))
        return choices + [('SPU unity (unpitched sample)', 44100)]

    def rows(self):
        out = []
        for row, (_bank, number, offset, size) in enumerate(self.samples):
            key = content_key(self.raw(row))
            name = (self.labels.label_for(key) if self.labels else None) or self.default_name(row)
            users = sorted({program for program, _ in self.users.get(number, ())})
            out.append(Row((name, '', f'{size // sfx.BLOCK * sfx.BLOCK_SAMPLES:,}', f'{size:,}',
                            'Loop' if sfx.loops(self.bank, offset, size) else '',
                            ', '.join(f'P{p}' for p in users)),
                           lambda offset=offset, size=size: sfx.decode(self.bank, offset, size), key, 'SFX'))
        return out

    def details(self, row):
        if row is None:
            return [('Bank', self.name), ('Contents', self.summary)]
        _bank, number, offset, size = self.samples[row]
        out = [('Waveform', str(number)), ('Offset in bank', f'0x{offset:06X}'), ('Bytes', f'{size:,}'),
               ('Blocks', str(size // sfx.BLOCK)), ('Samples', f'{size // sfx.BLOCK * sfx.BLOCK_SAMPLES:,}'),
               ('Loops', 'Yes' if sfx.loops(self.bank, offset, size) else 'No')]
        for program, tone in self.users.get(number, ()):
            out.append((f'Program {program}', f'keys {tone.low} to {tone.high}, centre {tone.center}, '
                                              f'volume {tone.volume}, pan {tone.pan}'))
        return out

    def title(self, row):
        return f'{self.name} / {self.default_name(row)}'

    def play(self, row, rate):
        _bank, _number, offset, size = self.samples[row]
        values = sfx.decode(self.bank, offset, size)
        return xa.wav_bytes(values, rate)


def wvd_sources(data, labels=None, name='Bank'):
    """One source per bank of a WVD file."""
    return [BankSource(f'{name} {i}', bank, labels) for i, bank in enumerate(wvd.banks(data))]


# --- sequences --------------------------------------------------------------

class SequenceSource(Source):
    """A SEQ played on one candidate bank; its rows are the programs the
    music asks for, with what the bank has for each."""
    caption = 'Programs the music uses'
    headers = ('Program', 'Preview', 'Notes', 'Keys', 'In this bank')
    numbered = False
    whole = True

    def __init__(self, title, data, bank_name, bank, labels=None):
        self.title_text, self.data, self.name, self.bank, self.labels = title, data, bank_name, bank, labels
        self.notes, self.length = seq.perform(data, 0)
        self.used = {}
        for _start, _end, key, _velocity, state in self.notes:
            self.used.setdefault(state['program'], []).append(key)
        try:
            self.programs = seq.instruments(bank, 0) if bank else {}
        except (struct.error, IndexError):
            self.programs = {}
        self.covered = sum(any(t.low <= key <= t.high for t in self.programs.get(state['program'], (0, 0, ()))[2])
                           for _s, _e, key, _v, state in self.notes)
        self.summary = (f'{self.covered} of {len(self.notes)} notes' if bank else 'no bank')

    def rows(self):
        out = []
        for program, keys in sorted(self.used.items()):
            tones = self.programs.get(program, (0, 0, ()))[2]
            reach = sum(any(t.low <= key <= t.high for t in tones) for key in keys)
            have = 'not in this bank' if not tones else f'{len(tones)} tone{"s" if len(tones) != 1 else ""}' + (
                '' if reach == len(keys) else f', {reach} of {len(keys)} notes in range')
            out.append(Row((f'Program {program}', '', str(len(keys)), f'{min(keys)} to {max(keys)}', have)))
        return out

    def details(self, row):
        resolution, tempo = seq.header(self.data, 0)
        return [('Sequence', self.title_text), ('Length', clock(self.length)),
                ('Tempo', f'{60000000 / tempo:.1f} BPM'), ('Ticks per quarter', str(resolution)),
                ('Notes', f'{len(self.notes):,}'), ('Events', f'{len(seq.events(self.data, 0)):,}'),
                ('Instrument bank', self.name or 'none'),
                ('Notes it can sound', f'{self.covered:,} of {len(self.notes):,}')]

    def text(self):
        rows = ['Delta | Status | Data 1 | Data 2']
        rows += [f'{d:6d} | {s:02X} | {a:6d} | {b:6d}' for d, s, a, b in seq.events(self.data, 0)]
        return '\n'.join(rows)

    def title(self, row):
        return f'{self.title_text} on {self.name}' if self.name else self.title_text

    def play(self, row, rate):
        import numpy as np
        if not self.bank:
            raise ValueError('No instrument bank was found for this sequence. Export MIDI is still available.')
        audio, _used = seq.render(self.data, 0, self.bank, 0)
        if not len(audio) or not np.any(audio):
            raise ValueError('This bank has none of the instruments the sequence plays. Select another bank.')
        return xa.wav_bytes_raw(seq.pcm(audio), seq.RATE, 2)

    def midi(self):
        return wvd.midi(self.data)


def disc_banks(project):
    """[(name, bank)] for every sound bank stored as a file of its own: WVD
    files, and VAB headers with the .VB beside them. Found once per disc."""
    cached = project.__dict__.get('_disc_banks')
    if cached is not None:
        return cached
    found, entries = [], project.disc.entries
    prefix = project.catalog.executable.rpartition('/')[0].split('/')[0] + '/' if project.catalog and '/' in project.catalog.executable else ''
    if prefix.upper() not in ('TOMBA/', 'TOMBI/'):
        prefix = ''
    for entry in project.disc.files:
        upper = entry.path.upper()
        if prefix and not upper.startswith(prefix.upper()):
            continue
        try:
            if upper.endswith('.WVD'):
                banks = wvd.banks(project.payload(entry))
                found += [(f'{entry.path} | Bank {i}' if len(banks) > 1 else entry.path, bank)
                          for i, bank in enumerate(banks)]
            elif upper.endswith(('.VH', '.VA')) and entry.size < 1 << 20:
                body = entries.get(upper.rsplit('.', 1)[0] + '.VB')
                head = project.disc.read(entry)
                if body is not None and vab.header_size(head):
                    found.append((entry.path, vab.canonical(head, project.disc.read(body))))
            elif upper.endswith('.VAB') and entry.size < 8 << 20:
                bank = vab.whole(project.disc.read(entry))
                if bank:
                    found.append((entry.path, bank[0]))
        except (FormatError, ValueError, KeyError, struct.error):
            continue
    project.__dict__['_disc_banks'] = found
    return found


def resident_banks(project, path, group):
    """Banks assigned by this section's actual sound load records."""
    from formats.level.scene import loaded_resources
    found = {}
    for (kind, slot), asset in loaded_resources(project, path, group).items():
        if kind == 'VH' and asset.source:
            body = project.disc.entries.get(asset.source.path.rsplit('.', 1)[0] + '.VB')
            if body:
                try:
                    found[slot] = (asset.source.path, vab.canonical(project.asset_data(asset), project.payload(body)))
                except (ValueError, FormatError, struct.error):
                    pass
            continue
        if kind != 'WVD':
            continue
        try:
            for index, bank in enumerate(wvd.banks(project.asset_data(asset))):
                found[slot + index] = (f'{asset.source.path} | Bank {index}', bank)
        except (ValueError, FormatError, struct.error, IndexError):
            continue
    return found


def sequence_sources(data, title, banks, near='', labels=None, limit=64, embedded_area=None, resident=None, embedded_bank=1):
    """A source per bank that can play the sequence, best first.

    Banks are ranked by how many of the music's notes they have a tone for,
    then by being in the sequence's own folder, then by the area number in
    the names Tomba gives its files (S_AR010.SEQ goes with SND0010.WVD)."""
    folder, stem = str(Path(near).parent).replace('\\', '/'), Path(near).stem.upper()
    if embedded_area is not None:
        if resident and embedded_bank in resident:
            name, bank = resident[embedded_bank]
            source = SequenceSource(title, data, name, bank, labels)
            source.bank_reason = f'Game music player: VAB slot {embedded_bank} from this section\'s sound load records.'
            return [source]
        # playJingle opens embedded SEQ slots on VAB_IDS[1] (1F8003AC).
        # In areas that load a two-bank WVD this is its second bank.
        resident = f'SND0{embedded_area:02d}0'
        match = next(((name, bank) for name, bank in banks
                      if Path(name.split(' | ')[0]).stem.upper() == resident
                      and name.endswith(' | Bank 1')), None)
        if match:
            source = SequenceSource(title, data, match[0], match[1], labels)
            source.bank_reason = 'Jingle player: VAB slot 1 from the area sound set (initial area variant).'
            return [source]
    # The retail load lists pair each standalone song with bank 0 of its
    # WVD. A second bank is SFX, not an alternative music instrument set.
    special = {'S_TITLE': 'SND_TTL', 'S_SYS00': 'SND_SYS', 'S_END': 'SND_END',
               'S_AR010': 'SND001_', 'S_AR010X': 'SND001_X',
               'S_AR100': 'SND010_', 'S_AR100X': 'SND010_X',
               'S_AR040X': 'SND004_X', 'S_AR1802': 'SND0182'}
    expected = special.get(stem)
    if expected is None and stem.startswith('S_AR'):
        expected = 'SND0' + stem[4:]
    if expected:
        matched = [(name, bank) for name, bank in banks
                   if Path(name.split(' | ')[0]).stem.upper() == expected
                   and (' | Bank ' not in name or name.endswith(' | Bank 0'))]
        if matched:
            source = SequenceSource(title, data, matched[0][0], matched[0][1], labels)
            source.bank_reason = 'Game load-list pairing: music bank 0.'
            return [source]
    area = ''.join(c for c in stem if c.isdigit())[:3]
    ranked = []
    for order, (name, bank) in enumerate(banks):
        source = SequenceSource(title, data, name, bank, labels)
        same_folder = str(Path(name.split(' | ')[0]).parent).replace('\\', '/') == folder
        same_area = bool(area) and area in Path(name.split(' | ')[0]).stem
        ranked.append(((-source.covered, not same_folder, not same_area, order), source))
    ranked.sort(key=lambda pair: pair[0])
    sources = [source for _, source in ranked if source.covered][:limit]
    for source in sources:
        source.bank_reason = 'Instrument compatibility estimate; the game bank has not been resolved for this embedded sequence.'
    return sources or [SequenceSource(title, data, '', b'', labels)]


# --- streamed audio ---------------------------------------------------------

class XaSource(Source):
    """The audio streams interleaved through one file of Form 2 sectors.

    A channel is every n-th sector. Where a channel skips a turn, or a
    sector carries the end-of-record flag, one clip ends and the next
    begins; voice files are cut this way."""
    caption = 'Streams'
    headers = ('Stream', 'Format', 'Rate', 'Length', 'Sectors')

    def __init__(self, name, image, lba, sectors):
        self.name, self.image, self.lba = name, str(image), lba
        self.clips = []         # [(file, channel, part, [sector index], coding)]
        channels = {}
        with open(self.image, 'rb') as handle:
            for index in range(sectors):
                handle.seek((lba + index) * xa.SECTOR + xa.SUBHEADER)
                sub = handle.read(4)
                if len(sub) < 4:
                    break
                if sub[2] & 0x24 == 0x24:
                    channels.setdefault((sub[0], sub[1]), []).append((index, sub[2], sub[3]))
        for (number, channel), found in sorted(channels.items()):
            steps = [b[0] - a[0] for a, b in zip(found, found[1:])]
            stride = max(set(steps), key=steps.count) if steps else 0
            part, run = 0, []
            for n, (index, submode, coding) in enumerate(found):
                run.append(index)
                last = n + 1 == len(found)
                if last or submode & 0x81 or found[n + 1][0] - index != stride:
                    self.clips.append((number, channel, part, run, found[n - len(run) + 1][2]))
                    part, run = part + 1, []
        self.parts = {}
        for number, channel, part, _run, _coding in self.clips:
            self.parts[number, channel] = max(self.parts.get((number, channel), 0), part + 1)
        self.summary = f'{len(channels)} channel{"s" if len(channels) != 1 else ""}, {len(self.clips)} clips'

    def describe(self, row):
        number, channel, part, run, coding = self.clips[row]
        speakers, rate, bits = xa.coding(coding)
        seconds = len(run) * xa.SAMPLES_PER_SECTOR / (rate * speakers)
        name = f'Channel {channel}' + (f', clip {part + 1}' if self.parts[number, channel] > 1 else '')
        return name, speakers, rate, bits, seconds

    def rows(self):
        out = []
        for row, clip in enumerate(self.clips):
            name, speakers, rate, bits, seconds = self.describe(row)
            out.append(Row((name, 'Stereo' if speakers == 2 else 'Mono', f'{rate / 1000:g} kHz',
                            clock(seconds), str(len(clip[3])))))
        return out

    def details(self, row):
        if row is None:
            return [('File', self.name), ('Contents', self.summary)]
        number, channel, _part, run, coding = self.clips[row]
        name, speakers, rate, bits, seconds = self.describe(row)
        return [('Stream', name), ('File number', str(number)), ('Channel', str(channel)),
                ('Format', f'{"Stereo" if speakers == 2 else "Mono"}, {rate:,} Hz, {bits}-bit ADPCM'),
                ('Length', clock(seconds)), ('Sectors', f'{len(run):,}'),
                ('First sector', f'{run[0]:,} of the file'), ('Coding byte', f'0x{coding:02X}')]

    def title(self, row):
        return f'{Path(self.name).name} / {self.describe(row)[0]}'

    def play(self, row, rate):
        with open(self.image, 'rb') as handle:
            samples, rate, speakers = xa.decode_channel(handle, self.lba, self.clips[row][3])
        if not samples:
            raise ValueError('This stream is in a coding the decoder does not read.')
        return xa.wav_bytes(samples, rate, speakers)


class PcmSource(Source):
    """A file of CD audio sectors: 16-bit stereo at 44.1 kHz, as it is."""
    caption = 'Track'
    headers = ('Track', 'Format', 'Length')
    numbered = False

    def __init__(self, name, image, lba, sectors):
        self.name, self.image, self.lba, self.sectors = name, str(image), lba, sectors
        self.seconds = sectors * xa.SECTOR / (44100 * 4)
        self.summary = f'CD audio, {clock(self.seconds)}'

    def rows(self):
        return [Row((Path(self.name).name, 'Stereo 16-bit, 44.1 kHz', clock(self.seconds)))]

    def details(self, row):
        return [('File', self.name), ('Format', 'CD audio: 16-bit stereo PCM, 44,100 Hz'),
                ('Length', clock(self.seconds)), ('Sectors', f'{self.sectors:,}')]

    def play(self, row, rate):
        with open(self.image, 'rb') as handle:
            handle.seek(self.lba * xa.SECTOR)
            return xa.wav_bytes_raw(handle.read(self.sectors * xa.SECTOR), 44100, 2)


SYNC = b'\x00' + b'\xff' * 10 + b'\x00'


def stream_kind(disc, entry, probe=256):
    """How a file's sectors are used: 'movie' (MDEC video, with or without
    sound), 'xa' (sound alone), 'cdda' (CD audio) or ''. Only an image of
    whole 2352-byte sectors can say; any other gives ''.

    A sample of the sectors is read. Streams are padded with empty sectors
    so that each channel keeps its turn, sometimes more of them than there
    is sound; those say nothing either way."""
    cache = disc.__dict__.setdefault('_stream_kinds', {})
    if entry.path not in cache:
        cache[entry.path] = probe_stream(disc, entry, probe)
    return cache[entry.path]


def probe_stream(disc, entry, probe):
    if disc.stride != xa.SECTOR or entry.size < 2048:
        return ''
    count = (entry.size + 2047) // 2048
    step = max(1, count // probe)
    audio = video = data = bare = 0
    with open(disc.path, 'rb') as handle:
        for index in range(0, count, step):
            handle.seek((disc.start + entry.lba + index) * xa.SECTOR)
            sector = handle.read(60)
            if len(sector) < 60:
                break
            if sector[:12] != SYNC:
                bare += 1
            elif sector[18] & 0x24 == 0x24:
                audio += 1
            elif sector[24:28] == b'\x60\x01\x01\x80':
                video += 1
            elif sector[18] & 0x08:
                data += 1
    if bare and not audio + video + data:
        return 'cdda'
    if video:
        return 'movie'
    return 'xa' if audio > data else ''
