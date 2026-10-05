"""LDAR load groups, source ranges, and ordered VRAM uploads."""
from dataclasses import dataclass, field
from collections import OrderedDict
import struct
import numpy as np
from disc.reader import FormatError
from formats.archive.gam import decompress


SYSTEM_LDAR = 'SYS/LDSYS.BIN'


def type_name(code):
    if code == 3: return "SPC"
    if code == 8: return "SAP"
    hi = code >> 8
    if hi in (0x8E, 0x8F): return "CLM"
    # Family 9 is a sound bank. Retail loads those by name; earlier builds
    # list them in their load groups.
    return {1: "GRPX", 3: "SPR", 4: "FOUR", 5: "WMD", 6: "WPP", 7: "WHM", 8: "APD",
            9: "WVD", 11: "SEQ", 13: "WFM", 15: "INS"}.get(hi >> 4, "Unknown")


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
        try:
            self.catalog = Catalog.discover(self.disc)
        except FormatError as exc:
            self.warnings.append(str(exc))
        if self.catalog:
            for entry in self.disc.files:
                if entry.path.startswith("SYS/LD") and entry.path.endswith(".BIN"):
                    try:
                        self.ldars[entry.path] = parse_ldar(self.disc.read(entry), entry.path, self.catalog)
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

    def vram(self, path, group_index):
        vram = np.zeros((512, 1024), dtype=np.uint16)
        groups = self.ldars[path]
        wanted = [(groups[0], 0)] if group_index == 0 else [(groups[0], 0), (groups[group_index], 0)]
        # The first group of the system table is loaded at boot and its
        # lower half of VRAM is never replaced: item and effect sprites on
        # pages 20 and 21, with their palettes.
        system = self.ldars.get(SYSTEM_LDAR)
        if system and path != SYSTEM_LDAR:
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
        return vram
