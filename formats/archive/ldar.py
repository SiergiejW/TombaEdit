"""LDAR load groups, source ranges, and ordered VRAM uploads."""
from dataclasses import dataclass, field
from collections import OrderedDict
import re
import struct
import numpy as np
from disc.reader import FormatError
from formats.archive.gam import decompress


SYSTEM_LDAR = 'SYS/LDSYS.BIN'
TABLE_NAME = re.compile(r'LD(\d?)(?:AR(\d+)|SYS)$')


def table_name(path):
    """(language, area) of a load table's path. SYS/LDAR04.BIN is (None, 4)
    and SYS/LDSYS.BIN (None, -1); the European disc has a set of tables for
    each language, so its SYS/LD2AR04.BIN is (2, 4). (None, -1) for a path
    that is not a load table."""
    found = TABLE_NAME.match(path.split('/')[-1].split('.')[0].upper())
    if found is None:
        return None, -1
    return (int(found[1]) if found[1] else None), (int(found[2]) if found[2] else -1)


def area_number(path):
    """Area a load table belongs to; -1 for a system table."""
    return table_name(path)[1]


def bank_readers(project, path, slot):
    """What reads the SPR bank in a slot by its fixed place in the table of
    loaded banks (1F8002C8 on): ([system load groups whose code does],
    whether the area's own code or the executable does). A bank only a
    system screen reads, such as the menu's, is drawn from that screen's
    pictures and not from an area's."""
    cache = project.__dict__.setdefault('bank_reader_cache', {})
    key = (table_name(path)[0], area_number(path), slot)
    if key in cache:
        return cache[key]
    from game.builds import executable
    program = executable(project, path)
    offset = (0x150 if program and program.build.legacy8 else 0x2C8) + slot * 4

    def reads(code):
        words = np.frombuffer(bytes(code[:len(code) // 4 * 4]), '<u4')
        # read in place (lw), or its address taken to read it through (addiu, ori)
        for i in np.flatnonzero(np.isin(words >> 26, (35, 9, 13)) & ((words & 0xFFFF) == offset)):
            base = int(words[i]) >> 21 & 31
            # the base register was loaded with the scratchpad's address
            if any(int(words[j]) >> 16 == (0x3C00 | base) and int(words[j]) & 0xFFFF == 0x1F80
                   for j in range(max(0, int(i) - 6), int(i))):
                return True
        return False

    def group_reads(group):
        for asset in group.assets:
            if asset.kind == 'INS':
                try:
                    if reads(project.asset_data(asset)):
                        return True
                except FormatError:
                    pass
        return False

    system = project.ldars.get(system_table(path), [])
    screens = [group.index for group in system if group_reads(group)]
    own = any(group_reads(group) for group in project.ldars.get(path, []))
    try:
        entry = project.catalogs[table_name(path)[0]].executable if hasattr(project, 'catalogs') else None
        own = own or (entry is not None and reads(project.disc.read(entry)[0x800:]))
    except (KeyError, FormatError, OSError):
        pass
    cache[key] = (screens, own)
    return cache[key]


def bank_screens(project, path, slot):
    """(system load groups to offer as VRAM for the bank in a slot, the
    position in that list of the one to open with, or None). Screens are
    offered while they are few: a slot that dozens of event scenes read is
    an ordinary area bank. The bank opens on a screen when nothing of the
    area reads it, and on its first system screen."""
    screens, own = bank_readers(project, path, slot)
    if len(screens) > 12:
        return [], None
    if not screens or own or len(screens) > 4:
        return screens, None
    # Later map screens can replace the primary screen's sprite artwork.
    return screens, 0


def system_table(path):
    """Path of the system load table that goes with an area's."""
    language = table_name(path)[0]
    folder = path.rsplit('/', 1)[0] if '/' in path else 'SYS'
    return f'{folder}/LDSYS.BIN' if language is None else f'{folder}/LD{language}SYS.BIN'


def type_name(code):
    if code == 3: return "SPC"
    if code == 8: return "SAP"
    hi = code >> 8
    if hi in (0x8E, 0x8F): return "CLM"
    # Family 9 is a sound bank. Retail loads those by name; earlier builds
    # list them in their load groups.
    return {1: "GRPX", 3: "SPR", 4: "FOUR", 5: "WMD", 6: "WPP", 7: "WHM", 8: "APD",
            9: "WVD", 10: "VH", 11: "SEQ", 13: "WFM", 15: "INS"}.get(hi >> 4, "Unknown")


@dataclass
class Asset:
    ldar: str
    group: int
    record_offset: int
    file_id: int
    code: int
    ram: int
    source: object
    offset: int
    size: int
    rect: tuple | None = None
    continuation: bool = False
    # Set where a build files a resource under another family's code: the
    # kind it really is and the slot later builds give it.
    actual: tuple | None = None

    @property
    def kind(self):
        return self.actual[0] if self.actual else type_name(self.code)

    @property
    def slot(self):
        return self.actual[1] if self.actual else (self.code >> 8) & 15

    @property
    def label(self):
        source = self.source.path.split("/")[-1] if self.source else f"Unresolved {self.file_id:04X}"
        return f"{self.kind} {self.code:04X}  |  {source} +{self.offset:06X}"


@dataclass
class LoadGroup:
    index: int
    offset: int
    assets: list = field(default_factory=list)


def parse_ldar(data, path, catalog):
    # The final pointer array is preceded by a zero word. Walk backwards over
    # KSEG0 pointers, validating their spacing against the parsed load groups.
    tail = len(data)
    pointers = []
    while tail >= 4:
        value = struct.unpack_from("<I", data, tail - 4)[0]
        if not 0x80000000 <= value < 0x80200000:
            break
        pointers.insert(0, value)
        tail -= 4
    if not pointers or tail < 4 or data[tail - 4:tail] != b"\0" * 4:
        raise FormatError(f"{path}: missing LDAR group pointer footer")
    end = tail - 4
    if end % 20:
        raise FormatError(f"{path}: misaligned LDAR records")
    groups = []
    group = LoadGroup(0, 0)
    source = None
    file_id = 0
    offset = 0
    for pos in range(0, end, 20):
        ignored, fid, code, ram, a, b = struct.unpack_from("<IHHIII", data, pos)
        if a == b == 0:
            if fid != 0xFFFF:
                raise FormatError(f"{path}: invalid group terminator at {pos:X}")
            groups.append(group)
            group = LoadGroup(len(groups), pos + 20)
            source, offset = None, 0
            continue
        if fid:
            file_id, source, offset = fid, catalog.links.get(fid), 0
        elif source is None:
            raise FormatError(f"{path}: continuation without source at {pos:X}")
        rect = struct.unpack_from("<4H", data, pos + 12) if b else None
        size = rect[2] * rect[3] * 2 if rect else a
        group.assets.append(Asset(path, group.index, pos, file_id, code, ram, source,
                                  offset, size, rect, not bool(fid)))
        offset += size
    if group.assets or len(pointers) != len(groups):
        raise FormatError(f"{path}: group/footer count mismatch")
    base = pointers[0]
    if any(p - base != g.offset for p, g in zip(pointers, groups)):
        raise FormatError(f"{path}: group pointers do not match record boundaries")
    return groups


class Project:
    """One immutable disc session, with a bounded decompression cache."""
    def __init__(self, path):
        from disc.reader import Disc
        from game.catalog import Catalog
        self.disc = Disc(path)
        self.catalog = None
        self.ldars = {}
        self.warnings = []
        self.cache = OrderedDict()
        self.cache_bytes = 0
        tables = [e for e in self.disc.files if re.search(r'(?:^|/)SYS/LD\d?(?:AR\d+|SYS)\.BIN$', e.path)]
        # A disc with a set of load tables for each language has a program
        # for each too, and every program links its own files.
        self.catalogs = {}
        for language in sorted({table_name(e.path)[0] for e in tables}, key=lambda n: -1 if n is None else n):
            try:
                self.catalogs[language] = Catalog.discover(self.disc, language)
            except FormatError as exc:
                self.warnings.append(str(exc) if language is None else f'Language {language}: {exc}')
        if not tables:
            try:
                self.catalogs[None] = Catalog.discover(self.disc)
            except FormatError as exc:
                self.warnings.append(str(exc))
        self.catalog = next(iter(self.catalogs.values()), None)
        if self.catalog:
            for entry in tables:
                catalog = self.catalogs.get(table_name(entry.path)[0])
                if catalog is None:
                    continue
                try:
                    self.ldars[entry.path] = parse_ldar(self.disc.read(entry), entry.path, catalog)
                except FormatError as exc:
                    self.warnings.append(str(exc))
            if not self.ldars:
                from formats.archive.embedded import embedded_groups
                self.ldars = embedded_groups(self.disc, self.catalog)
        self.reclassify()
        self.by_source = {}
        for groups in self.ldars.values():
            for group in groups:
                for asset in group.assets:
                    if asset.source:
                        self.by_source.setdefault(asset.source.path, []).append(asset)

    def reclassify(self):
        """Early builds keep a town's picture and cell map in placement slots
        (81FF and 85FF on the sampler disc) where later ones use 8FFF and
        8EFF. Placement lists are short and a multiple of 16 bytes, so
        anything else in family 8 is looked at and named for what it holds."""
        for groups in self.ldars.values():
            for group in groups:
                for asset in group.assets:
                    if asset.code >> 12 != 8 or asset.code >> 8 in (0x8E, 0x8F) or asset.source is None:
                        continue
                    if asset.size % 16 == 0 and asset.size < 0x4000:
                        continue
                    try:
                        head = self.asset_data(asset)[:8]
                    except FormatError:
                        continue
                    if head[:4] == b'\x10\0\0\0' and head[4] in (0, 1, 2, 8, 9):
                        asset.actual = ('CLM', 15)
                    else:
                        width, height = struct.unpack_from('<HH', head)
                        if 0 < width <= 512 and 0 < height <= 512 and 4 + width * height <= asset.size:
                            asset.actual = ('CLM', 14)

    def payload(self, entry):
        key = (entry.lba, entry.size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        if entry.size > 64 * 1024 * 1024:
            raise FormatError("File is too large for an asset preview; use raw export")
        data = decompress(self.disc.read(entry))
        while self.cache and self.cache_bytes + len(data) > 96 * 1024 * 1024:
            _, removed = self.cache.popitem(last=False)
            self.cache_bytes -= len(removed)
        self.cache[key] = data
        self.cache_bytes += len(data)
        return data

    def asset_data(self, asset):
        if asset.source is None:
            raise FormatError(f"Unresolved file ID {asset.file_id:04X}")
        data = self.payload(asset.source)
        end = asset.offset + asset.size
        if end > len(data):
            # A code overlay's record can count the cleared memory after it.
            if type_name(asset.code) == 'INS' and asset.offset < len(data):
                return data[asset.offset:]
            raise FormatError(f"{asset.source.path}: LDAR range ends at {end:X}, payload is {len(data):X}")
        return data[asset.offset:end]

    def vram(self, path, group_index, over=None):
        """VRAM as an area's load group leaves it. `over` is a group of the
        system load table to lay on top, as when a menu is opened. Each is
        built once a session and kept between sessions
        (formats.level.disc_cache); callers get a copy to change."""
        from formats.level import disc_cache
        key = (path, group_index, over)
        built = self.__dict__.setdefault('vram_cache', OrderedDict())
        if key not in built:
            vram = disc_cache.load(self, ('vram', path, group_index, over))
            if not isinstance(vram, np.ndarray) or vram.shape != (512, 1024):
                vram = self.build_vram(path, group_index, over)
                disc_cache.save(self, ('vram', path, group_index, over), vram)
            built[key] = vram
            while len(built) > 48:
                built.popitem(last=False)
        built.move_to_end(key)
        return built[key].copy()

    def build_vram(self, path, group_index, over=None):
        vram = np.zeros((512, 1024), dtype=np.uint16)
        groups = self.ldars[path]
        wanted = [(groups[0], 0)] if group_index == 0 else [(groups[0], 0), (groups[group_index], 0)]
        if over is not None:
            # A system screen opened inside an area: its pictures replace
            # the section's and the area's own stay.
            wanted.append((self.ldars[system_table(path)][over], 0))
        # The first group of the system table is loaded at boot and its
        # lower half of VRAM is never replaced: item and effect sprites on
        # pages 20 and 21, with their palettes.
        system = self.ldars.get(system_table(path))
        if system and area_number(path) >= 0:
            wanted.insert(0, (system[0], 256))
        for group, top in wanted:
            for asset in group.assets:
                if not asset.rect or asset.rect[1] < top:
                    continue
                x, y, w, h = asset.rect
                if x + w > 1024 or y + h > 512 or not w or not h:
                    raise FormatError("VRAM upload extends outside 1024 x 512 words")
                pixels = np.frombuffer(self.asset_data(asset), dtype="<u2").reshape(h, w)
                # Section data overwrites the base, including zero/transparent pixels.
                vram[y:y + h, x:x + w] = pixels
        self.effects_picture(vram, [group for group, _ in wanted])
        self.town_palette(vram, [group for group, _ in wanted])
        return vram

    def effects_picture(self, vram, groups):
        """The picture a section loads from the first TIM of WPP slot 3 when
        it starts: the TIM loader (800174FC in the European build) puts its
        pixels at VRAM (32, 0), beside Tomba's picture buffers, and its five
        palette rows at (128, 495). Sections that keep art of their own
        there, as the towns do, do not load it."""
        picture = next((a for g in groups for a in g.assets if a.kind == 'WPP' and a.slot == 3), None)
        if picture is None or vram[0:80, 32:64].any() or vram[495:500, 128:144].any():
            return
        try:
            from formats.sprites.wpp import parse_wpp
            kind, pictures = parse_wpp(self.asset_data(picture))
        except (FormatError, ValueError):
            return
        if kind != 'tim' or not pictures:
            return
        tim = pictures[0]
        if tim.cluts is None or tim.cluts.shape != (5, 16) or tim.indices.shape != (80, 128):
            return
        indices = tim.indices.astype(np.uint16)
        vram[0:80, 32:64] = indices[:, 0::4] | indices[:, 1::4] << 4 | indices[:, 2::4] << 8 | indices[:, 3::4] << 12
        vram[495:500, 128:144] = tim.cluts

    def town_palette(self, vram, groups):
        """The palette a town overlay loads when it starts: INFO and INFO2
        call LoadClut with the 256 colours of the section's CLM 8F picture
        (a TIM; its colours start at byte 14 hex) for VRAM (128, 510)."""
        code = next((a for g in groups for a in g.assets if a.kind == 'INS' and a.source is not None
                     and re.fullmatch(r'I\d?NFO2?\.BIN', a.source.path.rsplit('/', 1)[-1].upper())), None)
        if code is None:
            return
        picture = next((a for g in groups for a in g.assets
                        if a.code >> 8 == 0x8F or getattr(a, 'actual', None) == ('CLM', 15)), None)
        if picture is None:
            return
        try:
            data = self.asset_data(picture)
        except FormatError:
            return
        if len(data) >= 0x14 + 512 and data[:4] == b'\x10\0\0\0':
            vram[510, 128:384] = np.frombuffer(bytes(data[0x14:0x14 + 512]), '<u2')
