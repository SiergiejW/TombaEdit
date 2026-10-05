"""Camera-facing sprite cards and restrained backdrop motion."""
import math
import numpy as np


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
