"""Identify outward winding where a model or assembled model is closed."""
import numpy as np


def closed_winding(meshes):
    arrays = [b[0] for m in meshes for b in m.batches.values() if len(b[0])]
    if not arrays:
        return None
    triangles = np.concatenate(arrays).reshape(-1, 3, 3).astype(np.float64)
    edges = {}
    for triangle in np.round(triangles, 4):
        a, b, c = map(tuple, triangle)
        if len({a, b, c}) != 3:
            continue
        for x, y in ((a, b), (b, c), (c, a)):
            edge = tuple(sorted((x, y)))
            edges[edge] = edges.get(edge, 0) + 1
    if not edges or any(count != 2 for count in edges.values()):
        return None
    triangles -= triangles.reshape(-1, 3).mean(0)
    volume = np.einsum('ij,ij->i', triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum()
    return bool(volume < 0) if abs(volume) > 1e-6 else None
