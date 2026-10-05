"""WMD mesh decoder. Eight primitive batches per object, verified against OBJ dumps."""
from dataclasses import dataclass, field
import struct
import numpy as np
from disc.reader import FormatError


@dataclass
class Mesh:
    offset: int
    # key: (texture page, CLUT, semi-transparency); value: vertex/UV/colour arrays.
    batches: dict
    polygons: list = field(default_factory=list)
    image: object = None


def parse_wmd(data):
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
            size = 4 + nc * 4 + nv * 8 + (0 if textured else nc * 8)
            if pos + amount * size > end:
                raise FormatError("WMD primitive data extends outside object")
            for _ in range(amount):
                clut, page = struct.unpack_from("<HH", data, pos) if textured else (0, -1)
                color_pos = pos + (4 if textured else 0)
                colors = np.frombuffer(data, dtype=np.uint8, count=nc * 4, offset=color_pos).reshape(nc, 4)
                cmd = int(colors[0, 3])
                expected = (0x24, 0x2C, 0x34, 0x3C, 0x20, 0x28, 0x30, 0x38)[kind]
                if cmd & 0xFC != expected:
                    raise FormatError(f"Unexpected WMD GPU command {cmd:02X}")
                vp = color_pos + nc * 4
                vertices, uv = [], []
                for j in range(nv):
                    x, y, z, u, v = struct.unpack_from("<hhhBB", data, vp + j * 8)
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
                                     kind=('FT3', 'FT4', 'GT3', 'GT4', 'F3', 'F4', 'G3', 'G4')[kind]))
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
