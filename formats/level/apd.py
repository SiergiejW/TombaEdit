"""APD spawn records, traced through US routine 8005AA98."""
from dataclasses import dataclass
import struct
from disc.reader import FormatError


@dataclass
class Placement:
    offset: int
    raw: bytes
    position: tuple
    relative: bool = False

    @property
    def layer(self): return self.raw[1] & 127

    @property
    def kind(self): return self.raw[2]

    @property
    def variant(self): return self.raw[4]

    @property
    def section(self): return struct.unpack_from('<b', self.raw)[0]

    @property
    def model(self):
        if self.layer == 8:
            return 2, self.raw[14]
        if self.layer in (2, 4) and self.raw[12] & 16 and self.raw[14] != 255:
            return 1, self.raw[14]
        return None


def parse_apd(data):
    if len(data) % 16:
        raise FormatError('APD size is not a multiple of 16 bytes')
    placements, parent = [], None
    for at in range(0, len(data), 16):
        raw = data[at:at + 16]
        if raw[2] == 255:
            break
        position = struct.unpack_from('<3h', raw, 6)
        mode = raw[15] & 3
        relative = mode in (2, 3) and raw[1] & 127 not in (6, 7)
        if relative and parent is not None:
            position = tuple(a + b for a, b in zip(position, parent))
        if mode in (1, 2) and raw[1] & 127 not in (6, 7):
            parent = position
        placements.append(Placement(at, raw, position, relative))
    return placements
