"""Polygon edge outlines using the Tomba2Edit selection colours."""
import numpy as np

POLYGON_OUTLINE = (1.0, 1.0, 0.2)
GEOMETRY_OUTLINE = (0.80, 0.50, 0.05)
MODEL_OUTLINE = (0.75, 0.55, 0.1)


def mesh_outline(mesh):
    """Actual triangle/quad edges, without triangulation diagonals or a box."""
    segments = []
    for polygon in mesh.polygons:
        vertices = polygon['vertices']
        ring = (0, 1, 3, 2) if len(vertices) == 4 else (0, 1, 2)
        for a, b in zip(ring, ring[1:] + ring[:1]):
            segments.extend((vertices[a], vertices[b]))
    return np.asarray(segments, dtype=np.float32).reshape(-1, 3)
