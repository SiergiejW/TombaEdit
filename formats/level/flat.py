"""Flat scene identification, PSX painter order and opaque-pixel picking."""
import numpy as np
from psx.graphics import texture_page


def is_flat(entries):
    active = [e for e in entries if e.active]
    if any(e.alternative is not None for e in active):
        return True                         # a town's resident TIM picture
    geometry = [e.mesh for e in active if e.category == 'Geometry' and e.mesh.image is None]
    if geometry:
        vertices = [b[0] for m in geometry for b in m.batches.values() if len(b[0])]
        return bool(vertices) and np.ptp(np.concatenate(vertices)[:, 2]) < .01
    if any(e.mesh.image is not None and e.category == 'Backgrounds' for e in active):
        return True                         # fixed interior picture, with actors
    return not any(e.category == 'Models' for e in active)


def ordering_bucket(placement, visual, fixed_picture=False):
    """High OT buckets paint first. +0F is a signed per-object bias.

    US 80048B14/80048B4C: fixed bucket, or projected depth/4 plus bias,
    with four reserved buckets in front. Screen sprites (8004E014) and
    fixed rectangles (8004E338) use bucket 804 plus their ordering offset.
    """
    bias = visual.get('sort_bias', int.from_bytes(placement.raw[13:14], 'little', signed=True))
    if fixed_picture:
        return 804 + bias
    # Camera anchoring only changes position. Room furniture can follow the
    # camera while using the ordinary actor draw list (US 80018C40), not
    # the layer 7 screen-sprite renderer and its reserved backdrop buckets.
    if placement.layer == 7 and placement.raw[12] == 1:
        return 804 + visual.get('screen_bias', bias)
    depth = 0 if visual.get('sort_fixed') else visual.get('sort_depth', placement.position[2]) // 4
    return max(0, depth + bias) + 4


def paint_order(entries):
    # Insertion into the draw list and into the OT both prepend. For equal
    # buckets the APD order is therefore retained in the final painter pass.
    return sorted(range(len(entries)), key=lambda i: (-entries[i].draw_bucket, i))


def pick(meshes, order, visible, point, vram):
    """Select the last painted opaque polygon under a world X/Y point."""
    point = np.asarray(point, np.float64)
    for index in reversed(order):
        if index not in visible:
            continue
        mesh = meshes[index]
        best = None
        best_depth = -float('inf')
        for polygon in reversed(mesh.polygons):
            vertices = np.asarray(polygon['vertices'])[:, :2]
            triangles = ((0, 1, 2), (3, 2, 1)) if len(vertices) == 4 else ((0, 1, 2),)
            for triangle in triangles:
                a, b, c = vertices[list(triangle)]
                matrix = np.column_stack((b - a, c - a))
                if abs(np.linalg.det(matrix)) < 1e-8:
                    continue
                u, v = np.linalg.solve(matrix, point - a)
                if u < -1e-6 or v < -1e-6 or u + v > 1 + 1e-6:
                    continue
                image = mesh.image
                if image is None and polygon['page'] >= 0:
                    image = texture_page(vram, polygon['page'], polygon['clut'])
                if image is not None:
                    uv = np.asarray(polygon['uv'])[list(triangle)]
                    coord = (1 - u - v) * uv[0] + u * uv[1] + v * uv[2]
                    x = min(image.width - 1, max(0, int(coord[0] * image.width)))
                    y = min(image.height - 1, max(0, int(coord[1] * image.height)))
                    if image.getpixel((x, y))[3] <= 12:
                        continue
                if mesh.image is not None:
                    return index, polygon
                # Solid assets retain their internal depth in the flat view.
                # Pick the front face rather than the last stored primitive.
                z = np.asarray(polygon['vertices'])[list(triangle), 2]
                depth = (1 - u - v) * z[0] + u * z[1] + v * z[2]
                if depth > best_depth:
                    best, best_depth = (index, polygon), depth
        if best is not None:
            return best
    return None
