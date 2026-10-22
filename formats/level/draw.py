"""Objects drawn by the game's own draw code.

Each frame the game sorts its objects into lists by category and hands each
list to a routine that picks a draw routine by the object's draw mode and,
for some modes, by the area: the town sections (the overlays INFO, INFO2
and INFO3) draw mode 0D sprites their own way. The draw routines read the
SPR parts and turn them into GPU primitives with the object's texture page
offset, palette, mirroring, blending and shading applied.

Rather than restate those rules, an object here is drawn by those routines.
Its memory, as the level tracer leaves it, is copied into an R3000A and GTE
interpreter, the category's routine is called with a list holding only that
object, and the primitives it adds to the ordering table are read back. The
camera matrix is set so that the object's own position lands on a fixed
point of the screen at unit scale; what comes back is the object's picture
relative to its position, exactly as the game assembles it.

The category routines are found in each executable by what they read: every
one keeps the length of its list and the list itself in two scratchpad
words, the same in every build, next to the flag at 1F8001C6 that says the
lists were already built this frame.
"""
import bisect
import struct
from dataclasses import dataclass

import numpy as np

# Scratchpad words, the same in every build.
LIST_READY = 0x1F8001C6         # nonzero: the category lists were built this frame
LISTS = {1: (0x1F80024E, 0x1F80025C), 2: (0x1F800250, 0x1F800260), 3: (0x1F800252, 0x1F800264),
         4: (0x1F800254, 0x1F800268), 5: (0x1F800256, 0x1F80026C), 8: (0x1F800258, 0x1F800274),
         7: (0x1F80025A, 0x1F800270)}
# The words each routine takes its list from on the first pass of a frame,
# when 1F8001C6 is clear and it also notes the list for a second pass. The
# second pass draws some modes differently, so the capture takes the first.
BUILDING = {1: (0x1F800244, 0x1F800218), 2: (0x1F800246, 0x1F80021C), 3: (0x1F80024A, 0x1F800220),
            4: (0x1F80024C, 0x1F800224), 5: (0x1F800248, 0x1F800228), 7: (0x1F800240, 0x1F80022C),
            8: (0x1F800242, 0x1F800230)}
PACKETS, ORDERING = 0x1F800164, 0x1F8001E0      # next free primitive, ordering table
MATRIX = 0x1F8000C0                              # camera rotation and translation
CAMERA_ALONG, CAMERA_DEPTH = 0x1F8000EE, 0x1F8000F6
# Where the capture keeps its list, primitives and ordering table.
LIST_AT, PACKET_AT, TABLE_AT = 0x80380000, 0x80390000, 0x803C0000
TABLE_SLOTS = 0x2000
TABLE_BASE = TABLE_AT + 0x400 * 4                # room for negative depth biases
# The object's position is drawn at this screen point, at this depth.
ORIGINS = ((160, 120), (-96, 120), (416, 120), (160, -88), (160, 328))
SCREEN_DEPTH = 512
STACK = 0x803F0000
STEPS = 400000
def town_of(name):
    """The town renderer the category routines pick for draw mode 0D. The
    routine at 800310D0 of the European build sets it from the area and
    section each frame, which comes to the overlay the section loads: INFO,
    INFO2 or INFO3 (I0NFO to I8NFO3 by language on the European disc)."""
    import re
    match = re.fullmatch(r'I(?:\d)?NFO(\d?)\.BIN', name.upper())
    return int(match.group(1) or 1) if match else 0

_LOOPS = {}


def draw_loops(exe, base):
    """{category: routine address} and the town renderer byte, found in an
    executable (bytes with its 0x800 header). A routine is taken to start at
    the nearest jal target at or before an instruction."""
    key = (len(exe), hash(exe[0x800:0x10800]), base)
    if key in _LOOPS:
        return _LOOPS[key]
    words = np.frombuffer(exe, '<u4', (len(exe) - 0x800) // 4, 0x800)
    op = words >> 26
    targets = np.unique(0x80000000 | (words[op == 3] & 0x3FFFFFF) << 2)
    uses = {}
    upper = {}
    for i in np.nonzero((op == 15) | np.isin(op, (9, 0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B)))[0]:
        w = int(words[i])
        o, rs, rt, imm = w >> 26, w >> 21 & 31, w >> 16 & 31, w & 0xFFFF
        if o == 15:
            upper[rt] = (imm, i)
            continue
        hi = upper.get(rs)
        if hi is None or i - hi[1] > 24:
            continue
        address = (hi[0] << 16) + ((imm ^ 0x8000) - 0x8000) & 0xFFFFFFFF
        k = int(np.searchsorted(targets, base + 4 * int(i), 'right')) - 1
        if k >= 0:
            uses.setdefault(int(targets[k]), set()).add(address)
    loops = {}
    for category, (count, items) in LISTS.items():
        hits = [start for start, used in uses.items() if {count, items, LIST_READY} <= used]
        if len(hits) == 1:
            loops[category] = hits[0]
    # The town byte is the one RAM byte category 2's routine reads.
    town = None
    if 2 in loops:
        start = loops[2]
        for used in sorted(a for a in uses.get(start, ()) if 0x80010000 <= a < 0x80200000):
            town = used
            break
    _LOOPS[key] = (loops, town)
    return _LOOPS[key]


@dataclass
class Primitive:
    """One GPU primitive relative to the object's position: corners (x, y)
    in drawing order 0-1-2-3, texture coordinates, palette word, texture
    page word, the blend flag and mode, raw texture (no shading) and the
    shading colour."""
    corners: tuple
    uv: tuple = ()
    clut: int = 0
    tpage: int = 0
    blend: bool = False
    mode: int = 0
    raw: bool = False
    colour: tuple = (128, 128, 128)
    textured: bool = True
    sprite: bool = False        # a GPU sprite rectangle, which cannot be mirrored

    def key(self):
        return (self.corners, self.uv, self.clut, self.tpage, self.blend, self.mode,
                self.raw, self.colour, self.textured, self.sprite)


def _sxy(word):
    x, y = word & 0x7FF, word >> 16 & 0x7FF
    return (x - 0x800 if x & 0x400 else x, y - 0x800 if y & 0x400 else y)


def _uv(word):
    return word & 0xFF, word >> 8 & 0xFF


def command_size(words, at):
    """Words of the GP0 command at `at`, or 0 for one this does not know."""
    cmd = words[at] >> 24
    if cmd == 0 or cmd == 1 or 0xE1 <= cmd <= 0xE6:
        return 1
    if cmd == 2:
        return 3
    if 0x20 <= cmd <= 0x3F:
        textured, four, gouraud = cmd & 4, cmd & 8, cmd & 0x10
        corners = 4 if four else 3
        return 1 + corners * (1 + bool(textured) + bool(gouraud)) - bool(gouraud)
    if 0x40 <= cmd <= 0x5F:
        if cmd & 8:                     # a line through any number of points
            at2 = at + 1
            while at2 < len(words) and words[at2] & 0xF000F000 != 0x50005000:
                at2 += 1
            return at2 + 1 - at
        return 4 if cmd & 0x10 else 3
    if 0x60 <= cmd <= 0x7F:
        return (2 if cmd & 0x18 else 3) + bool(cmd & 4)
    if 0x80 <= cmd <= 0x9F:
        return 4
    return 0


def primitives(packets, origin):
    """[Primitive] from ordering table packets in drawing order, positions
    made relative to `origin`. A packet may hold several commands."""
    out, page = [], 0
    ox, oy = origin

    def at(word):
        x, y = _sxy(word)
        return x - ox, y - oy

    for packet in packets:
        i = 0
        while i < len(packet):
            size = command_size(packet, i)
            if not size or i + size > len(packet):
                break
            words = packet[i:i + size]
            i += size
            cmd = words[0] >> 24
            colour = (words[0] & 0xFF, words[0] >> 8 & 0xFF, words[0] >> 16 & 0xFF)
            blend, raw = bool(cmd & 2), bool(cmd & 1)
            if cmd == 0xE1:
                page = words[0] & 0x1FF
            elif 0x20 <= cmd <= 0x3F:
                gouraud, four, textured = bool(cmd & 0x10), bool(cmd & 8), bool(cmd & 4)
                step = 1 + textured + gouraud
                count = 4 if four else 3
                first = 1                       # the first corner's colour is in the command word
                xy = [at(words[first + k * step]) for k in range(count)]
                if textured:
                    uv = [_uv(words[first + 1 + k * step]) for k in range(count)]
                    clut, page = words[first + 1] >> 16, words[first + 1 + step] >> 16 & 0x1FF
                else:
                    uv, clut = [], 0
                if not four:
                    xy.append(xy[2])
                    if uv:
                        uv.append(uv[2])
                out.append(Primitive(tuple(xy), tuple(uv), clut, page, blend, page >> 5 & 3,
                                     raw or not textured, colour, textured))
            elif 0x60 <= cmd <= 0x7F:
                textured = bool(cmd & 4)
                x, y = at(words[1])
                sizes = {8: (1, 1), 0x10: (8, 8), 0x18: (16, 16)}
                w, h = sizes.get(cmd & 0x18) or (words[-1] & 0xFFFF, words[-1] >> 16)
                xy = ((x, y), (x + w, y), (x, y + h), (x + w, y + h))
                if textured:
                    u, v = _uv(words[2])
                    uv = ((u, v), (u + w, v), (u, v + h), (u + w, v + h))
                    out.append(Primitive(xy, uv, words[2] >> 16, page, blend, page >> 5 & 3, raw, colour, sprite=True))
                else:
                    out.append(Primitive(xy, (), 0, page, blend, page >> 5 & 3, True, colour, textured=False))
    return out


class DrawCapture:
    """Runs a category draw routine for one object in a copy of the level
    tracer's memory."""

    def __init__(self, exe, base, read, town=0):
        """`read(address, count)` reads the tracer's memory."""
        from psx.mips.cpu import CPU
        self.loops, self.town_byte = draw_loops(exe, base)
        self.read = read
        self.town = town
        self.cpu = CPU()
        self.loaded = False

    @property
    def available(self):
        return bool(self.loops)

    def load(self, regions):
        """Copy memory into the interpreter: [(address, bytes)], or
        [(address, count)] to read from the tracer."""
        cpu = self.cpu
        for address, data in regions:
            cpu.write(address, data if isinstance(data, (bytes, bytearray)) else self.read(address, data))
        self.loaded = True

    def capture(self, obj, state, scratch, category=None, frame_entry=None, memory=()):
        """Primitives the game draws for the object whose 0x200 bytes are
        `state`, at `obj`, with scratchpad `scratch`; `memory` is more
        [(address, bytes)] to put in place first. `frame_entry` replaces the
        object's current animation step by one showing that SPR frame.
        Returns [Primitive] or None when the routine did not finish."""
        if category is None:
            category = state[0x1C] & 0x7F
        loop = self.loops.get(category)
        if loop is None:
            return None
        cpu = self.cpu
        x, y, z = (struct.unpack_from('<h', state, at)[0] for at in (0x12, 0x16, 0x1A))
        seen, found = set(), []
        for origin in ORIGINS:
            cpu.write(0x1F800000, scratch[:0x400])
            for address, data in memory:
                cpu.write(address, data)
            cpu.write(obj, state)
            cpu.w8(obj + 1, 1)                       # on screen
            if frame_entry is not None:
                cpu.write(LIST_AT + 0x10, struct.pack('<4H', frame_entry, 0, 0, 1))
                cpu.w32(obj + 0x24, LIST_AT + 0x10)
            if self.town_byte:
                cpu.w8(self.town_byte, self.town)
            count, items = BUILDING[category]
            cpu.w16(LIST_READY, 0)
            cpu.w16(count, 1)
            cpu.w32(items, LIST_AT)
            cpu.w32(LIST_AT, obj)
            cpu.w32(PACKETS, PACKET_AT)
            cpu.w32(ORDERING, TABLE_BASE)
            # ClearOTagR: every slot links to the one below it.
            table = np.arange(TABLE_SLOTS, dtype=np.uint32) * 4 + (TABLE_AT & 0xFFFFFF) - 4
            table[0] = 0xFFFFFF
            cpu.write(TABLE_AT, table.astype('<u4').tobytes())
            # Identity rotation; the object's position goes to the screen
            # point at SCREEN_DEPTH, where one unit is one pixel.
            cpu.write(MATRIX, struct.pack('<9hh3i', 4096, 0, 0, 0, 4096, 0, 0, 0, 4096, 0,
                                          -x, -y, SCREEN_DEPTH - z))
            cpu.w16(CAMERA_ALONG, x & 0xFFFF)
            cpu.w16(CAMERA_DEPTH, z & 0xFFFF)
            gte = cpu.gte
            gte.write_ctrl(24, origin[0] << 16 & 0xFFFFFFFF)
            gte.write_ctrl(25, origin[1] << 16 & 0xFFFFFFFF)
            gte.write_ctrl(26, SCREEN_DEPTH)
            try:
                cpu.R[29] = STACK
                cpu.call(loop, max_instr=STEPS, sp=STACK)
            except Exception:
                return None if not found else found
            for prim in primitives(self.walk(), origin):
                if prim.key() not in seen:
                    seen.add(prim.key())
                    found.append(prim)
            if found and not any(self.clipped(p, origin) for p in found):
                break
        return found

    @staticmethod
    def clipped(prim, origin):
        """Whether a primitive lies near the screen's edge, where the
        routines leave out what does not show."""
        xs = [x + origin[0] for x, _ in prim.corners]
        ys = [y + origin[1] for _, y in prim.corners]
        return min(xs) < 8 or max(xs) > 312 or min(ys) < 8 or max(ys) > 232

    def walk(self):
        """Packets of the ordering table, far end first."""
        cpu, out = self.cpu, []
        at = (TABLE_AT + (TABLE_SLOTS - 1) * 4) & 0xFFFFFF
        steps = 0
        while at != 0xFFFFFF and steps < 100000:
            steps += 1
            tag = cpu.r32(0x80000000 | at)
            size = tag >> 24
            if size:
                out.append([cpu.r32(0x80000000 | at + 4 + 4 * k) for k in range(size)])
            at = tag & 0xFFFFFF
        return out


# Rendering ------------------------------------------------------------------

def _colours(words):
    r = (words & 31).astype(np.float32) * (255 / 31)
    g = (words >> 5 & 31).astype(np.float32) * (255 / 31)
    b = (words >> 10 & 31).astype(np.float32) * (255 / 31)
    return np.stack([r, g, b], -1)


def _texels(vram, tpage, clut, cache):
    """256 x 256 colour words of a texture page through a palette."""
    key = (tpage, clut)
    if key not in cache:
        x, y = (tpage & 15) * 64, (tpage >> 4 & 1) * 256
        depth = tpage >> 7 & 3
        yy = (np.arange(256) + y) % 512
        px = np.arange(256)
        if depth >= 2:
            words = vram[np.ix_(yy, (px + x) % 1024)]
        else:
            per = 4 if depth == 0 else 2
            raw = vram[np.ix_(yy, (x + px // per) % 1024)]
            index = (raw >> ((px % per) * (16 // per))) & (15 if depth == 0 else 255)
            cx, cy = (clut & 63) * 16, clut >> 6 & 511
            palette = vram.reshape(-1)[(cy * 1024 + cx + np.arange(16 if depth == 0 else 256)) % vram.size]
            words = palette[index]
        cache[key] = words
    return cache[key]


def render(prims, vram, layer=None):
    """(RGBA image, left, top) of primitives over nothing; left and top are
    the image's offset from the object's position. None when nothing is
    drawn.

    `layer` picks part of the picture: 'solid' for the texels drawn as they
    are, or a blend mode (0 to 3) for the texels blended that way, as their
    own colour, to be blended with the scene behind. By default blended
    texels are mixed with what the sprite itself draws under them."""
    from PIL import Image
    if not prims:
        return None
    xs = [x for p in prims for x, _ in p.corners]
    ys = [y for p in prims for _, y in p.corners]
    left, top = min(xs), min(ys)
    width, height = max(xs) - left, max(ys) - top
    if not (0 < width <= 2048 and 0 < height <= 2048):
        return None
    canvas = np.zeros((height, width, 4), np.float32)
    cache = {}
    for prim in prims:
        corners = [(x - left, y - top) for x, y in prim.corners]
        covered = np.zeros((height, width), bool)
        for tri in ((0, 1, 2), (1, 2, 3)):
            _triangle(canvas, prim, [corners[k] for k in tri],
                      [prim.uv[k] for k in tri] if prim.textured else None, vram, cache, covered, layer)
    image = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8), 'RGBA')
    return image, left, top


def blend_modes(prims):
    """The blend modes some of these primitives are drawn with."""
    return sorted({prim.mode for prim in prims if prim.blend})


def _triangle(canvas, prim, xy, uv, vram, cache, covered=None, layer=None):
    (x0, y0), (x1, y1), (x2, y2) = xy
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if area == 0:
        return
    h, w = canvas.shape[:2]
    lo_x, hi_x = max(0, min(x0, x1, x2)), min(w, max(x0, x1, x2))
    lo_y, hi_y = max(0, min(y0, y1, y2)), min(h, max(y0, y1, y2))
    if lo_x >= hi_x or lo_y >= hi_y:
        return
    gy, gx = np.mgrid[lo_y:hi_y, lo_x:hi_x]
    px, py = gx + 0.5, gy + 0.5
    # Barycentric weights; the GPU fills the pixels whose centres are
    # inside, leaving the right and bottom edges out.
    w0 = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
    w1 = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
    w2 = 1 - w0 - w1
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if covered is not None:
        region_covered = covered[lo_y:hi_y, lo_x:hi_x]
        inside &= ~region_covered
        region_covered |= inside
    if not inside.any():
        return
    if uv is None:
        colour = np.array(prim.colour, np.float32) * (255 / 255)
        rgb = np.broadcast_to(colour, inside.shape + (3,))
        solid = inside
        blended = inside if prim.blend else np.zeros_like(inside)
    else:
        (u0, v0), (u1, v1), (u2, v2) = uv
        # Corner texture coordinates name texel centres; a rectangle's far
        # edge is one past its last texel.
        u = np.floor(w0 * u0 + w1 * u1 + w2 * u2 - 1e-4).astype(np.int64) % 256
        v = np.floor(w0 * v0 + w1 * v1 + w2 * v2 - 1e-4).astype(np.int64) % 256
        words = _texels(vram, prim.tpage, prim.clut, cache)[v, u]
        solid = inside & (words != 0)
        rgb = _colours(words)
        if not prim.raw:
            rgb = np.clip(rgb * (np.array(prim.colour, np.float32) / 128), 0, 255)
        blended = solid & bool(prim.blend) & (words >> 15 == 1)
    region = canvas[lo_y:hi_y, lo_x:hi_x]
    if layer is not None:
        shown = solid & ~blended if layer == 'solid' else blended if prim.mode == layer else None
        if shown is not None:
            region[..., :3][shown] = rgb[shown]
            region[..., 3][shown] = 255
        return
    back = region[..., :3].astype(np.int16) >> 3
    front = rgb.astype(np.int16) >> 3
    if prim.mode == 0:
        mixed = (back >> 1) + (front >> 1)
    elif prim.mode == 1:
        mixed = back + front
    elif prim.mode == 2:
        mixed = back - front
    else:
        mixed = back + (front >> 2)
    mixed = np.clip(mixed, 0, 31).astype(np.uint8)
    region[..., :3][solid] = rgb[solid]
    region[..., :3][blended] = ((mixed << 3) | (mixed >> 2))[blended]
    region[..., 3][solid] = 255
