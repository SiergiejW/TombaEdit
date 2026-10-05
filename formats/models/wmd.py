"""WMD mesh decoder. Eight primitive batches per object, verified against OBJ dumps.

Two layouts of a textured primitive exist. The builds from 1997 (the
Japanese demo and the sampler disc) follow the GPU packet: colours, then one
word per corner holding U, V and, for the first two corners, the CLUT and
the texture page, then eight bytes of position per corner. Later builds put
the CLUT and page first and fold U and V into the spare half of each
position. Untextured primitives are the same in both.
"""
from dataclasses import dataclass, field
import struct
import numpy as np
from disc.reader import FormatError

KINDS = ('FT3', 'FT4', 'GT3', 'GT4', 'F3', 'F4', 'G3', 'G4')
COMMANDS = (0x24, 0x2C, 0x34, 0x3C, 0x20, 0x28, 0x30, 0x38)
RETAIL, EARLY = 'retail', 'early'


@dataclass
class Mesh:
    offset: int
    # key: (texture page, CLUT, semi-transparency); value: vertex/UV/colour arrays.
    batches: dict
    polygons: list = field(default_factory=list)
    image: object = None


def primitive_size(kind, layout=RETAIL):
    """Bytes one primitive of a batch occupies."""
    corners = 3 + kind % 2
    colours = corners if kind % 4 >= 2 else 1
    if kind >= 4:
        return 4 + colours * 4 + corners * 8 + colours * 8
    if layout == EARLY:
        return colours * 4 + corners * 4 + corners * 8
    return 4 + colours * 4 + corners * 8


def parse_wmd(data, layout=None):
    """Decode a bank. `layout` is RETAIL or EARLY; left out, the retail
    layout is tried first and the early one when the bank does not fit it."""
    if layout is None:
        try:
            return parse_wmd(data, RETAIL)
        except FormatError as newer:
            try:
                return parse_wmd(data, EARLY)
            except FormatError:
                raise newer from None
    if len(data) < 4:
        raise FormatError("WMD missing object count")
    count = struct.unpack_from("<I", data)[0]
    if count > 4096 or 4 + count * 4 > len(data):
        raise FormatError("Invalid WMD object table")
    pointers = list(struct.unpack_from(f"<{count}I", data, 4)) + [len(data)]
    if any(p < 4 + count * 4 or p > len(data) for p in pointers) or pointers != sorted(pointers):
        raise FormatError("Invalid WMD object offsets")
    meshes = []
    for start, end in zip(pointers, pointers[1:]):
        pos, batches, polygons = start, {}, []
        for kind in range(8):
            if pos + 4 > end:
                raise FormatError("Truncated WMD primitive batch")
            amount = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            nv = 3 + kind % 2
            nc = nv if kind % 4 >= 2 else 1
            textured = kind < 4
            size = primitive_size(kind, layout)
            if pos + amount * size > end:
                raise FormatError("WMD primitive data extends outside object")
            for _ in range(amount):
                early = textured and layout == EARLY
                if early:
                    # Corner words: U, V, then CLUT for the first corner and
                    # texture page for the second.
                    words = pos + nc * 4
                    clut = struct.unpack_from("<H", data, words + 2)[0]
                    page = struct.unpack_from("<H", data, words + 6)[0]
                    color_pos = pos
                else:
                    clut, page = struct.unpack_from("<HH", data, pos) if textured else (0, -1)
                    color_pos = pos + (4 if textured else 0)
                colors = np.frombuffer(data, dtype=np.uint8, count=nc * 4, offset=color_pos).reshape(nc, 4)
                cmd = int(colors[0, 3])
                if cmd & 0xFC != COMMANDS[kind]:
                    raise FormatError(f"Unexpected WMD GPU command {cmd:02X}")
                vp = color_pos + nc * 4 + (nv * 4 if early else 0)
                vertices, uv = [], []
                for j in range(nv):
                    x, y, z, u, v = struct.unpack_from("<hhhBB", data, vp + j * 8)
                    if early:
                        u, v = data[words + j * 4], data[words + j * 4 + 1]
                    vertices.append((x, -y, -z))
                    uv.append(((u + 0.5) / 256, (v + 0.5) / 256))
                # PSX texture modulation uses 128 as neutral. Raw-textured
                # primitives (bit 0) bypass vertex colour modulation.
                cols = colors[:, :3].astype(np.float32) / (128 if textured else 255)
                if textured and cmd & 1:
                    cols[:] = 1
                if nc == 1:
                    cols = np.repeat(cols, nv, axis=0)
                order = [0, 1, 2] if nv == 3 else [0, 1, 2, 3, 2, 1]
                key = (page, clut, bool(cmd & 2))
                polygons.append(dict(offset=pos, vertices=vertices, uv=uv,
                                     colors=cols, page=page, clut=clut, command=cmd,
                                     kind=KINDS[kind]))
                target = batches.setdefault(key, [[], [], []])
                target[0].extend(vertices[j] for j in order)
                target[1].extend(uv[j] for j in order)
                target[2].extend(cols[j] for j in order)
                pos += size
        if pos != end:
            raise FormatError(f"Unparsed WMD object bytes at {pos:X}..{end:X}")
        meshes.append(Mesh(start, {key: tuple(np.asarray(a, dtype=np.float32) for a in arrays)
                                   for key, arrays in batches.items()}, polygons))
    return meshes


def layout_of(data):
    """Which textured layout a bank uses, or None if it is not a WMD."""
    for layout in (RETAIL, EARLY):
        try:
            parse_wmd(data, layout)
            return layout
        except FormatError:
            continue
    return None
