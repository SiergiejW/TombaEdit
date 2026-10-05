"""Build a read-only level scene from an area's actual LDAR load context."""
from dataclasses import dataclass, field
import numpy as np
from PIL import Image, ImageOps
from formats.level.apd import parse_apd
from formats.level.runtime import InitialPoseResolver
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


def area_of(path):
    """Area number of an LDARnn.BIN path; -1 for the system load table."""
    stem = path.split('/')[-1].split('.')[0]
    return int(stem[4:]) if stem.startswith('LDAR') and stem[4:].isdigit() else -1


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
    None when the pages they name hold nothing."""
    left, top = min(p[1] for p in pieces), min(p[2] for p in pieces)
    image = Image.new('RGBA', (max(p[1] + p[5] for p in pieces) - left, max(p[2] + p[6] for p in pieces) - top))
    pages = {}
    for tpage, x, y, u, v, width, height, clut in pieces:
        try:
            if (tpage, clut) not in pages:
                pages[tpage, clut] = texture_page(vram, tpage, clut)
        except FormatError:
            continue
        image.alpha_composite(pages[tpage, clut].crop((u, v, u + width, v + height)), (x - left, y - top))
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
    backdrops = []
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
            model_frames = []
            mesh, category, note = None, 'Unresolved', 'Visual link is unresolved; position comes from APD.'
            visual = resolver.resolve(placement) if active else {}
            model_ref = visual.get('model', placement.model)
            if model_ref:
                bank, model = model_ref
                if bank in models and model < len(models[bank]):
                    mesh = placed_model(models[bank][model], placement.position, visual)
                    category, note = 'Models', (f'WMD bank {bank}, model {model}. '
                        f'Initial scale {visual.get("scale", (4096, 4096, 4096))}, '
                        f'rotation {visual.get("rotation", (0, 0, 0))} (4096 units per turn).')
                    versions = resolver.model_animation(placement) if active else []
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
                            note = (f'WMD bank {bank}, model {model}, rewritten by its handler: '
                                    f'{len(model_frames)} versions, {sum(t for _, t in model_frames)} ticks per cycle.')
            frames, frames_first = [], None
            if mesh is None and 'sprite' in visual and visual['sprite'] in sprites:
                bank, flip = visual['sprite'], visual.get('flip', False)
                where = placement.position
                if visual.get('anchored'):
                    # Screen-list objects that keep pace with the camera count
                    # their Y from the top of the screen, a screen above where
                    # the level's own objects would put it. They belong to the
                    # picture behind them and sit just in front of it.
                    where = (where[0], where[1] - 240, where[2] + 1)
                for frame, ticks in visual['frames']:
                    parts = sprites[bank][frame] if frame < len(sprites[bank]) else None
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
                    if bank in pictures:
                        note += ' Pixels decoded from the matching WPP animation bank.'
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
                        # Both frames hang from the same anchor.
                        both = parts + bank[extra]
                        left, top = min(p[13] for p in both), min(p[14] for p in both)
                        joined = Image.new('RGBA', (max(p[13] + p[9] for p in both) - left,
                                                    max(p[14] + p[10] for p in both) - top))
                        for layer_parts, layer in ((parts, image), (bank[extra], over)):
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
                mesh = marker(placement.position, placement.offset)
            entry = SceneEntry(f'{name} | {asset.code:04X} #{i:03d}', category, mesh,
                               asset, placement, active, note, frames)
            entry.handler = resolver.handler_address(placement)
            entry.animation_address = visual.get('animation_address')
            entries.append(entry)
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
                    [entry.note], sky=(0., 0., 0.), locations=locations, location_index=index)))
    return scene


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
