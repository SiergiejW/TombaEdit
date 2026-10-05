"""Camera-facing sprite cards and restrained backdrop motion."""
import math
import numpy as np
from dataclasses import dataclass
from PIL import Image


def model_vertices(vertices, position, scale=(4096, 4096, 4096), rotation=(0, 0, 0)):
    """PSX RotMatrix order, in game coordinates, then the viewer's Y/Z flip."""
    rx, ry, rz = (v * 2 * math.pi / 4096 for v in rotation)
    sx, cx, sy, cy, sz, cz = math.sin(rx), math.cos(rx), math.sin(ry), math.cos(ry), math.sin(rz), math.cos(rz)
    x = np.array(((1, 0, 0), (0, cx, -sx), (0, sx, cx)))
    y = np.array(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)))
    z = np.array(((cz, -sz, 0), (sz, cz, 0), (0, 0, 1)))
    flip = np.array((1, -1, -1))
    raw = np.asarray(vertices) * flip * (np.asarray(scale) / 4096)
    return np.ascontiguousarray((raw @ (x @ y @ z).T + position) * flip, dtype=np.float32)


def billboard_vertices(vertices, anchor, heading, pitch):
    h, v = math.radians(heading), math.radians(pitch)
    right = np.array((math.cos(h), 0., math.sin(h)))
    up = np.array((math.sin(v) * math.sin(h), math.cos(v), -math.sin(v) * math.cos(h)))
    local = np.asarray(vertices) - anchor
    return np.ascontiguousarray(anchor + local[:, :1] * right + local[:, 1:2] * up,
                                dtype=np.float32)


def backdrop_position(sprite, camera_position, heading, pitch, turned=False):
    """Translation follows the game's fixed path axis, never the look axis.

    The game has no free-look panorama. For editor free-look one repeat spans
    a full turn; vertical movement is limited to half the reference screen.
    This avoids multiplying orbit movement by camera distance or rotating the
    direction of parallax when looking around.
    """
    path = -camera_position[2] if turned else camera_position[0]
    reference = (path - 160, -camera_position[1] - 240)
    period = abs(sprite.period) or 320
    angle = (heading + 180) % 360 - 180
    look = (angle if sprite.period else max(-90., min(90., angle))) * period / 360
    tilt = max(-90., min(90., pitch)) * 240 / 180
    return (sprite.screen[0] - reference[0] * sprite.follow[0] - look + sprite.left,
            sprite.screen[1] - reference[1] * sprite.follow[1] - tilt + sprite.top)


@dataclass
class Panorama:
    image: object
    follow: tuple
    top: float
    parts: list


def panorama_layers(backdrops, visible):
    """Join adjacent game strips before repeating them in editor free-look.

    The game only has its fixed path camera. The editor has a panorama:
    the whole vertical band fits at the horizon and finite scenery repeats
    horizontally too. World camera Y and forward distance do not move it.
    """
    sprites = [(i, b) for i, b in backdrops if i in visible]
    if not sprites:
        return []
    top = min(b.screen[1] + b.top for _, b in sprites)
    bottom = max(b.screen[1] + b.top + b.image.height for _, b in sprites)
    height = bottom - top
    groups = {}
    for i, b in sprites:
        groups.setdefault((b.follow, b.period), []).append((i, b))
    layers = []
    for (follow, period), group in groups.items():
        left = min(b.screen[0] + b.left for _, b in group)
        right = max(b.screen[0] + b.left + b.image.width for _, b in group)
        y0 = min(b.screen[1] + b.top for _, b in group)
        y1 = max(b.screen[1] + b.top + b.image.height for _, b in group)
        width = max(1, abs(period) or round(right - left))
        picture = Image.new('RGBA', (width, max(1, round(y1 - y0))))
        parts = []
        for i, b in group:
            x, y = round(b.screen[0] + b.left - left), round(b.screen[1] + b.top - y0)
            picture.alpha_composite(b.image, (x, y))
            if x + b.image.width > width:
                picture.alpha_composite(b.image, (x - width, y))
            parts.append((i, x, y, b.image.width, b.image.height))
        # A short sky band ends at the horizon screen's bottom; a tall band
        # is centred, giving both upward and downward look some artwork.
        shift = 240 - height if height <= 240 else (240 - height) / 2
        layers.append(Panorama(picture, follow, y0 - top + shift, parts))
    return layers


def panorama_position(layer, camera_position, heading, pitch, turned=False):
    width = layer.image.width
    path = -camera_position[2] if turned else camera_position[0]
    look = (heading % 360) / 360 * width
    x = 160 - width / 2 - (path * layer.follow[0] + look) % width
    # Pitch stops at +/- 60 degrees and shifts at most a quarter-screen.
    # No camera-Y term: framing a tall model cannot push the sky off-screen.
    y = layer.top + max(-60., min(60., pitch))
    return x, y
