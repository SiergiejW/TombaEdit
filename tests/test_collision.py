"""Geometry regressions independent of copyrighted game data."""
import struct
import unittest
from formats.collision.whm import Span, Whm, Plane, parse_whm
from formats.collision.geometry import records, lines
from disc.reader import FormatError


class CollisionTests(unittest.TestCase):
    def span(self, attribute=1, y=-100, delta=-6, parameter=0x42, column=0):
        return Span(0, column, 20, attribute, y, delta, parameter)

    def test_signed_division_and_partial_interval(self):
        span = self.span(delta=-5)
        self.assertEqual(span.height_at(1, integer=True), -99)
        self.assertEqual(span.height_at(3, integer=True), -101)
        self.assertEqual(span.height_at(3), -101.25)
        self.assertEqual(span.segments, (((2, -100), (6, -105)),))

    def test_solid_delta_and_vertical_side(self):
        solid = self.span(17, y=-50, delta=-300, parameter=0x80)
        self.assertEqual(solid.extent, (-350, -50))
        self.assertIn(((8, -50), (8, -350)), solid.segments)
        wall = self.span(8, y=-100, delta=-200, parameter=7)
        self.assertEqual(wall.segments, (((7, -100), (7, -300)),))

    def test_flat_zero_width_floor_matches_standing_evaluator(self):
        span = self.span(delta=-6, parameter=0)
        self.assertEqual(span.height_at(5, integer=True), -106)
        self.assertEqual(span.segments, (((0, -106), (8, -106)),))

    def test_solid_union_removes_internal_edges_keeps_outline(self):
        spans = [self.span(17, y=0, delta=-100, parameter=0x80, column=i) for i in range(2)]
        whm = Whm(16, 0, 0, 10, [Plane(0, [[spans[0]], [spans[1]]])])
        vertices, _ = lines(records(whm))
        self.assertEqual(len(vertices), 8)  # four exterior edges, no centre seam
        self.assertNotIn([8., 0., 0.], vertices.tolist())
        # Duplicate filled records do not cancel the outer boundary.
        duplicated, _ = lines(records(whm) + records(whm))
        self.assertEqual(len(duplicated), 8)

    def test_inactive_records_have_no_invented_boundary(self):
        self.assertEqual(self.span(0x8000).segments, ())

    def test_explicit_plane_offsets_and_alias_columns(self):
        # Two columns can reuse one list. The first plane has padding before
        # it, which the executable's explicit offset (not a guessed header
        # size) must honour.
        data = struct.pack('<5H', 0x0111, 0, 16, 2400, 14) + bytes(4)
        data += struct.pack('<3H', 4, 4, 1) + struct.pack('<HhhH', 1, -20, -4, 0x80)
        whm = parse_whm(data)
        self.assertEqual([s.offset for s in whm.spans], [20, 20])
        self.assertEqual([s.column for s in whm.spans], [0, 1])
        with self.assertRaises(FormatError):
            parse_whm(data[:8] + bytes(2) + data[10:])


if __name__ == '__main__':
    unittest.main()
