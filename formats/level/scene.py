"""Build a read-only level scene from an area's actual LDAR load context."""
from dataclasses import dataclass, field
import numpy as np
from PIL import ImageOps
from formats.level.apd import parse_apd
from formats.level.runtime import InitialPoseResolver
from formats.models.wmd import parse_wmd
from formats.models.four import rebuild_mesh
from psx.graphics import sprite_frames, render_sprite
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


@dataclass
class LevelScene:
    entries: list
    resources: list
    vram: object
    notes: list = field(default_factory=list)
    # Collision overlay as GL line arrays: (vertices, colours), both N x 3.
    collision: tuple = None


def area_of(path):
    """Area number of an LDARnn.BIN path; -1 for the system load table."""
    stem = path.split('/')[-1].split('.')[0]
    return int(stem[4:]) if stem.startswith('LDAR') and stem[4:].isdigit() else -1


def loaded_resources(project, path, index):
    resources = {}
    groups = project.ldars[path]
    for group in ([groups[0]] if index == 0 else [groups[0], groups[index]]):
        for asset in group.assets:
            resources[asset.kind, (asset.code >> 8) & 15] = asset
    return resources


def translated(mesh, position):
    offset = np.asarray(position) * (1, -1, -1)
    return rebuild_mesh([dict(p, vertices=np.asarray(p['vertices']) + offset)
                         for p in mesh.polygons], mesh.offset, mesh.image)


def quad(vertices, image=None, color=(1, 1, 1), offset=0):
    polygon = dict(offset=offset, vertices=vertices, uv=[(0, 0), (1, 0), (0, 1), (1, 1)],
                   colors=[color] * 4, page=-2 if image is not None else -1,
                   clut=0, command=0x2C if image is not None else 0x28, kind='FT4' if image is not None else 'F4')
    return rebuild_mesh([polygon], offset, image)


def marker(position, offset):
    x, y, z = np.asarray(position) * (1, -1, -1)
    return quad([(x-5,y,z),(x,y+8,z),(x,y-8,z),(x+5,y,z)], color=(1,.5,.15), offset=offset)


def sprite_mesh(image, parts, position, flip, offset):
    left = min((p[13] for p in parts), default=0)
    top = min((p[14] for p in parts), default=0)
    if flip:
        image = ImageOps.mirror(image)
        left = -left - image.width
    x, y, z = np.asarray(position) * (1, -1, -1)
    return quad([(x+left,y-top,z),(x+left+image.width,y-top,z),
                 (x+left,y-top-image.height,z),(x+left+image.width,y-top-image.height,z)], image, offset=offset)


def collision_lines(banks):
    """Collision spans as line segments. `banks` is [(Whm, x0, z0, step)].
    Plane n lies at depth z0 + n * step, which is where the objects that
    walk on it are placed, and a column is 8 units of X; see whm.py.
    Surfaces are drawn as they slope; solid ranges only by their outline,
    since every column of a hillside carries one."""
    vertices, colours = [], []

    def line(a, b, colour):
        vertices.extend((a, b))
        colours.extend((colour, colour))

    def covered(ranges, y):
        return any(low <= y <= high for low, high in ranges)

    for whm, x0, z0, step in banks:
        for plane in whm.planes:
            z = -(z0 + plane.index * step)
            previous = []
            for column in plane.columns + [[]]:
                x = x0 + (column[0].column if column else len(plane.columns)) * 8
                solid = []
                for span in column:
                    if span.wall:
                        solid.append(span.extent)
                        line((x, -span.y0, z), (x + 8, -span.y0, z), SOLID)
                        line((x, -span.y1, z), (x + 8, -span.y1, z), SOLID)
                    else:
                        line((x, -span.y0, z), (x + 8, -(span.y0 + span.y1), z),
                             SURFACE if span.attribute == 1 else SPECIAL)
                # A vertical edge wherever this column is solid and its
                # neighbour is not, or the other way round.
                edges = sorted({y for low, high in previous + solid for y in (low, high)})
                for low, high in zip(edges, edges[1:]):
                    middle = (low + high) / 2
                    if covered(previous, middle) != covered(solid, middle):
                        line((x, -low, z), (x, -high, z), SOLID)
                previous = solid
    if not vertices:
        return None
    return np.asarray(vertices, np.float32), np.asarray(colours, np.float32)


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


def build_scene(project, path, index):
    resources = loaded_resources(project, path, index)
    vram = project.vram(path, index)
    entries, notes, models, sprites = [], [], {}, {}
    area = area_of(path)
    resolver = InitialPoseResolver(project, area, max(0, index-1), resources)
    slots = resolver.placement_slots(area, index-1) if resolver.available and index else None
    notes.append(resolver.reason)
    notes.append('Initial state preview. Event conditions and scripted spawns are not simulated. Orange markers have unresolved visuals.')
    for (kind, slot), asset in resources.items():
        try:
            if kind == 'WMD':
                models[slot] = parse_wmd(project.asset_data(asset))
                if slot == 0:
                    for i, mesh in enumerate(models[slot]):
                        entries.append(SceneEntry(f'Geometry {i:03d}', 'Geometry', mesh, asset))
            elif kind == 'SPR':
                sprites[slot] = sprite_frames(project.asset_data(asset))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    images = {}

    def sprite_image(bank, frame, visual):
        key = (bank, frame, visual.get('tpage'), visual.get('clut'))
        if key not in images:
            try:
                image = render_sprite(sprites[bank][frame], vram, tpage=visual.get('tpage', 0),
                                      clut=visual.get('clut'))
                # A blank result means the pixels are uploaded while the game
                # runs; the placement keeps its marker instead.
                images[key] = image if image.getbbox() else None
            except FormatError:
                images[key] = None
        return images[key]

    for (kind, slot), asset in resources.items():
        if kind != 'APD':
            continue
        try:
            placements = parse_apd(project.asset_data(asset))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
            continue
        for i, placement in enumerate(placements):
            active = slots is None or slot == slots[0] or (slot == slots[1] and
                         placement.section in (index-1, ~(index-1)))
            name = f'Object {placement.layer}:{placement.kind:02X} / {placement.variant:02X}'
            mesh, category, note = None, 'Unresolved', 'Visual link is unresolved; position comes from APD.'
            visual = resolver.resolve(placement) if active else {}
            model_ref = visual.get('model', placement.model)
            if model_ref:
                bank, model = model_ref
                if bank in models and model < len(models[bank]):
                    mesh = translated(models[bank][model], placement.position)
                    category, note = 'Models', f'WMD bank {bank}, model {model}. Translation from APD; dynamic rotation is not simulated.'
            frames = []
            if mesh is None and 'sprite' in visual and visual['sprite'] in sprites:
                bank, flip = visual['sprite'], visual.get('flip', False)
                for frame, ticks in visual['frames']:
                    parts = sprites[bank][frame] if frame < len(sprites[bank]) else None
                    image = sprite_image(bank, frame, visual) if parts else None
                    if image is not None:
                        frames.append((sprite_mesh(image, parts, placement.position, flip,
                                                   placement.offset), ticks))
                if frames:
                    mesh = frames[0][0]
                    category = 'Sprites'
                    note = (f'SPR bank {bank}, frame {visual["frames"][0][0]}, texture page base '
                            f'0x{visual.get("tpage", 0):X}. '
                            + (f'{len(frames)} animation steps, {sum(t for _, t in frames)} ticks per pass.'
                               if len(frames) > 1 else 'Single-frame pose.'))
                    if len(frames) < 2:
                        frames = []
            if mesh is None:
                mesh = marker(placement.position, placement.offset)
            entries.append(SceneEntry(f'{name} | {asset.code:04X} #{i:03d}', category, mesh,
                                      asset, placement, active, note, frames))
    banks = []
    x0, z0, step = resolver.collision_frame(area, index - 1)
    for (kind, slot), asset in resources.items():
        if kind != 'WHM':
            continue
        try:
            # Area 0 keeps the near planes in slot 1 and continues 270 units
            # deeper in slot 0 (US routine 80042654); elsewhere slot 0 is used.
            deeper = 3 * step if area == 0 and slot == 0 and ('WHM', 1) in resources else 0
            banks.append((parse_whm(project.asset_data(asset)), x0, z0 + deeper, step))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    town = town_picture(project, resources, notes)
    if town:
        entries.insert(0, town)
    collision = collision_lines(banks)
    if collision is None and town is not None and getattr(town, 'cells', None) is not None:
        collision = town_lines(town.cells)
    return LevelScene(entries, list(resources.values()), vram, notes, collision)


def sprite_pages(project, path, index):
    """Texture page bases by SPR slot and frame, {slot: {frame: base}}, taken
    from every object the load group places. The SPR viewer uses them to draw
    a bank the way the level does."""
    cache = project.__dict__.setdefault('sprite_page_cache', {})
    if (path, index) not in cache:
        resources = loaded_resources(project, path, index)
        resolver = InitialPoseResolver(project, area_of(path), max(0, index - 1), resources)
        pages = {}
        for (kind, slot), asset in resources.items():
            if kind != 'APD' or not resolver.available:
                continue
            try:
                placements = parse_apd(project.asset_data(asset))
            except FormatError:
                continue
            for placement in placements:
                visual = resolver.resolve(placement)
                if 'sprite' in visual:
                    for frame, _ in visual['frames']:
                        pages.setdefault(visual['sprite'], {}).setdefault(frame, visual['tpage'])
        cache[path, index] = pages
    return cache[path, index]
