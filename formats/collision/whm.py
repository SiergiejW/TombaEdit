"""Tomba 1 WHM: collision spans indexed by depth plane and X column.

US routine 80042654 selects a depth slice and an eight-unit path column.
Eight-byte records are <HhhH>: attribute, base Y, signed Y delta, packed
horizontal interval and contact control. The second signed word is NEVER
an absolute end Y. Attribute 0010 fills a rectangle; 0001/0002 are floor /
ceiling boundaries and 0004/0008 are directional side boundaries.
See docs/collision.md for the evaluator, including integer rounding.
"""
from dataclasses import dataclass
import struct

from disc.reader import FormatError

PLANE_DEPTH = 90


def trunc_div(numerator, denominator):
    """Signed MIPS DIV rounds towards zero, including negative slopes."""
    return (-1 if numerator < 0 else 1) * (abs(numerator) // denominator)


def signed16(value):
    return (value + 32768) % 65536 - 32768


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
        """Compatibility name: bit 4 denotes a filled region, not a wall."""
        return bool(self.attribute & 0x10)

    @property
    def start(self):
        return self.parameter & 15

    @property
    def length(self):
        return (self.parameter >> 4) & 15

    @property
    def contact(self):
        return self.parameter >> 8

    @property
    def shape(self):
        if self.wall:
            return 'Solid region'
        return ' + '.join(name for bit, name in ((1, 'Floor'), (2, 'Ceiling'),
                         (4, 'Left boundary'), (8, 'Right boundary'))
                         if self.attribute & bit) or 'Inactive'

    def height_at(self, local_x, integer=False):
        """Floor evaluator 8004339C, before its contact tolerance tests.

        The standing test extrapolates to the whole column. Its flat / zero
        width case uses the lower endpoint of a negative rise. Ceiling and
        side tests also enforce the packed horizontal interval.
        """
        if not self.y1:
            value = self.y0
        elif not self.length:
            value = self.y0 + min(0, self.y1)
        else:
            numerator = self.y1 * (local_x - self.start)
            value = self.y0 + (trunc_div(int(numerator), self.length) if integer
                               else numerator / self.length)
        return signed16(value) if integer else value

    @property
    def segments(self):
        """Boundary segments in local X/Y, without fabricated joins.

        Floors and ceilings use the packed interval, side boundaries can
        have zero width (vertical). Flat zero-width floors cover a column.
        Filled records are rectangles from base Y to base Y + delta.
        """
        x = self.column * 8 + self.start
        end = x + self.length
        y, bottom = self.y0, self.y0 + self.y1
        if self.wall:
            return (((x, y), (end, y)), ((end, y), (end, bottom)),
                    ((end, bottom), (x, bottom)), ((x, bottom), (x, y)))
        if not self.attribute & 15:
            return ()
        if not self.length and self.attribute & 3:
            y = self.height_at(0)
            return (((self.column * 8, y), (self.column * 8 + 8, y)),)
        return (((x, y), (end, bottom)),)

    @property
    def extent(self):
        """Lowest and highest Y the span touches."""
        end = self.y0 + self.y1
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
    tag, origin, width, y_header = struct.unpack_from('<4H', data)
    count = tag >> 8
    if tag & 255 != 0x11 or not 0 < count <= 32 or not width or width % 8:
        raise FormatError('WHM header has an unsupported plane or X table layout')
    if 8 + count * 2 > len(data):
        raise FormatError('WHM plane table is truncated')
    starts = struct.unpack_from(f'<{count}H', data, 8)
    flags = starts[0]  # retained for callers of the original header API
    ends = starts[1:] + (len(data),)
    if starts[0] < 8 + count * 2:
        raise FormatError('WHM first plane overlaps its header')
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
