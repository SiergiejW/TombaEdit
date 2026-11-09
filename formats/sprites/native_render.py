"""Display captured original draw commands without palette or page substitution.

The command capture is native; rasterization remains the editor's software
renderer. A transparent isolated sprite has no scene framebuffer for blending.
"""
from PIL import Image
import numpy as np
from formats.level.draw import Primitive, render
from disc.reader import FormatError


def load_vram(project, path, index, screen=None):
    """Only explicit ordered LDAR uploads, with a mask of initialized words.

    No conditional effects picture, town CLUT, guessed runtime palette or
    data from a different section is injected. Unknown VRAM stays unknown,
    even though its storage is zeroed to make software rendering deterministic.
    """
    from formats.archive.ldar import system_table, area_number
    groups = project.ldars[path]
    wanted = [(groups[0], 0)]
    if index:
        wanted.append((groups[index], 0))
    if screen is not None:
        wanted.append((project.ldars[system_table(path)][screen], 0))
    system = project.ldars.get(system_table(path))
    if system and area_number(path) >= 0:
        wanted.insert(0, (system[0], 256))
    vram = np.zeros((512, 1024), np.uint16)
    loaded = np.zeros(vram.shape, bool)
    for group, top in wanted:
        for asset in group.assets:
            if not asset.rect or asset.rect[1] < top:
                continue
            x, y, width, height = asset.rect
            if not (0 <= x < 1024 and 0 <= y < 512 and 0 < width <= 1024 - x and 0 < height <= 512 - y):
                raise FormatError('Native VRAM upload extends outside 1024 x 512 words')
            pixels = np.frombuffer(project.asset_data(asset), '<u2')
            if pixels.size != width * height:
                raise FormatError('Native VRAM upload size differs from its rectangle')
            vram[y:y + height, x:x + width] = pixels.reshape(height, width)
            loaded[y:y + height, x:x + width] = True
    return vram, loaded


def packets_loaded(packets, loaded):
    """Conservative coverage check for every texture/CLUT read of a packet.

    Rectangle bounds include all texels of each primitive's UV extent. This
    may reject a triangle with unloaded texels outside it, never invent them.
    """
    for value in packets:
        p = Primitive(**value) if isinstance(value, dict) else value
        if not p.textured:
            continue
        if not p.uv:
            return False
        page, depth = p.tpage, p.tpage >> 7 & 3
        per_word = 4 if depth == 0 else 2 if depth == 1 else 1
        u, v = zip(*p.uv)
        # Polygon corners name inclusive texel centres in packets, while
        # GPU rectangle commands carry an exclusive far edge. Including the
        # polygon's last corner is conservative for both rasterizers.
        us = np.arange(min(u), max(u) + (0 if p.sprite and max(u) > min(u) else 1)) % 256
        vs = np.arange(min(v), max(v) + (0 if p.sprite and max(v) > min(v) else 1)) % 256
        if not us.size or not vs.size:
            return False
        xs = ((page & 15) * 64 + us // per_word) % 1024
        ys = (((page >> 4) & 1) * 256 + vs) % 512
        if not loaded[np.ix_(ys, xs)].all():
            return False
        if depth < 2:
            cx, cy = (p.clut & 63) * 16, p.clut >> 6 & 511
            count = 16 if depth == 0 else 256
            positions = (cy * 1024 + cx + np.arange(count)) % loaded.size
            if not loaded.reshape(-1)[positions].all():
                return False
    return True


class PacketRenderer:
    def __init__(self, packets, vram):
        self.packets, self.vram, self.cache = packets, vram, {}

    def picture(self, index):
        if index not in self.cache:
            primitives = [Primitive(**p) if isinstance(p, dict) else p
                          for p in self.packets.get(index, ())]
            self.cache[index] = render(primitives, self.vram)
        return self.cache[index]

    def __call__(self, index, overrides=None):
        if overrides:
            raise ValueError('Native draw traces do not accept palette substitutions')
        result = self.picture(index)
        return result[0] if result else Image.new('RGBA', (1, 1))


def packet_renderer(packets, vram):
    return PacketRenderer(packets, vram)


def command_records(packets, evidence):
    """All captured variants remain inspectable, even with unresolved VRAM."""
    for frame in sorted(set(packets) | set(evidence)):
        item = evidence.get(frame, {})
        contexts = [c for c in item.get('contexts', ()) if c.get('draw_commands')]
        if not contexts and frame in packets:
            contexts = [dict(source='', draw_commands=packets[frame])]
        for context in contexts:
            for number, packet in enumerate(context['draw_commands']):
                yield frame, item.get('status', 'unresolved'), context.get('source', ''), number, packet
