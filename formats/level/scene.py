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


@dataclass
class LevelScene:
    entries: list
    resources: list
    vram: object
    notes: list = field(default_factory=list)
    # Collision overlay as GL line arrays: (vertices, colours), both N x 3.
    collision: tuple = None


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
    """Collision spans as line segments. `banks` is [(Whm, x0, z0)]. A plane
    is a 90 unit slice of depth and a column is 8 units of X; see whm.py."""
    vertices, colours = [], []
    for whm, x0, z0 in banks:
        for plane in whm.planes:
            z = -(z0 + plane.index * PLANE_DEPTH + PLANE_DEPTH / 2)
            for span in plane.spans:
                x = x0 + span.column * 8
                if span.wall:
                    vertices += [(x + 4, -span.y0, z), (x + 4, -span.y1, z)]
                    colour = (.85, .45, .15)
                else:
                    vertices += [(x, -span.y0, z), (x + 8, -(span.y0 + span.y1), z)]
                    colour = (.35, 1., .35) if span.attribute == 1 else (1., .3, .9)
                colours += [colour, colour]
    if not vertices:
        return None
    return np.asarray(vertices, np.float32), np.asarray(colours, np.float32)


def build_scene(project, path, index):
    resources = loaded_resources(project, path, index)
    vram = project.vram(path, index)
    entries, notes, models, sprites = [], [], {}, {}
    area = int(path.split('LDAR')[-1].split('.')[0])
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
                images[key] = render_sprite(sprites[bank][frame], vram, tpage=visual.get('tpage', 0),
                                            clut=visual.get('clut'))
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
    x0, z0 = resolver.collision_origin(area, index - 1)
    for (kind, slot), asset in resources.items():
        if kind != 'WHM':
            continue
        try:
            # Area 0 keeps the near planes in slot 1 and continues 270 units
            # deeper in slot 0 (US routine 80042654); elsewhere slot 0 is used.
            banks.append((parse_whm(project.asset_data(asset)), x0,
                          z0 + (270 if area == 0 and slot == 0 and ('WHM', 1) in resources else 0)))
        except FormatError as exc:
            notes.append(f'{asset.label}: {exc}')
    return LevelScene(entries, list(resources.values()), vram, notes, collision_lines(banks))
