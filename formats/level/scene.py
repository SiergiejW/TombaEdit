"""Build a read-only level scene from an area's actual LDAR load context."""
from dataclasses import dataclass, field, replace
import struct
import numpy as np
from PIL import Image, ImageOps
from formats.level.apd import parse_apd, Placement
from formats.level.runtime import InitialPoseResolver, OBJECT
# At most this many spawned objects are added to a section.
SPAWN_LIMIT = 160
from formats.level.draw import render as render_primitives
from formats.models.wmd import parse_wmd
from formats.models.four import rebuild_mesh
from psx.graphics import sprite_frames, render_sprite, texture_page
from formats.collision.whm import parse_whm, PLANE_DEPTH
from disc.reader import FormatError


SURFACE, SPECIAL, SOLID = (.35, 1., .35), (1., .3, .9), (1., .6, .15)


@dataclass
class SceneEntry:
    name: str
    category: str
    mesh: object
    source: object
    placement: object = None
    active: bool = True
    note: str = ''
    # Animated sprites: [(mesh, ticks)] for one pass of the object's script.
    frames: list = field(default_factory=list)
    # A second mesh the viewer can swap in, such as a town's tinted picture.
    alternative: object = None
    handler: int = None
    animation_address: int = None
    draw_bucket: float = 0
    class_name: str = ''    # what the class is, where it has been identified
    class_note: str = ''

    @property
    def class_label(self):
        """The class as listed: its layer and type, and its name if known."""
        return f'{self.object_class} {self.class_name}'.strip()

    @property
    def object_class(self):
        """What kind of thing this is: the APD layer and type of a placed
        object, which pick its routine, or what the entry is otherwise."""
        if self.placement is not None:
            return f'{self.placement.layer}:{self.placement.kind:02X}'
        return 'Town' if self.name == 'Town picture' else self.category

    @property
    def color(self):
        """(r, g, b) the entry is marked in: its dot in the list, its marker
        and its selection outline."""
        return class_color(self.placement)


@dataclass
class Backdrop:
    """A layer 7 sprite. `anchor` is its placement and `screen` where that
    lands on the 320 x 240 screen with the camera at the origin; `follow` is
    the fraction of camera movement it scrolls by on each axis."""
    image: object
    left: int
    top: int
    anchor: tuple
    screen: tuple
    follow: tuple
    period: int = 0     # screen pixels after which it repeats sideways; 0 for never


@dataclass
class LevelScene:
    entries: list
    resources: list
    vram: object
    notes: list = field(default_factory=list)
    # Collision overlay as GL line arrays: (vertices, colours), both N x 3.
    collision: tuple = None
    # Backdrop sprites, drawn behind everything in screen space: one
    # (entry index, Backdrop) per layer 7 placement that resolved.
    backdrop: list = field(default_factory=list)
    # Colour to clear the view with while the backdrop is shown, or None.
    sky: tuple = None
    collision_records: list = field(default_factory=list)
    collision_context: str = ''
    locations: list = field(default_factory=list)
    location_index: int = 0
    town_views: list = field(default_factory=list)
    # Where the build loads the area's code overlay; 0 when not known.
    overlay: int = 0
    view_2d: bool = False
    # Updates a second, each stepping every animation once: one a field,
    # 50 on the European disc and 60 on the others.
    rate: int = 60


def area_of(path):
    """Area number of a load table's path; -1 for a system load table."""
    from formats.archive.ldar import area_number
    return area_number(path)


def loaded_resources(project, path, index):
    resources = {}
    groups = project.ldars[path]
    for group in ([groups[0]] if index == 0 else [groups[0], groups[index]]):
        for asset in group.assets:
            resources[asset.kind, asset.slot] = asset
    return resources


def translated(mesh, position):
    offset = np.asarray(position) * (1, -1, -1)
    return rebuild_mesh([dict(p, vertices=np.asarray(p['vertices']) + offset)
                         for p in mesh.polygons], mesh.offset, mesh.image)


def placed_model(mesh, position, visual):
    """Apply the object's initial PSX scale and rotation before placement."""
    from formats.level.presentation import model_vertices
    placed = rebuild_mesh([dict(p, vertices=model_vertices(p['vertices'], position,
                        visual.get('scale', (4096, 4096, 4096)),
                        visual.get('rotation', (0, 0, 0))))
                         for p in mesh.polygons], mesh.offset, mesh.image)
    placed.front_clockwise = getattr(mesh, 'front_clockwise', True)
    return placed


def model_preview(mesh, visual):
    """Keep an uninitialized lit model inspectable without inventing a material."""
    if (not visual.get('lit') or not mesh.polygons or
            any(p['page'] >= 0 or np.any(p['colors']) for p in mesh.polygons)):
        return mesh, False
    # Some reusable meshes contain only positions until runtime setup fills
    # their colour/normal fields. Grey is an explicit inspection fallback.
    faces = []
    for p in mesh.polygons:
        points = np.asarray(p['vertices'], np.float64)
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        length = np.linalg.norm(normal)
        amount = abs(np.dot(normal / length, (0.3, 0.8, 0.52))) if length else 0
        grey = 0.35 + 0.3 * amount
        faces.append(dict(p, colors=np.full((len(points), 3), grey, np.float32)))
    shown = rebuild_mesh(faces, mesh.offset, mesh.image)
    shown.front_clockwise = getattr(mesh, 'front_clockwise', True)
    return shown, True


def quad(vertices, image=None, color=(1, 1, 1), offset=0):
    polygon = dict(offset=offset, vertices=vertices, uv=[(0, 0), (1, 0), (0, 1), (1, 1)],
                   colors=[color] * 4, page=-2 if image is not None else -1,
                   clut=0, command=0x2C if image is not None else 0x28, kind='FT4' if image is not None else 'F4')
    return rebuild_mesh([polygon], offset, image)


# The level's own geometry, which has no class to tell apart.
AREA_COLOR = (0.75, 0.75, 0.78)
GOLDEN_RATIO_CONJUGATE = 0.6180339887498949


def class_color(placement):
    """One colour per object class, as Tomba2Edit marks them: a walk round
    the hue wheel by the golden ratio, so classes numbered next to each
    other land far apart. Every object of a class shares it."""
    if placement is None:
        return AREA_COLOR
    import colorsys
    number = placement.layer * 97 + placement.kind
    return colorsys.hsv_to_rgb(number * GOLDEN_RATIO_CONJUGATE % 1.0, 0.7, 1.0)


def marker(position, offset, color=(1, .5, .15)):
    x, y, z = np.asarray(position) * (1, -1, -1)
    return quad([(x-5,y,z),(x,y+8,z),(x,y-8,z),(x+5,y,z)], color=color, offset=offset)


def sprite_mesh(image, parts, position, flip, offset):
    left = min((p[13] for p in parts), default=0)
    top = min((p[14] for p in parts), default=0)
    if flip:
        image = ImageOps.mirror(image)
        left = -left - image.width
    return placed_sprite(image, left, top, position, offset)


def placed_sprite(image, left, top, position, offset):
    """A sprite picture whose top left corner is (left, top) from the
    object's position, in screen pixels."""
    x, y, z = np.asarray(position) * (1, -1, -1)
    mesh = quad([(x+left,y-top,z),(x+left+image.width,y-top,z),
                 (x+left,y-top-image.height,z),(x+left+image.width,y-top-image.height,z)], image, offset=offset)
    mesh.billboard_anchor = np.asarray((x, y, z))
    return mesh


def edge_colour(image):
    """Most common colour along the first row of an image that has any
    pixels: the sky a backdrop was painted to fade into."""
    from collections import Counter
    pixels = np.asarray(image.convert('RGBA'))
    rows = np.nonzero(pixels[..., 3].any(axis=1))[0]
    if not len(rows):
        return None
    row = pixels[rows[0]]
    colour, _ = Counter(map(tuple, row[row[:, 3] > 0][:, :3].tolist())).most_common(1)[0]
    return tuple(c / 255 for c in colour)


def fixed_picture(pieces, vram):
    """Assemble the rectangles of a mode 2 backdrop: (image, left, top), or
    None when the pages they name hold nothing.

    The routine (8004E244) adds each rectangle to the front of one draw
    list, so the last in the table is drawn first and the first ends up on
    top. A rectangle with the blend flag mixes its marked texels with what
    is under them by the mode in its texture page word; over nothing, they
    are left half clear."""
    left, top = min(p[1] for p in pieces), min(p[2] for p in pieces)
    image = Image.new('RGBA', (max(p[1] + p[5] for p in pieces) - left, max(p[2] + p[6] for p in pieces) - top))
    pages = {}

    def page(tpage, clut, flagged=None):
        if (tpage, clut, flagged) not in pages:
            pages[tpage, clut, flagged] = texture_page(vram, tpage, clut, flagged=flagged)
        return pages[tpage, clut, flagged]

    for tpage, x, y, u, v, width, height, clut, blend in reversed(pieces):
        box, at = (u, v, u + width, v + height), (x - left, y - top)
        try:
            if not blend:
                image.alpha_composite(page(tpage, clut).crop(box), at)
                continue
            image.alpha_composite(page(tpage, clut, False).crop(box), at)
            front = np.asarray(page(tpage, clut, True).crop(box)).astype(np.float32)
        except FormatError:
            continue
        region = (at[0], at[1], at[0] + width, at[1] + height)
        back = np.asarray(image.crop(region)).astype(np.float32)
        marked, under = front[..., 3] > 0, back[..., 3] > 0
        mode = tpage >> 5 & 3
        mixed = (back[..., :3] / 2 + front[..., :3] / 2 if mode == 0 else back[..., :3] + front[..., :3] if mode == 1
                 else back[..., :3] - front[..., :3] if mode == 2 else back[..., :3] + front[..., :3] / 4)
        out = back.copy()
        both = marked & under
        out[both, :3] = np.clip(mixed[both], 0, 255)
        alone = marked & ~under
        out[alone, :3] = front[alone, :3]
        out[alone, 3] = 128
        image.paste(Image.fromarray(out.astype(np.uint8), 'RGBA'), region[:2])
    return (image, left, top) if image.getbbox() else None


def collision_lines(banks):
    """Compatibility wrapper for verified WHM boundary geometry."""
    from formats.collision.geometry import records, lines
    return lines([row for whm, x0, z0, turned in banks
                  for row in records(whm, x0, z0, turned)])


def orient_assemblies(entries):
    # Relative APD records can assemble one closed object from open panels.
    # The AP box's panels have the opposite winding from most WMD models.
    from formats.models.winding import closed_winding
    assembled = []
    for entry in entries:
        if entry.placement is None:
            continue
        mode = entry.placement.raw[15] & 3
        if mode == 1:
            assembled = []
        if entry.category == 'Models':
            assembled.append(entry.mesh)
        else:
            assembled = []
        if mode == 3 and assembled:
            winding = closed_winding(assembled)
            if winding is not None:
                for mesh in assembled:
                    mesh.front_clockwise = winding
            assembled = []


def cell_colours():
    """One translucent colour per cell value; 0 stays clear. Values with bit
    7 set share a blue cast so they read as one group."""
    import colorsys
    table = np.zeros((256, 4), np.uint8)
    for value in range(1, 256):
        hue = (.62 + (value & 127) * .02) % 1 if value & 0x80 else (value * .13) % .5
        r, g, b = colorsys.hsv_to_rgb(hue, .85, 1.)
        table[value] = (int(r * 255), int(g * 255), int(b * 255), 110)
    return table


def town_picture(project, resources, notes):
    """Town sections are a pre-rendered picture (CLM slot 15) with a map of
    8 x 8 pixel cells over it (CLM slot 14). Returns a scene entry holding
    the picture, with the picture tinted by the cell map as its alternative
    frame, or None for ordinary sections."""
    from formats.sprites.wpp import parse_tim
    picture, cells = resources.get(('CLM', 15)), resources.get(('CLM', 14))
    if picture is None:
        return None
    try:
        tim = parse_tim(project.asset_data(picture))
    except FormatError:
        return None                 # slot 15 holds other data in some areas
    image = tim.image(tim.cluts.reshape(-1) if tim.cluts is not None else None)
    opaque = np.asarray(image).copy()
    opaque[..., 3] = 255
    from PIL import Image
    image = Image.fromarray(opaque)
    tinted = image
    if cells is not None:
        data = project.asset_data(cells)
        width, height = np.frombuffer(data, '<u2', 2)
        if 4 + int(width) * int(height) <= len(data):
            grid = np.frombuffer(data, np.uint8, int(width) * int(height), 4).reshape(height, width)
            overlay = Image.fromarray(cell_colours()[grid]).resize((width * 8, height * 8), Image.NEAREST)
            tinted = image.copy()
            tinted.alpha_composite(overlay.crop((0, 0, image.width, image.height)))
            used = sorted(set(grid.reshape(-1).tolist()) - {0})
            notes.append('Town map cell values: ' + ' '.join(f'{v:02X}' for v in used)
                         + '. Blue cells have bit 7 set.')
    # Placements in a town are pixel positions on the picture.
    corners = [(0, 0, -1), (image.width, 0, -1), (0, -image.height, -1), (image.width, -image.height, -1)]
    entry = SceneEntry('Town picture', 'Geometry', quad(corners, image), picture,
                       note=f'{image.width} x {image.height} pre-rendered picture. '
                            'Town map shows it tinted by the 8 x 8 cell map.')
    entry.alternative = quad(corners, tinted)
    entry.draw_bucket = float('inf')
    entry.cells = grid if cells is not None and tinted is not image else None
    return entry


def town_lines(grid):
    """Outline of a town's cell map: green where walkable ground meets
    blocked cells, magenta between cells of different non-zero values."""
    vertices, colours = [], []
    height, width = grid.shape
    padded = np.zeros((height + 1, width + 1), np.uint8)
    padded[:height, :width] = grid
    for y in range(height):
        for x in range(width):
            here = int(grid[y, x])
            for other, a, b in ((int(padded[y, x + 1]), (x + 1, y), (x + 1, y + 1)),
                                (int(padded[y + 1, x]), (x, y + 1), (x + 1, y + 1))):
                if here != other:
                    colour = SURFACE if not here or not other else SPECIAL
                    vertices += [(a[0] * 8, -a[1] * 8, 0), (b[0] * 8, -b[1] * 8, 0)]
                    colours += [colour, colour]
            # The map's own top and left edges.
            if here and x == 0:
                vertices += [(0, -y * 8, 0), (0, -(y + 1) * 8, 0)]
                colours += [SURFACE, SURFACE]
            if here and y == 0:
                vertices += [(x * 8, 0, 0), ((x + 1) * 8, 0, 0)]
                colours += [SURFACE, SURFACE]
    if not vertices:
        return None
    return np.asarray(vertices, np.float32), np.asarray(colours, np.float32)


@dataclass
class ScriptSource:
    """Stands where a scene entry's resource does, for what a script made."""
    label: str
    code: int = 0xC000
    kind: str = 'WSS'


def scripted_placements(project, resolver, area, section):
    """[(source, [(Placement, ScriptObject)])] for the objects the section's
    event scripts create."""
    if not resolver.available:
        return []
    from formats.script.events import section_scripts, script_objects
    out = []
    entrance = None
    for name, script in section_scripts(project, area, section):
        made = []
        for created in script_objects(name, script):
            position = created.position
            if any(created.from_player):
                # Placed next to Tomba: shown from where he enters.
                entrance = entrance or resolver.entrance(area, section) or (0, 0, 0)
                position = tuple(v + (entrance[axis] if created.from_player[axis] else 0)
                                 for axis, v in enumerate(position))
            made.append((Placement(created.offset, created.raw, position, extra=created.extra), created))
        if made:
            out.append((ScriptSource(name), made))
    return out


def build_scene(project, path, index):
    resources = loaded_resources(project, path, index)
    vram = project.vram(path, index)
    entries, notes, models, sprites = [], [], {}, {}
    geometry = []       # listed after the objects placed in it
    backdrops = []
    area = area_of(path)
    resolver = InitialPoseResolver(project, area, max(0, index-1), resources)
    from game.classes import class_name, class_note
    # Classes are named by the area whose code runs them.
    runtime = getattr(resolver, 'area', area)
    slots = resolver.placement_slots(area, index-1) if resolver.available and index else None
    notes.append(resolver.reason)
    notes.append('Initial state preview. Event conditions and scripted spawns are not simulated. Diamond markers, in the colour of their class, have unresolved visuals.')
    for (kind, slot), asset in resources.items():
        try:
            if kind == 'WMD':
                models[slot] = parse_wmd(project.asset_data(asset))
                if slot == 0:
                    for i, mesh in enumerate(models[slot]):
                        geometry.append(SceneEntry(f'Geometry {i:03d}', 'Geometry', mesh, asset))
            elif kind == 'SPR':
                sprites[slot] = sprite_frames(project.asset_data(asset))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    from formats.level.palettes import apply_model_palettes
    palette_rows = apply_model_palettes(resolver, vram, models)
    if palette_rows:
        notes.append(f'{palette_rows} model palette rows decoded from the area overlay.')
    images = {}
    from formats.sprites.wpp import parse_wpp, frame_image, bank_palettes
    pictures = {}
    for (family, slot), asset in resources.items():
        if family != 'WPP':
            continue
        try:
            kind, bank = parse_wpp(project.asset_data(asset))
        except FormatError:
            continue
        if kind == 'frames':
            for sprite_slot, frames in sprites.items():
                if len(frames) == len(bank):
                    pictures[sprite_slot] = bank

    drawn_pictures = {}

    def drawn_picture(placement, frame):
        """(image, left, top) of a frame as the game's draw routine
        assembles it for this object, or None."""
        prims = resolver.draw(placement, frame)
        if not prims:
            return None
        key = tuple(prim.key() for prim in prims)
        if key not in drawn_pictures:
            drawn_pictures[key] = render_primitives(prims, vram)
        return drawn_pictures[key]

    def sprite_image(bank, frame, visual):
        key = (bank, frame, visual.get('tpage'), visual.get('clut'))
        if key not in images:
            try:
                parts = sprites[bank][frame]
                if bank in pictures:
                    palettes = bank_palettes(vram, sprites[bank], bank == 0)
                    fallback = palettes[0][1] if palettes else None
                    rows = {}
                    for n, part in enumerate(parts):
                        clut = visual.get('clut')
                        clut = part[2] if clut is None else clut
                        x, y = (clut & 63) * 16, (clut >> 6) & 511
                        palette = vram[y, x:x + 16]
                        if palette.any():
                            rows[n] = palette
                    image = frame_image(pictures[bank][frame], parts, fallback, rows)
                else:
                    image = render_sprite(parts, vram, tpage=visual.get('tpage', 0),
                                          clut=visual.get('clut'))
                # Blank frames are timed steps too, for instance a blink.
                images[key] = image
            except FormatError:
                images[key] = None
        return images[key]

    batches = []
    for (kind, slot), asset in resources.items():
        if kind != 'APD':
            continue
        try:
            batches.append((slot, asset, parse_apd(project.asset_data(asset)), None))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    # What the section's event script creates is put through the same
    # object routines as what the placement lists hold.
    scripted = scripted_placements(project, resolver, area, index - 1) if index else []
    for source, made in scripted:
        batches.append((None, source, [placement for placement, _ in made], [created for _, created in made]))
    if scripted:
        notes.append(f'{sum(len(made) for _, made in scripted)} objects are created by the event script '
                     + ', '.join(source.label for source, _ in scripted)
                     + '. They are listed as event previews, at the place and with the animation the script gives them first.')
    # Objects no list places: what the section's controllers spawn when it
    # starts, and (below, as they are traced) what objects spawn.
    seen_spawns = set()

    def spawns(made, parent=None, origin=''):
        found = []
        for pool, address, state in made:
            if pool not in ('objects', 'models', 'backdrops') or len(seen_spawns) >= SPAWN_LIMIT:
                continue
            child = resolver.child(pool, address, state, parent, origin)
            key = (child.raw, child.position)
            if key not in seen_spawns:
                seen_spawns.add(key)
                found.append(child)
        return found

    controlled = 0
    entered = spawns(resolver.entry_spawns() if resolver.available and index else (),
                     origin='spawned when Tomba enters the section')
    if entered:
        controlled += len(entered)
        batches.append((None, ScriptSource('Tomba\'s entry', kind='ENTRY'), entered, None))
    for kind, variant, made in (resolver.controller_spawns() if resolver.available and index else ()):
        children = spawns(made, origin=f'section controller {kind:02X} / {variant:02X}')
        if children:
            controlled += len(children)
            batches.append((None, ScriptSource(f'Controller {kind:02X}/{variant:02X}', kind='CTRL'), children, None))
    if controlled:
        notes.append(f'{controlled} objects are spawned by the section\'s controllers and by Tomba\'s entry '
                     'when it starts; they are listed as spawned objects.')
    for slot, asset, placements, created in batches:
        for i, placement in enumerate(placements):
            active = (created is not None or bool(placement.origin) or slots is None or slot == slots[0] or (
                slot == slots[1] and placement.section in (index-1, ~(index-1))))
            name = f'Object {placement.layer}:{placement.kind:02X} / {placement.variant:02X}'
            model_frames = []
            mesh, category, note = None, 'Unresolved', 'Visual link is unresolved; position comes from APD.'
            if slots and slot == slots[1] != slots[0] and created is None:
                # Records of the area-wide list carry their room number in
                # +6B without the one the section's own list subtracts.
                placement = replace(placement, extra=placement.extra + ((0x6B, bytes((placement.raw[15] >> 2,))),))
            visual = resolver.resolve(placement) if active else {}
            if visual.get('spawned') and placement.origin.count('spawned by') < 2:
                state = resolver.object_states.get((placement.raw, placement.position))
                label = class_name(runtime, placement.layer, placement.kind) or f'{placement.layer}:{placement.kind:02X}'
                children = spawns(visual['spawned'], (OBJECT, state) if state else None,
                                  f'spawned by {label} at {placement.position}'
                                  + (f', {placement.origin}' if placement.origin else ''))
                if children:
                    batches.append((None, ScriptSource(f'Spawned by {label}', kind='SPAWN'), children, None))
            # A prefilled APD model pointer is not a draw instruction. Town
            # controllers reuse these records for invisible triggers too.
            model_ref = visual.get('model') if resolver.available and active and placement.layer != 8 else placement.model
            if model_ref:
                bank, model = model_ref
                if bank in models and model < len(models[bank]):
                    source_mesh, neutral = model_preview(models[bank][model], visual)
                    mesh = placed_model(source_mesh, placement.position, visual)
                    category, note = 'Models', (f'WMD bank {bank}, model {model}. '
                        f'Initial scale {visual.get("scale", (4096, 4096, 4096))}, '
                        f'rotation {visual.get("rotation", (0, 0, 0))} (4096 units per turn).')
                    if neutral:
                        note += (' Stored colour fields are zero before runtime setup. Neutral inspection shading; '
                                 'the game material is not yet reconstructed.')
                    versions = resolver.model_animation(placement) if active else []
                    writer = None
                    if active and neutral and not versions:
                        versions, writer = resolver.model_colour_animation(placement, (bank, model))
                    if versions:
                        # The handler rewrites the model as it runs; each
                        # version is decoded in place of the stored one.
                        source = project.asset_data(resources['WMD', bank])
                        start = models[bank][model].offset
                        for data, ticks in versions[:32]:
                            try:
                                edited = parse_wmd(source[:start] + data + source[start + len(data):])[model]
                            except FormatError:
                                model_frames = []
                                break
                            model_frames.append((placed_model(edited, placement.position, visual), ticks))
                        if len(model_frames) > 1:
                            mesh = model_frames[0][0]
                            note = (f'WMD bank {bank}, model {model}, rewritten by its handler: '
                                    f'{len(model_frames)} versions, {sum(t for _, t in model_frames)} ticks per cycle.')
                            if writer:
                                note += f' Runtime colour writer 0x{writer:08X}; stored mesh colours are initially empty.'
            frames, frames_first = [], None
            if mesh is None and 'sprite' in visual and visual['sprite'] in sprites:
                visual = resolver.animation_preview(placement, visual) if active else visual
                bank, flip = visual['sprite'], visual.get('flip', False)
                where = visual.get('position', placement.position)
                if visual.get('anchored'):
                    # Screen-list objects that keep pace with the camera count
                    # their Y from the top of the screen, a screen above where
                    # the level's own objects would put it. They belong to the
                    # picture behind them and sit just in front of it.
                    where = (where[0], where[1] - 240, where[2] + 1)
                # Most sprites are drawn here by the game's own draw routine
                # (formats.level.draw); the rest from their SPR parts.
                assembled = placement.layer != 7 and not visual.get('anchored')
                drawn = 0
                for frame, ticks in visual['frames']:
                    parts = sprites[bank][frame] if frame < len(sprites[bank]) else None
                    picture = drawn_picture(placement, frame) if assembled and parts else None
                    if picture is not None:
                        image, left, top = picture
                        frames.append((placed_sprite(image, left, top, where, placement.offset), ticks))
                        drawn += 1
                        continue
                    image = sprite_image(bank, frame, visual) if parts else None
                    if image is not None:
                        frames_first = frames_first or (parts, image)
                        frames.append((sprite_mesh(image, parts, where, flip, placement.offset), ticks))
                if frames and any(mesh.image.getbbox() for mesh, _ in frames):
                    mesh = frames[0][0]
                    category = 'Sprites'
                    note = (f'SPR bank {bank}, frame {visual["frames"][0][0]}, texture page base '
                            f'0x{visual.get("tpage", 0):X}. '
                            + (f'{len(frames)} animation steps, {sum(t for _, t in frames)} ticks per pass.'
                               if len(frames) > 1 else 'Single-frame pose.'))
                    if drawn:
                        note += ' Assembled by the game\'s own draw routine.'
                    if visual.get('animation_preview'):
                        note += (f' Handler animation preview 0x{visual["animation_preview"]:08X}; '
                                 'initialization holds a pose. AI transitions and movement are not simulated.')
                    elif assembled and resolver.town and visual.get('shade') == 0:
                        category = 'Event previews'
                        note += (' Its shade +6B is 0, so the town does not draw it yet; shown from its'
                                 ' SPR parts only with Event previews enabled.')
                    if bank in pictures:
                        note += ' Pixels decoded from the matching WPP animation bank.'
                    if 'position' in visual:
                        note += f' Attached pose at {visual["position"]}, calculated by its handler from the parent object.'
                    if len(frames) < 2:
                        frames = []
                    if visual.get('condition'):
                        category = 'Event previews'
                        note += ' ' + visual['condition']
                elif frames:
                    frames = []
                    note = 'Sprite link is known, but its pixels or palette are not loaded in this section.'
            if frames_first is not None and placement.layer == 7 and 'screen' in visual:
                parts, image = frames_first
                extra = visual.get('overlay', 0)
                bank = sprites[visual['sprite']]
                if 0 < extra < len(bank) and bank[extra]:
                    over = sprite_image(visual['sprite'], extra, visual)
                    if over is not None:
                        # Both frames hang from the same anchor, the second
                        # raised by the object's word +20 (draw routine
                        # 8011E778 of area 4's overlay).
                        rise = visual.get('overlay_rise', 0)
                        raised = [part[:14] + (part[14] - rise,) for part in bank[extra]]
                        both = parts + raised
                        left, top = min(p[13] for p in both), min(p[14] for p in both)
                        joined = Image.new('RGBA', (max(p[13] + p[9] for p in both) - left,
                                                    max(p[14] + p[10] for p in both) - top))
                        for layer_parts, layer in ((parts, image), (raised, over)):
                            joined.alpha_composite(layer, (min(p[13] for p in layer_parts) - left,
                                                           min(p[14] for p in layer_parts) - top))
                        parts, image = both, joined
                ax, ay = placement.position[:2]
                sx, sy = visual['screen']
                follow = visual['follow']
                left = min(p[13] for p in parts)
                backdrops.append((len(entries), Backdrop(image, left, min(p[14] for p in parts),
                                                         (ax, ay), (sx, sy), follow,
                                                         visual.get('period', 0))))
                mesh, frames, category = rebuild_mesh([], placement.offset, image), [], 'Backgrounds'
                note = (f'Backdrop sprite: SPR bank {visual["sprite"]}, frame {visual["frames"][0][0]}. Drawn behind '
                        f'the level, following {follow[0]:.3g} of camera movement across and {follow[1]:.3g} down.')
            if len(model_frames) > 1:
                frames = model_frames
            pieces = resolver.picture_parts(placement) if mesh is None and active else []
            if pieces:
                picture = fixed_picture(pieces, vram)
                if picture is not None:
                    image, left, top = picture
                    x, y, z = placement.position
                    # The camera word these objects subtract is the world Y of
                    # the bottom of the 240-line screen, while their own Y
                    # counts from its top, so the picture sits a screen higher
                    # than its placement reads.
                    y -= 240
                    # Anchored to the level and drawn behind what stands in it.
                    corners = [(x + left, -(y + top), -z - 2), (x + left + image.width, -(y + top), -z - 2),
                               (x + left, -(y + top) - image.height, -z - 2),
                               (x + left + image.width, -(y + top) - image.height, -z - 2)]
                    mesh, category = quad(corners, image, offset=placement.offset), 'Backgrounds'
                    note = f'Fixed picture of {len(pieces)} rectangles, {image.width} x {image.height}, drawn behind the section.'
            if mesh is None:
                mesh = marker(placement.position, placement.offset, class_color(placement))
            if placement.origin:
                name = f'Spawned {placement.layer}:{placement.kind:02X} / {placement.variant:02X}'
                category = 'Spawned' if category in ('Sprites', 'Models', 'Unresolved') else category
                note = f'Not placed by a list: {placement.origin}. ' + note
            if created is not None:
                made = created[i]
                name = f'Script object {made.slot} | class {made.kind} / {made.subtype:02X}'
                category = 'Event previews'
                where = ', '.join(f'Tomba {v:+d}' if made.from_player[axis] else str(v)
                                  for axis, v in enumerate(made.position))
                note = (f'Created by {made.script} at {made.offset:04X}: CreateObject({made.slot}, {made.kind}, '
                        f'{made.subtype}, {where}), then animation {made.animation} from frame {made.frame}. '
                        + ('Placed next to Tomba; shown from where he enters the section. ' if any(made.from_player) else '')
                        + note)
            entry = SceneEntry(f'{name} | {asset.label} #{i:03d}' if created is not None
                               else f'{name} | {asset.code:04X} #{i:03d}', category, mesh,
                               asset, placement, active, note, frames)
            entry.handler = resolver.handler_address(placement)
            entry.class_name = class_name(runtime, placement.layer, placement.kind)
            entry.class_note = class_note(runtime, placement.layer, placement.kind)
            entry.animation_address = visual.get('animation_address')
            from formats.level.flat import ordering_bucket
            entry.draw_bucket = ordering_bucket(placement, visual, fixed_picture=bool(pieces))
            entries.append(entry)
    entries.extend(geometry)
    orient_assemblies(entries)
    from formats.collision.geometry import records, lines
    collision_records = []
    x0, z0, turned, only = resolver.collision_frame(area, index - 1)
    for (kind, slot), asset in resources.items():
        if kind != 'WHM' or only not in (None, slot) or not resolver.available:
            continue
        try:
            # Area 0 keeps the near planes in slot 1 and continues 270 units
            # deeper in slot 0 (US routine 80042654); elsewhere slot 0 is used.
            deeper = 3 * PLANE_DEPTH if area == 0 and index < 4 and slot == 0 and ('WHM', 1) in resources else 0
            whm = parse_whm(project.asset_data(asset))
            collision_records.extend(records(whm, x0, z0 + deeper, turned, asset))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    if resolver.available and area == 3 and index in (2, 6) and ('WHM', 1) in resources:
        asset = resources['WHM', 1]
        alt_x, alt_z, alt_turned, _ = resolver.collision_frame(area, index - 1, alternate=True)
        try:
            alternate = records(parse_whm(project.asset_data(asset)), alt_x, alt_z, alt_turned, asset)
            for record in alternate:
                record.route = 'Alternate mountain route'
            collision_records.extend(alternate)
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    town = town_picture(project, resources, notes)
    if town:
        entries.insert(0, town)
        backdrops = [(index + 1, backdrop) for index, backdrop in backdrops]
    collision = lines([r for r in collision_records if r.route == 'Default route'])
    if collision is None and town is not None and getattr(town, 'cells', None) is not None:
        collision = town_lines(town.cells)
    # The art stops where the game's clear colour takes over. That colour is
    # not stored with the section, so the top edge of the highest piece of
    # scenery stands in for it.
    sky = None
    if backdrops:
        highest = min((b for _, b in backdrops), key=lambda b: b.screen[1] + b.top)
        sky = edge_colour(highest.image)
    else:
        picture = next((e for e in entries if e.active and e.note.startswith('Fixed picture')), None)
        if picture is not None:
            sky = edge_colour(picture.mesh.image)
    context = (f'Path: {"Z" if turned else "X"}, origin {x0}; depth: {"-X" if turned else "Z"}, origin {z0}. '
               'Each WHM plane is a 2D X/Y test, selected by depth in 90-unit slices. '
               'First entrance orientation; changing entrance can change the active bank.')
    if not resolver.available:
        context = 'World collision origins are not verified for this executable. Open a WHM asset for its local X/Y boundaries.'
    from game.areas import section_name
    locations = [(section_name(area, g.index - 1), path, g.index)
                 for g in project.ldars[path][1:] if g.assets]
    scene = LevelScene(entries, list(resources.values()), vram, notes, collision, backdrops, sky,
                       collision_records, context, locations, index)
    scene.overlay = resolver.build.overlay if resolver.available else 0
    scene.rate = 50 if resolver.available and resolver.build.name.startswith('European') else 60
    from formats.level.flat import is_flat
    scene.view_2d = is_flat(entries)
    if town is not None:
        from formats.level.town import town_graphics
        profile = town_graphics(project, resources, area, index - 1)
        if profile is not None:
            asset = resources['SPR', profile.bank]
            for name, frame in profile.houses:
                parts = sprites[profile.bank][frame]
                image = render_sprite(parts, vram, tpage=profile.pages[frame], clut=profile.cluts[frame])
                mesh = sprite_mesh(image, parts, (0, 0, 0), False, frame)
                entry = SceneEntry(name, 'Backgrounds', mesh, asset,
                    note=f'SPR {asset.code:04X} frame {frame} in {asset.source.path}. '
                         f'Texture page base {profile.pages[frame]}, CLUT 0x{profile.cluts[frame]:04X}. '
                         f'Cutaway artwork used within {profile.name}; characters are separate runtime sprites.')
                scene.town_views.append((name, LevelScene([entry], list(resources.values()), vram,
                    [entry.note], sky=(0., 0., 0.), locations=locations, location_index=index, view_2d=True)))
    return scene


def sprite_pages(project, path, index):
    """Texture page bases by SPR slot and frame, {slot: {frame: base}}, taken
    from every object the load group places. The SPR viewer uses them to draw
    a bank the way the level does."""
    cache = project.__dict__.setdefault('sprite_page_cache', {})
    palettes = project.__dict__.setdefault('sprite_clut_cache', {})
    owners = project.__dict__.setdefault('sprite_owner_cache', {})
    if (path, index) not in cache:
        resources = loaded_resources(project, path, index)
        resolver = InitialPoseResolver(project, area_of(path), max(0, index - 1), resources)
        pages, cluts, shown, built = {}, {}, {}, {}
        later = []      # (slot, frames, page base, CLUT, label) from what an object's code can go on to show
        kinds = {}      # class -> the (slot, page base) pairs its objects use
        counts = {}
        from game.classes import class_name
        runtime = getattr(resolver, 'area', area_of(path))
        placed = []
        for (kind, slot), asset in resources.items():
            if kind != 'APD' or not resolver.available:
                continue
            try:
                placed.append((parse_apd(project.asset_data(asset)), ''))
            except FormatError:
                continue
        # What the section's event script creates shows frames too, and so
        # does what its controllers and its objects spawn.
        for source, made in (scripted_placements(project, resolver, area_of(path), index - 1) if index else []):
            placed.append(([placement for placement, _ in made], f' ({source.label})'))
        spawned = set()

        def children(made, parent=None):
            out = []
            for pool, address, state in made:
                if pool in ('objects', 'models', 'backdrops') and len(spawned) < SPAWN_LIMIT:
                    child = resolver.child(pool, address, state, parent)
                    if (child.raw, child.position) not in spawned:
                        spawned.add((child.raw, child.position))
                        out.append(child)
            return out
        for _, _, made in (resolver.controller_spawns() if resolver.available and index else ()):
            placed.append((children(made), ' (spawned)'))
        if resolver.available and index:
            placed.append((children(resolver.entry_spawns()), ' (spawned)'))
        animations = {}
        styles = project.__dict__.setdefault('sprite_style_cache', {}).setdefault((path, index), {})
        for placements, origin in placed:
            for placement in placements:
                visual = resolver.resolve(placement)
                label = (class_name(runtime, placement.layer, placement.kind)
                         or f'class {placement.layer}:{placement.kind:02X}') + origin
                if visual.get('spawned') and origin.count('spawned') < 2:
                    state = resolver.object_states.get((placement.raw, placement.position))
                    placed.append((children(visual['spawned'], (OBJECT, state) if state else None),
                                   origin + ' (spawned)'))
                if 'sprite' in visual and visual.get('animation_address'):
                    users = animations.setdefault(visual['sprite'], {}).setdefault(visual['animation_address'], [])
                    if label not in users:
                        users.append(label)
                model = visual.get('model', placement.model)
                if model:
                    users = built.setdefault(model[0], {}).setdefault(model[1], [])
                    if label not in users:
                        users.append(label)
                if 'sprite' in visual:
                    for frame, _ in visual['frames']:
                        styles.setdefault(visual['sprite'], {}).setdefault(frame, visual)
                        pages.setdefault(visual['sprite'], {}).setdefault(frame, visual['tpage'])
                        users = shown.setdefault(visual['sprite'], {}).setdefault(frame, [])
                        if label not in users:
                            users.append(label)
                        if visual.get('clut') is not None:
                            cluts.setdefault(visual['sprite'], {}).setdefault(frame, visual['clut'] & 0x7FFF)
                    slot = visual['sprite']
                    if slot not in counts:
                        try:
                            counts[slot] = len(sprite_frames(project.asset_data(resources['SPR', slot])))
                        except (FormatError, KeyError):
                            counts[slot] = 0
                    assigned = resolver.code_animations(resolver.handler_address(placement), slot, counts[slot])
                    for address, script in assigned.items():
                        users = animations.setdefault(slot, {}).setdefault(address, [])
                        if label not in users:
                            users.append(label)
                    more = resolver.code_frames(resolver.handler_address(placement),
                                                visual.get('animation_address', 0), counts[slot])
                    more = set(more) | {f for script in assigned.values() for f in script.frames}
                    kinds.setdefault((placement.layer, placement.kind), set()).add((slot, visual['tpage']))
                    if more:
                        later.append((slot, more, visual['tpage'], visual.get('clut'), label,
                                      (placement.layer, placement.kind)))
        # Frames an object only shows later take its page and palette where
        # no object starts out showing them. A class whose objects use
        # different pages by variant is left out: which page goes with
        # which of its scripts cannot be told from one object.
        direct = {slot: set(frames) for slot, frames in pages.items()}
        coded = {}
        for slot, frames, page, clut, label, kind in later:
            if len(kinds[kind]) > 1:
                continue
            for frame in frames:
                if frame in direct.get(slot, ()):
                    continue
                pages.setdefault(slot, {}).setdefault(frame, page)
                coded.setdefault(slot, set()).add(frame)
                users = shown.setdefault(slot, {}).setdefault(frame, [])
                if label not in users:
                    users.append(label)
                if clut is not None:
                    cluts.setdefault(slot, {}).setdefault(frame, clut & 0x7FFF)
        project.__dict__.setdefault('sprite_coded_cache', {})[path, index] = coded
        cache[path, index] = pages
        palettes[path, index] = cluts
        owners[path, index] = shown
        project.__dict__.setdefault('model_owner_cache', {})[path, index] = built
        project.__dict__.setdefault('sprite_animation_cache', {})[path, index] = animations
    return cache[path, index]


def sprite_animations(project, path, index):
    """The animation scripts objects of a load group start on, {SPR slot:
    {script address: [class name]}}."""
    sprite_pages(project, path, index)
    return project.sprite_animation_cache[path, index]


def sprite_routines(project, path, index):
    """Pages and palettes of the sprites that objects nobody places would
    show: {slot: {frame: (page base, CLUT word or None)}}.

    Splashes, bursts, sparks and the like are created by other objects
    while the game runs, so no placement list names them, but each is an
    entry of the same tables of object routines. Every routine of the load
    group's code is run on a made-up object, for each type number and
    variant it might be given, and what it sets the object to show is
    noted. A type or variant the routine was never meant for can read past
    its tables, so where two answers differ the lower numbers win, and the
    result ranks below anything a placed object says."""
    cache = project.__dict__.setdefault('sprite_routine_cache', {})
    if (path, index) in cache:
        return cache[path, index]
    from formats.level.apd import Placement
    resources = loaded_resources(project, path, index)
    resolver = InitialPoseResolver(project, area_of(path), max(0, index - 1), resources)
    found = {}
    if resolver.available:
        counts = {}
        for (kind, slot), asset in resources.items():
            if kind == 'SPR':
                try:
                    counts[slot] = len(sprite_frames(project.asset_data(asset)))
                except FormatError:
                    pass
        resolver.stop_at_animation = False

        def shown(layer, kind, variant, choice):
            raw = bytearray(16)
            raw[1], raw[2], raw[3], raw[4] = layer, kind, choice, variant
            try:
                visual = resolver.attempt(Placement(0, bytes(raw), (0, 0, 0)), False)
            except Exception:
                return None
            if 'sprite' not in visual or visual['sprite'] not in counts:
                return None
            frames = [frame for frame, _ in visual['frames']]
            if not frames or max(frames) >= counts[visual['sprite']] or visual['tpage'] >= 32:
                return None
            return visual['sprite'], frames, visual['tpage'], visual.get('clut'), visual

        claims = {}
        for layer, table in resolver.build.tables.items():
            if layer == 8:
                continue
            for kind in range(0x80):
                routine = resolver.read_word(table + kind * 4)
                if not any(start <= routine < end for start, end in resolver.code):
                    continue
                misses = 0
                for variant in range(16):
                    first = shown(layer, kind, variant, 0)
                    if first is None:
                        misses += 1
                        if misses >= 4:
                            break
                        continue
                    misses = 0
                    for choice in range(4):
                        result = first if choice == 0 else shown(layer, kind, variant, choice)
                        if result is None:
                            break
                        slot, frames, page, clut, visual = result
                        for frame in frames:
                            rank = (variant, choice)
                            if frame not in claims.setdefault(slot, {}) or rank < claims[slot][frame][0]:
                                claims[slot][frame] = (rank, page, None if clut is None else clut & 0x7FFF,
                                                     dict(visual, handler=routine, layer=layer, kind=kind))
        found = {slot: {frame: (page, clut) for frame, (_, page, clut, _) in frames.items()}
                 for slot, frames in claims.items()}
        styles = project.__dict__.setdefault('sprite_style_cache', {}).setdefault((path, index), {})
        for slot, entries in claims.items():
            for frame, (_, _, _, visual) in entries.items():
                styles.setdefault(slot, {}).setdefault(frame, visual)
        animations = project.__dict__.setdefault('sprite_animation_cache', {}).setdefault((path, index), {})
        visited = set()
        for slot, entries in claims.items():
            for _, _, _, visual in entries.values():
                root = visual['handler']
                if (slot, root) in visited:
                    continue
                visited.add((slot, root))
                label = f'Handler 0x{root:08X} ({visual["layer"]}:{visual["kind"]:02X})'
                addresses = set(resolver.code_animations(root, slot, counts[slot]))
                addresses.add(visual['animation_address'])
                for address in addresses:
                    users = animations.setdefault(slot, {}).setdefault(address, [])
                    if label not in users:
                        users.append(label)
    cache[path, index] = found
    return found


def sprite_coded(project, path, index):
    """Frames whose page comes from what an object's code goes on to show,
    not from what it starts with: {slot: {frame}}."""
    sprite_pages(project, path, index)
    return project.sprite_coded_cache[path, index]


def sprite_owners(project, path, index):
    """Which classes of object show each frame, {slot: {frame: [name]}}: a
    frame is named for the things that are drawn with it. A class without a
    name is listed by its layer and type."""
    sprite_pages(project, path, index)
    return project.sprite_owner_cache[path, index]


def model_owners(project, path, index):
    """Which classes of object are built from each model, {WMD slot:
    {model: [name]}}."""
    sprite_pages(project, path, index)
    return project.model_owner_cache[path, index]


def sprite_cluts(project, path, index):
    """Palettes by SPR slot and frame, {slot: {frame: CLUT word}}, for the
    frames whose object draws them through a palette of its own instead of
    the one stored in their parts."""
    sprite_pages(project, path, index)
    return project.sprite_clut_cache[path, index]


def same_banks(project, data):
    """Load tables of other areas that hold this very sprite bank. Areas
    share enemies and items by carrying a copy of the bank each."""
    import hashlib
    index = project.__dict__.get('sprite_bank_index')
    if index is None:
        index = project.__dict__['sprite_bank_index'] = {}
        for path, groups in project.ldars.items():
            for group in groups:
                for asset in group.assets:
                    if asset.kind == 'SPR' and asset.source is not None:
                        try:
                            digest = hashlib.sha1(project.asset_data(asset)).digest()
                        except FormatError:
                            continue
                        index.setdefault(digest, [])
                        if path not in index[digest]:
                            index[digest].append(path)
    return index.get(hashlib.sha1(data).digest(), [])


def lend_palettes(project, path, index, frames, vram, cluts=None, data=None):
    """(VRAM, [(CLUT word, load table, group it came from)]) with the
    palettes a bank needs and this section has not loaded copied in from
    sections that have: the other sections of the area first, since a bank
    in the base group is shared and each section loads the palettes for
    what it shows of it, then the sections of any area that carries the
    same bank (`data`)."""
    from psx.graphics import palette_missing, palette_runtime
    wanted = {part[2] & 0x7FFF for frame in frames for part in frame} | set((cluts or {}).values())
    missing = sorted(word for word in wanted if not palette_runtime(word) and palette_missing(vram, word))
    lent = []
    if missing:
        vram = vram.copy()
        vrams = {}
        # Search this area's sections first. Only build the cross-area bank
        # index when a palette is still missing after that search.
        remaining = set(missing)
        for donors in ([path], None):
            if not remaining:
                break
            if donors is None:
                donors = [other for other in (same_banks(project, data) if data is not None else []) if other != path]
            for donor in donors:
                for group in project.ldars[donor][1:]:
                    if not group.assets or (donor, group.index) == (path, index):
                        continue
                    donor_vram = vrams.setdefault((donor, group.index), None)
                    if donor_vram is None:
                        donor_vram = vrams[donor, group.index] = project.vram(donor, group.index)
                    for word in list(remaining):
                        if not palette_missing(donor_vram, word):
                            x, y = (word & 63) * 16, (word >> 6) & 511
                            vram[y, x:x + 16] = donor_vram[y, x:x + 16]
                            lent.append((word, donor, group.index))
                            remaining.remove(word)
                    if not remaining:
                        break
                if not remaining:
                    break
    return vram, lent
