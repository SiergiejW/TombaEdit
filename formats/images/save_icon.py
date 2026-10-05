"""The title frame of a memory card save.

A save file opens with `SC`, a byte saying how many icon frames follow
(0x11 one, 0x12 two, 0x13 three) and how many blocks the save takes. The
title is 64 bytes of Shift-JIS at offset 4. A sixteen colour palette is at
0x60 and the icon frames, 16 x 16 at four bits a pixel, start at 0x80.
"""
import numpy as np
from PIL import Image
from psx.graphics import rgba


def frames(data):
    return max(1, min(3, data[2] & 3)) if data[:2] == b'SC' else 0


def title(data):
    text = bytes(data[4:68]).split(b'\0')[0]
    try:
        return text.decode('shift_jis').strip()
    except UnicodeDecodeError:
        return text.decode('shift_jis', 'replace').strip()


def icons(data):
    """The icon's frames as RGBA images."""
    palette = np.frombuffer(data, '<u2', 16, 0x60)
    out = []
    for n in range(frames(data)):
        start = 0x80 + n * 0x80
        if start + 0x80 > len(data):
            break
        packed = np.frombuffer(data, np.uint8, 128, start).reshape(16, 8)
        indices = np.empty((16, 16), np.uint8)
        indices[:, 0::2], indices[:, 1::2] = packed & 15, packed >> 4
        out.append(Image.fromarray(rgba(palette[indices])))
    return out


def sheet(data, scale=8):
    """All frames side by side, enlarged, for a still preview."""
    pictures = icons(data)
    if not pictures:
        return Image.new('RGBA', (16 * scale, 16 * scale))
    out = Image.new('RGBA', ((16 * len(pictures) + 4 * (len(pictures) - 1)) * scale, 16 * scale))
    for n, picture in enumerate(pictures):
        out.alpha_composite(picture.resize((16 * scale, 16 * scale), Image.NEAREST), (n * 20 * scale, 0))
    return out
