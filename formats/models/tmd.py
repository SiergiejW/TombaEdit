"""TMD, the model file of Sony's own libraries.

A TMD is the word 0x41, a flag word, an object count and one 28-byte record
per object: where its vertices, normals and primitives start, how many of
each there are, and a scale. Offsets count from the first record unless bit
0 of the flags says they are memory addresses already.

A primitive opens with four bytes: the length of the drawing packet it
becomes, its own length in words, a flag byte and a mode byte. The mode is
a GPU command: bit 2 textured, bit 3 a quad, bit 4 shaded per vertex, bit 1
semi-transparent. Flag bit 0 turns lighting off, in which case colours are
stored in place of normals; bit 2 gives a lit face a colour per vertex.
The body is then, in order: a word per corner with U, V and (on the first
two) the CLUT and texture page; the colours; and 16-bit indices into the
vertex and normal lists.

Meshes come out in the shape the WMD decoder produces, so the same viewer
and exporter take them.
"""
import struct
import numpy as np
from disc.reader import FormatError
from formats.models.wmd import Mesh

MAGIC = 0x41
RECORD = 28


def header(data, offset=0):
    """(flags, object count) if a TMD starts at `offset`, else None."""
    if offset + 12 > len(data):
        return None
    magic, flags, count = struct.unpack_from('<3I', data, offset)
    if magic != MAGIC or flags > 1 or not 0 < count <= 4096 or offset + 12 + count * RECORD > len(data):
        return None
    return flags, count


def objects(data, offset=0):
    """[(vertices at, count, normals at, count, primitives at, count)] with
    absolute positions, or None if any of them leaves the data."""
    found = header(data, offset)
    if found is None or found[0]:
        return None
    base, out = offset + 12, []
    for n in range(found[1]):
        vert, nvert, norm, nnorm, prim, nprim, _scale = struct.unpack_from('<6Ii', data, base + n * RECORD)
        if max(nvert, nnorm, nprim) > 65536 or base + vert + nvert * 8 > len(data) \
                or base + norm + nnorm * 8 > len(data) or base + prim + nprim * 4 > len(data):
            return None
        out.append((base + vert, nvert, base + norm, nnorm, base + prim, nprim))
    return out


def layout(flag, mode):
    """(corners, UV words, colour words, indices, stride of a corner's
    indices, lit) of a polygon primitive."""
    corners = 4 if mode & 8 else 3
    textured, shaded = bool(mode & 4), bool(mode & 0x10)
    if flag & 1:        # no lighting: colours stand in for normals
        colours = corners if shaded else 1
        return corners, corners * textured, colours, corners, 1, False
    colours = 0 if textured else corners if flag & 4 else 1
    return corners, corners * textured, colours, corners * 2 if shaded else corners + 1, 2 if shaded else 1, True


def parse(data, offset=0):
    """[Mesh], one per object."""
    table = objects(data, offset)
    if table is None:
        raise FormatError('Not a TMD model, or one whose offsets are memory addresses')
    meshes = []
    for vert, nvert, _norm, _nnorm, prim, nprim in table:
        points = np.frombuffer(data, '<i2', nvert * 4, vert).reshape(nvert, 4)[:, :3].astype(np.float32)
        points = points * np.array((1, -1, -1), np.float32)
        batches, polygons, pos = {}, [], prim
        for _ in range(nprim):
            if pos + 4 > len(data):
                raise FormatError('TMD primitive list is cut off')
            _olen, ilen, flag, mode = data[pos:pos + 4]
            start, pos = pos, pos + 4 + ilen * 4
            if pos > len(data):
                raise FormatError('TMD primitive extends outside the file')
            if mode >> 5 != 1:
                continue            # lines and sprites
            corners, uvs, colours, indices, stride, lit = layout(flag, mode)
            at = start + 4
            if 4 * (uvs + colours) + 2 * indices > ilen * 4:
                raise FormatError(f'TMD primitive {mode:02X}/{flag:02X} is shorter than its mode needs')
            page, clut, uv = -1, 0, [(0., 0.)] * corners
            if uvs:
                clut = struct.unpack_from('<H', data, at + 2)[0]
                page = struct.unpack_from('<H', data, at + 6)[0] & 0x1FF
                uv = [((data[at + j * 4] + .5) / 256, (data[at + j * 4 + 1] + .5) / 256) for j in range(corners)]
                at += uvs * 4
            if colours:
                rgb = np.frombuffer(data, np.uint8, colours * 4, at).reshape(colours, 4)[:, :3].astype(np.float32)
                rgb = rgb / (128 if uvs else 255)
                at += colours * 4
            else:
                rgb = np.ones((1, 3), np.float32)
            if len(rgb) == 1:
                rgb = np.repeat(rgb, corners, axis=0)
            words = struct.unpack_from(f'<{indices}H', data, at)
            # Lit faces lead each index (or just the first) with a normal.
            picked = words[1::2] if lit and stride == 2 else words[1:] if lit else words
            if any(i >= nvert for i in picked[:corners]):
                raise FormatError('TMD primitive names a vertex past the end of the list')
            vertices = [tuple(points[i]) for i in picked[:corners]]
            order = [0, 1, 2] if corners == 3 else [0, 1, 2, 3, 2, 1]
            key = (page, clut, bool(mode & 2))
            polygons.append(dict(offset=start, vertices=vertices, uv=uv, colors=rgb, page=page, clut=clut,
                                 command=mode, kind=('G' if mode & 0x10 else 'F') + ('T' if uvs else '') + str(corners)))
            target = batches.setdefault(key, [[], [], []])
            target[0].extend(vertices[j] for j in order)
            target[1].extend(uv[j] for j in order)
            target[2].extend(rgb[j] for j in order)
        meshes.append(Mesh(vert, {key: tuple(np.asarray(a, dtype=np.float32) for a in arrays)
                                  for key, arrays in batches.items()}, polygons))
    return meshes


def jointed(meshes):
    """Whether the objects are parts of a figure, each modelled around its
    own origin for the game to pose, rather than pieces of one scene. Such
    parts lie on top of one another as stored: together they span little
    more than the largest of them."""
    spans, low, high = [], None, None
    for mesh in meshes:
        points = [batch[0] for batch in mesh.batches.values() if len(batch[0])]
        if not points:
            continue
        points = np.concatenate(points)
        a, b = points.min(axis=0), points.max(axis=0)
        spans.append(float(np.linalg.norm(b - a)))
        low = a if low is None else np.minimum(low, a)
        high = b if high is None else np.maximum(high, b)
    return len(spans) >= 3 and float(np.linalg.norm(high - low)) < 1.6 * max(spans)


def size(data, offset=0):
    """Bytes the TMD at `offset` occupies, from the end of its last list."""
    table = objects(data, offset)
    if table is None:
        return 0
    end = offset + 12 + len(table) * RECORD
    for vert, nvert, norm, nnorm, prim, nprim in table:
        pos = prim
        for _ in range(nprim):
            if pos + 4 > len(data):
                return 0
            pos += 4 + data[pos + 1] * 4
        end = max(end, vert + nvert * 8, norm + nnorm * 8, pos)
    return min(end, len(data)) - offset
