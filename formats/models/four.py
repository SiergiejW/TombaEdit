"""FOUR model deformation banks, decoded from the US game routine 80027A30.

The eight batches correspond to WMD primitive types. Each record starts
with one signed SVECTOR delta per corner, followed by reserved words.
The game subtracts (delta * weight) >> 12 from the source WMD vertex.
The banks carry no name of their own. Load records identify them only by
type codes 40FF to 45FF, and FOUR is the label those codes have in the
community's type list.
"""
from dataclasses import dataclass
import struct
import numpy as np
from disc.reader import FormatError
from formats.models.wmd import Mesh

KINDS = ('FT3', 'FT4', 'GT3', 'GT4', 'F3', 'F4', 'G3', 'G4')
STRIDES = (32, 40, 48, 64, 32, 40, 48, 64)


@dataclass
class Morph:
    offset: int
    counts: tuple
    deltas: list
    reserved: list


def parse_four(data):
    if len(data) < 4:
        raise FormatError('FOUR object table is missing')
    count = struct.unpack_from('<I', data)[0]
    if not 0 < count <= 4096 or 4 + count * 4 > len(data):
        raise FormatError('Invalid FOUR object count')
    offsets = list(struct.unpack_from(f'<{count}I', data, 4)) + [len(data)]
    if offsets[0] < 4 + count * 4 or any(a >= b for a, b in zip(offsets, offsets[1:])):
        raise FormatError('Invalid FOUR object offsets')
    morphs = []
    for start, end in zip(offsets, offsets[1:]):
        if end > len(data):
            raise FormatError('FOUR object extends outside the bank')
        pos, counts, deltas, reserved = start, [], [], []
        for kind, stride in enumerate(STRIDES):
            if pos + 4 > end:
                raise FormatError('Truncated FOUR batch')
            amount = struct.unpack_from('<I', data, pos)[0]
            pos += 4
            if amount > (end - pos) // stride:
                raise FormatError('Truncated FOUR vertex deltas')
            counts.append(amount)
            corners = 3 + kind % 2
            for _ in range(amount):
                vectors = np.frombuffer(data, '<i2', corners * 4, pos).reshape(corners, 4)
                deltas.append(vectors[:, :3].astype(np.int32))
                reserved.append(data[pos + corners * 8:pos + stride])
                pos += stride
        if pos != end:
            raise FormatError('Unparsed bytes after FOUR batches')
        morphs.append(Morph(start, tuple(counts), deltas, reserved))
    return morphs


def topology(mesh):
    return tuple(sum(p['kind'] == kind for p in mesh.polygons) for kind in KINDS)


def rebuild_mesh(polygons, offset=0, image=None):
    batches = {}
    for p in polygons:
        order = [0, 1, 2] if len(p['vertices']) == 3 else [0, 1, 2, 3, 2, 1]
        target = batches.setdefault((p['page'], p['clut'], bool(p['command'] & 2)), [[], [], []])
        for target_array, source in zip(target, (p['vertices'], p['uv'], p['colors'])):
            target_array.extend(source[i] for i in order)
    return Mesh(offset, {k: tuple(np.asarray(a, np.float32) for a in arrays)
                         for k, arrays in batches.items()}, polygons, image)


def deform(mesh, morph, weight):
    if topology(mesh) != morph.counts:
        raise FormatError('FOUR and WMD polygon batches do not match')
    polygons = []
    for polygon, delta in zip(mesh.polygons, morph.deltas):
        raw = np.rint(np.asarray(polygon['vertices']) * (1, -1, -1)).astype(np.int32)
        raw -= (delta * int(weight)) >> 12
        # The original routine writes signed 16-bit vertex coordinates.
        vertices = raw.astype(np.int16).astype(np.float32) * (1, -1, -1)
        polygons.append(dict(polygon, vertices=vertices))
    return rebuild_mesh(polygons, mesh.offset)
