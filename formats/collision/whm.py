"""Tomba 1 WHM: collision spans indexed by depth plane and X column.

US routine 80042654 picks a plane from an object's Z, 90 units per plane,
and a column from its X, 8 units per column. A column starts with a u16 span
count followed by eight-byte spans: attribute, two signed words and a
parameter. With bit 4 of the attribute set the span is a solid range between
the two Y values. Otherwise it is a walkable surface: the first word is its Y
at the left edge of the column and the second the rise across the column, so
neighbouring columns join into slopes. Y is negative upwards, as in the
models. The remaining attribute bits and the parameter are shown raw.
"""
from dataclasses import dataclass
import struct

from disc.reader import FormatError

PLANE_DEPTH = 90


@dataclass(frozen=True)
class Span:
    plane: int
    column: int
    offset: int
    attribute: int
    y0: int
    y1: int
    parameter: int

    @property
    def wall(self):
        return bool(self.attribute & 0x10)

    @property
    def extent(self):
        """Lowest and highest Y the span touches."""
        end = self.y1 if self.wall else self.y0 + self.y1
        return min(self.y0, end), max(self.y0, end)


@dataclass
class Plane:
    index: int
    columns: list

    @property
    def spans(self):
        return [span for column in self.columns for span in column]


@dataclass
class Whm:
    width: int
    y_header: int
    origin: int
    flags: int
    planes: list

    @property
    def spans(self):
        return [span for plane in self.planes for span in plane.spans]


def parse_whm(data):
    if len(data) < 12:
        raise FormatError('WHM header is truncated')
    tag, origin, width, y_header, flags = struct.unpack_from('<5H', data)
    count = tag >> 8
    if tag & 255 != 0x11 or not 0 < count <= 32 or not width or width % 8:
        raise FormatError('WHM header has an unsupported plane or X table layout')
    if 10 + count * 2 > len(data):
        raise FormatError('WHM plane table is truncated')
    markers = struct.unpack_from(f'<{count}H', data, 10)
    starts = (10 + 2 * (count - 1),) + markers[:-1]
    ends = markers[:-1] + (len(data),)
    if any(start >= end or end > len(data) for start, end in zip(starts, ends)):
        raise FormatError('WHM plane boundaries are invalid')
    planes = []
    columns_per_plane = width // 8
    for plane_index, (base, end) in enumerate(zip(starts, ends)):
        table_bytes = columns_per_plane * 2
        if base + table_bytes > end:
            raise FormatError(f'WHM plane {plane_index} X table is truncated')
        offsets = struct.unpack_from(f'<{columns_per_plane}H', data, base)
        if offsets[0] != table_bytes or any(a > b for a, b in zip(offsets, offsets[1:])):
            raise FormatError(f'WHM plane {plane_index} X offsets are invalid')
        columns = []
        for x, relative in enumerate(offsets):
            at = base + relative
            if at + 2 > end:
                raise FormatError(f'WHM plane {plane_index} column {x} is outside the plane')
            amount = struct.unpack_from('<H', data, at)[0]
            if amount > 1024 or at + 2 + amount * 8 > end:
                raise FormatError(f'WHM plane {plane_index} column {x} has invalid spans')
            column = []
            for i in range(amount):
                offset = at + 2 + i * 8
                attribute, y0, y1, parameter = struct.unpack_from('<HhhH', data, offset)
                column.append(Span(plane_index, x, offset, attribute, y0, y1, parameter))
            columns.append(column)
        planes.append(Plane(plane_index, columns))
    return Whm(width, y_header, origin, flags, planes)
