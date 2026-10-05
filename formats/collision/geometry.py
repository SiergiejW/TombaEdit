"""WHM boundaries in world space, preserving their source records."""
from dataclasses import dataclass
import numpy as np
from formats.collision.whm import PLANE_DEPTH

FLOOR = (.35, 1., .35)
CEILING = (.3, .7, 1.)
SIDE = (1., .3, .9)
SOLID = (1., .6, .15)


@dataclass
class CollisionRecord:
    source: object
    span: object
    points: tuple
    depth: float
    turned: bool
    route: str = 'Default route'

    @property
    def color(self):
        a = self.span.attribute
        return SOLID if a & 16 else SIDE if a & 12 else CEILING if a & 2 else FLOOR


def records(whm, along0=0, depth0=0, turned=False, source=None, planes=None):
    out = []
    for plane in whm.planes:
        if planes is not None and plane.index not in planes:
            continue
        depth = depth0 + plane.index * PLANE_DEPTH * (-1 if turned else 1)
        for span in plane.spans:
            points = []
            for segment in span.segments:
                for x, y in segment:
                    points.append((depth, -y, -(along0 + x)) if turned else
                                  (along0 + x, -y, -depth))
            if points:
                out.append(CollisionRecord(source, span, tuple(points), depth, turned))
    return out


def lines(rows):
    """Remove duplicate edges, including internal edges of adjacent solids.

    Solids are merged as rectangle unions per depth slice. Surface records
    stay separate for picking and inspection, but identical lines are drawn
    once. No averaging or smoothing changes the actual collision shape.
    """
    edges = {}
    rectangles = {}
    for row in rows:
        if row.span.wall and row.span.length and row.span.y1:
            rectangles.setdefault((id(row.source), row.span.plane, row.turned, row.depth, row.route), []).append(row)
            continue
        for a, b in zip(row.points[::2], row.points[1::2]):
            if a != b:
                edges[tuple(sorted((a, b)))] = row.color

    # Split collinear rectangle edges at every endpoint; only exposed pieces
    # survive. This removes the comb of vertical lines through solid ground.
    for group in rectangles.values():
        horizontal, vertical = {}, {}
        bounds = [(tuple(min(p[i] for p in row.points) for i in range(3)),
                   tuple(max(p[i] for p in row.points) for i in range(3))) for row in group]
        along = 2 if group[0].turned else 0
        for row in group:
            for a, b in zip(row.points[::2], row.points[1::2]):
                varying = next((i for i in range(3) if a[i] != b[i]), None)
                if varying is None:
                    continue
                axis = vertical if varying == 1 else horizontal
                key = (varying, tuple(a[i] for i in range(3) if i != varying))
                axis.setdefault(key, []).append((min(a[varying], b[varying]), max(a[varying], b[varying])))
        for axis in (horizontal, vertical):
            for (varying, fixed), intervals in axis.items():
                boundaries = sorted({v for interval in intervals for v in interval})
                pieces = []
                across = along if varying == 1 else 1
                centre = list(fixed); centre.insert(varying, 0)
                coordinate = centre[across]
                before = [(lo[varying], hi[varying]) for lo, hi in bounds
                          if lo[across] < coordinate - .0001 < hi[across]]
                after = [(lo[varying], hi[varying]) for lo, hi in bounds
                         if lo[across] < coordinate + .0001 < hi[across]]
                for low, high in zip(boundaries, boundaries[1:]):
                    middle = (low + high) / 2
                    if any(a < middle < b for a, b in before) != any(a < middle < b for a, b in after):
                        if pieces and pieces[-1][1] == low:
                            pieces[-1] = (pieces[-1][0], high)
                        else:
                            pieces.append((low, high))
                for low, high in pieces:
                    def point(v):
                        p = list(fixed); p.insert(varying, v); return tuple(p)
                    edges[tuple(sorted((point(low), point(high))))] = SOLID
    if not edges:
        return None
    vertices = [p for edge in edges for p in edge]
    colors = [color for color in edges.values() for _ in range(2)]
    return np.asarray(vertices, np.float32), np.asarray(colors, np.float32)
