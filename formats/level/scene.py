"""Build a read-only level scene from an area's actual LDAR load context."""
from dataclasses import dataclass, field
import numpy as np
from PIL import ImageOps
from formats.level.apd import parse_apd
from formats.level.runtime import InitialPoseResolver
from formats.models.wmd import parse_wmd
from formats.models.four import rebuild_mesh
from psx.graphics import sprite_frames, render_sprite
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


@dataclass
class LevelScene:
    entries: list
    resources: list
    vram: object
    notes: list = field(default_factory=list)


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


def sprite_mesh(parts, vram, shard, position, flip, offset):
    image = render_sprite(parts, vram, shard=shard)
    left = min((p[13] for p in parts), default=0)
    top = min((p[14] for p in parts), default=0)
    if flip:
        image = ImageOps.mirror(image)
        left = -left - image.width
    x, y, z = np.asarray(position) * (1, -1, -1)
    return quad([(x+left,y-top,z),(x+left+image.width,y-top,z),
                 (x+left,y-top-image.height,z),(x+left+image.width,y-top-image.height,z)], image, offset=offset)


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
    texture = next((a for a in project.ldars[path][index].assets if a.kind == 'GRPX'
                    and a.rect and a.rect[2] >= 64 and a.rect[3] >= 256), None)
    if texture is None:
        texture = next((a for a in resources.values() if a.kind == 'GRPX'
                        and a.rect and a.rect[2] >= 64 and a.rect[3] >= 256), None)
    shard = (texture.rect[2], texture.rect[3], project.asset_data(texture)) if texture else None
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
            if mesh is None and 'sprite' in visual:
                bank, frame = visual['sprite'], visual['frame']
                if bank in sprites and frame < len(sprites[bank]) and sprites[bank][frame]:
                    mesh = sprite_mesh(sprites[bank][frame], vram, shard, placement.position,
                                       visual.get('flip', False), placement.offset)
                    category, note = 'Sprites', f'SPR bank {bank}, frame {frame}. Initial pose traced from the game code.'
            if mesh is None:
                mesh = marker(placement.position, placement.offset)
            entries.append(SceneEntry(f'{name} | {asset.code:04X} #{i:03d}', category, mesh,
                                      asset, placement, active, note))
    return LevelScene(entries, list(resources.values()), vram, notes)
