"""Identify outward winding where a model or assembled model is closed."""
import numpy as np


def closed_winding(meshes):
    arrays, faces = [], set()
    for mesh in meshes:
        polygons = getattr(mesh, 'polygons', None)
        if polygons is None:
            arrays.extend(b[0] for b in mesh.batches.values() if len(b[0]))
            continue
        for polygon in polygons:
            points = np.asarray(polygon['vertices'], np.float64)
            face = tuple(sorted(map(tuple, np.round(points, 4))))
            # Some panels include a second, inward-facing copy, with the
            # opposite quad diagonal. Count the first surface once when
            # checking whether the assembly encloses a volume.
            if face in faces:
                continue
            faces.add(face)
            order = [0, 1, 2] if len(points) == 3 else [0, 1, 2, 3, 2, 1]
            arrays.append(points[order])
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
