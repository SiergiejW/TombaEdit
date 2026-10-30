"""The plan of a cut top-down village, with what each resident says.

Section 0 of AREA11, AREA16 and AREA17 has an empty load list, so the level view
shows nothing for it. Its residents, props and houses survive in the INFO2
overlay (formats.level.cut_towns); this draws them as a plan and lists each
resident with the messages its dialogue routine can open.

The plan is drawn from the data alone. The village's background picture, its
collision map and the sprite tables that say which drawing each subtype is were
not kept on the disc, so the plan has no background and most residents are marks.
The figure sheets the villages load are on the disc, and the tab shows them under
the plan. For the residents of the commonest subtype of each village the plan draws
the figure, with the palette that research on the PAL disc found for it (FIGURES).
"""
from dataclasses import dataclass, field
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from formats.level.cut_towns import CUT, EXITS, VILLAGES, WINDOWS, dialogue_cases, villages

SCALE = 2
MARGIN = 40
AREA_SETS = {area: number for number, (area, *_rest) in VILLAGES.items() if number in CUT}


@dataclass
class Row:
    number: int
    subtype: int
    where: str
    behaviour: str
    case: int
    messages: list = field(default_factory=list)    # [(entry index, text)]; entry None: not on this disc
    note: str = ''


@dataclass
class Preview:
    name: str
    area: int
    image: object
    rows: list
    notes: list
    sheets: list = field(default_factory=list)      # [Sheet]: the figure sheets of the village load groups
    places: dict = field(default_factory=dict)      # where a button can take the user: 'bank', 'group', 'overlay'
    village: object = None                          # what the plan is drawn from, to draw it again with a selection
    art: object = None


@dataclass
class Sheet:
    group: int              # group of the system load table
    words: object           # the 64 x 256 words of the first texture page: 4-bit figures, 256 x 256 texels
    palettes: list          # [(label, 16 colours)]: complete palettes of the area's CLUT files, best first
    best: int               # the palette shown first
    building_words: object = None       # the 384 x 256 words of pages 1 to 6: 8-bit pictures, 768 x 256 texels
    building_palettes: list = field(default_factory=list)   # [(label, 256 colours)], best first


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def patrol_box(village, r):
    """The box a resident walks in as world positions, or None for one that stands still."""
    x0, y0, x1, y1 = r.box
    if not r.behaviour or (x0, y0, x1, y1) == (0, 0, 0, 0):
        return None
    if village.set_number == 0x0E:      # Stonetown keeps its boxes relative to the resident
        return r.x + x0, r.y + y0, r.x + x1, r.y + y1
    return x0, y0, x1, y1


HIGHLIGHT = (0, 190, 255, 255)


@dataclass
class Backdrop:
    """A picture drawn under the plan: its top left corner at world position (x, y), `scale` per cent of a
    pixel of the picture to a unit of the world, `opacity` from 0 to 1."""
    image: object
    x: float
    y: float
    scale: float = 100.0
    opacity: float = 1.0

    @property
    def size(self):
        return self.image.width * self.scale / 100, self.image.height * self.scale / 100


def draw_plan(village, art=None, selected=(), hits=None, backdrop=None):
    """The plan of a village as an image: houses, patrol boxes, props and numbered residents.
    Residents `art` has a figure for are drawn as it; a stand-in is translucent. `selected` is a list of
    (kind, index), kind being 'resident', 'prop' or 'house' (index from 0), drawn highlighted. When `hits`
    is a list, (kind, index, (left, top, right, bottom)) is added to it for each element, in image pixels.
    A `backdrop` is drawn under everything and makes the plan big enough to show all of it."""
    chosen = set(selected)
    hits = [] if hits is None else hits
    boxes = [b for b in (patrol_box(village, r) for r in village.residents) if b]
    xs = ([r.x for r in village.residents] + [p.x for p in village.props] + [h[i] for h in village.houses for i in (0, 2)]
          + [b[i] for b in boxes for i in (0, 2)])
    ys = ([r.y for r in village.residents] + [p.y for p in village.props] + [h[i] for h in village.houses for i in (1, 3)]
          + [b[i] for b in boxes for i in (1, 3)])
    exits = EXITS.get(village.set_number, [])
    for (x0, y0, x1, y1), _where in exits:
        xs += [v for v in (x0, x1) if v is not None]
        ys += [v for v in (y0, y1) if v is not None]
    if backdrop is not None:
        xs += [backdrop.x, backdrop.x + backdrop.size[0]]
        ys += [backdrop.y, backdrop.y + backdrop.size[1]]
    left, top = min(xs) - MARGIN, min(ys) - MARGIN
    width, height = int((max(xs) + MARGIN - left) * SCALE), int((max(ys) + MARGIN - top) * SCALE)

    def at(x, y):
        return (x - left) * SCALE, (y - top) * SCALE
    image = Image.new('RGBA', (width, height), (226, 222, 210, 255))
    draw = ImageDraw.Draw(image)
    for gx in range(int(left) // 64 * 64, int(left + width / SCALE) + 64, 64):
        draw.line([at(gx, top), at(gx, top + height / SCALE)], fill=(214, 210, 198, 255))
    for gy in range(int(top) // 64 * 64, int(top + height / SCALE) + 64, 64):
        draw.line([at(left, gy), at(left + width / SCALE, gy)], fill=(214, 210, 198, 255))
    if backdrop is not None:
        picture = backdrop.image.convert('RGBA')
        size = (max(1, round(backdrop.size[0] * SCALE)), max(1, round(backdrop.size[1] * SCALE)))
        picture = picture.resize(size, Image.Resampling.NEAREST if backdrop.scale * SCALE >= 100 else Image.Resampling.LANCZOS)
        if backdrop.opacity < 1:
            picture.putalpha(picture.getchannel('A').point(lambda a: int(a * backdrop.opacity)))
        image.alpha_composite(picture, (round(at(backdrop.x, backdrop.y)[0]), round(at(backdrop.x, backdrop.y)[1])))
        draw = ImageDraw.Draw(image)
    label, small = _font(13), _font(11)
    for n, (x0, y0, x1, y1) in enumerate(village.houses, 1):
        draw.rectangle([at(x0, y0), at(x1, y1)], outline=(40, 110, 230, 255), width=2)
        draw.text((at(x0, y0)[0] + 4, at(x0, y0)[1] + 3), f'H{n}', fill=(40, 110, 230, 255), font=label)
        hits.append(('house', n - 1, (*at(x0, y0), *at(x1, y1))))
    for n, ((x0, y0, x1, y1), _where) in enumerate(exits):
        # An open side of an exit runs out to the edge of the map.
        x0, y0 = (left if x0 is None else x0), (top if y0 is None else y0)
        x1, y1 = (left + width / SCALE if x1 is None else x1), (top + height / SCALE if y1 is None else y1)
        shade = Image.new('RGBA', image.size, (0, 0, 0, 0))
        ImageDraw.Draw(shade).rectangle([*at(x0, y0), *at(x1, y1)], fill=(240, 130, 20, 50))
        image.alpha_composite(shade)
        draw = ImageDraw.Draw(image)
        draw.rectangle([*at(x0, y0), *at(x1, y1)], outline=(240, 130, 20, 255), width=3)
        draw.text((at(x0, y0)[0] + 5, at(x0, y0)[1] + 4), f'exit {n + 1}', fill=(200, 90, 0, 255), font=label)
        hits.append(('exit', n, (*at(x0, y0), *at(x1, y1))))
    for r in village.residents:
        box = patrol_box(village, r)
        if box:
            picked = ('resident', r.index) in chosen
            draw.rectangle([at(box[0], box[1]), at(box[2], box[3])], outline=(30, 160, 60, 255) if not picked else HIGHLIGHT,
                           width=2 if not picked else 4)
    for p in village.props:
        px, py = at(p.x, p.y)
        draw.rectangle([px - 4, py - 4, px + 4, py + 4], fill=(240, 190, 30, 255), outline=(120, 90, 0, 255))
        hits.append(('prop', p.index, (px - 5, py - 5, px + 5, py + 5)))
    for r in village.residents:
        px, py = at(r.x, r.y)
        colour = (150, 40, 190, 255) if r.room else (210, 30, 30, 255)
        lift = 0
        found = art.look_for(r.subtype) if art is not None else None
        if found is not None:
            look, stand_in = found
            figure = look.images[FACINGS.get(r.frame, 'front')]
            figure = figure.resize((figure.width * SCALE, figure.height * SCALE), Image.Resampling.NEAREST)
            if stand_in:
                figure = figure.copy()
                figure.putalpha(figure.getchannel('A').point(lambda a: int(a * STAND_IN_OPACITY)))
            image.alpha_composite(figure, (int(px - figure.width / 2), int(py - figure.height)))
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=colour)
            lift = figure.height - 22
        else:
            draw.line([(px, py), (px, py - 22)], fill=colour, width=2)
            draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=colour)
        draw.ellipse([px - 10, py - 34 - lift, px + 10, py - 14 - lift], fill=colour, outline=(255, 255, 255, 255))
        text = str(r.index + 1)
        box = draw.textbbox((0, 0), text, font=small)
        draw.text((px - (box[2] - box[0]) / 2 - box[0], py - 24 - lift - (box[3] - box[1]) / 2 - box[1]), text,
                  fill=(255, 255, 255, 255), font=small)
        half = figure.width / 2 if found is not None else 10
        hits.append(('resident', r.index, (px - max(half, 10), py - 34 - lift, px + max(half, 10), py + 3)))
    for kind, index in chosen:
        for k, i, (x0, y0, x1, y1) in hits:
            if (k, i) != (kind, index):
                continue
            if kind in ('house', 'exit'):
                shade = Image.new('RGBA', image.size, (0, 0, 0, 0))
                ImageDraw.Draw(shade).rectangle([x0, y0, x1, y1], fill=(0, 190, 255, 45))
                image.alpha_composite(shade)
                draw = ImageDraw.Draw(image)
                draw.rectangle([x0, y0, x1, y1], outline=HIGHLIGHT, width=4)
            else:
                draw.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], outline=HIGHLIGHT, width=3)
    return image


def hit_test(hits, x, y):
    """The (kind, index) of the element at an image pixel: residents before props before houses, the smallest first."""
    for kind in ('resident', 'prop', 'exit', 'house'):
        found = [((x1 - x0) * (y1 - y0), index) for k, index, (x0, y0, x1, y1) in hits
                 if k == kind and x0 <= x <= x1 and y0 <= y <= y1]
        if found:
            return kind, min(found)[1]
    return None


def describe(preview, selected):
    """A line about what is selected on the plan."""
    village = preview.village
    if not selected:
        return 'Click a resident, prop or house on the plan, or a row of the table, to select it. Click empty space to deselect.'
    if len(selected) > 1:
        return f'{len(selected)} residents selected.'
    kind, index = selected[0]
    if kind == 'resident':
        r, row = village.residents[index], preview.rows[index]
        return (f'Resident {row.number}: {row.where}, {row.behaviour}, subtype {r.subtype}, case {row.case}, '
                f'facing {r.frame}, at ({r.x}, {r.y}).')
    if kind == 'prop':
        q = village.props[index]
        return (f'Prop {index + 1}: subtype {q.subtype}, animation {q.animation}, type {q.kind}, '
                f'{"outdoors" if not q.room else f"inside house {q.room}"}, at ({q.x}, {q.y}).')
    if kind == 'exit':
        (x0, y0, x1, y1), where = EXITS[village.set_number][index]
        edge = lambda a, b: f'{a} {"beyond" if b is None else b}'
        return (f'Exit {index + 1}: leads to {where}. The game fires it when Tomba is inside '
                f'x {x0 if x0 is not None else "any"} to {x1 if x1 is not None else "any"}, '
                f'y {y0 if y0 is not None else "any"} to {y1 if y1 is not None else "any"}. Nothing leads back here.')
    x0, y0, x1, y1 = village.houses[index]
    inside = [r.index + 1 for r in village.residents if r.room == index + 1]
    return (f'House {index + 1}: from ({x0}, {y0}) to ({x1}, {y1}); residents inside: '
            f'{", ".join(map(str, inside)) if inside else "none"}.')


def _overlay(project):
    for groups in project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind == 'INS' and asset.source and 'NFO2' in asset.source.path.upper():
                    return project.asset_data(asset)
    return None


def _bank(project, path):
    """(Wfm, its asset) of the village's text bank, or (None, None)."""
    from formats.text.wfm import Wfm
    for asset in project.ldars[path][0].assets:
        if asset.kind == 'WFM' and asset.code >> 8 == 0xD0:
            try:
                return Wfm(project.asset_data(asset)), asset
            except Exception:
                return None, None
    return None, None


def _overlay_asset(project):
    for groups in project.ldars.values():
        for group in groups:
            for asset in group.assets:
                if asset.kind == 'INS' and asset.source and 'NFO2' in asset.source.path.upper():
                    return asset
    return None


def _village(project, path, index):
    """(executable, overlay, village) for the empty section a load-table group stands for, or None."""
    from formats.level.scene import area_of
    area = area_of(path)
    if index != 1 or area not in AREA_SETS or project.ldars[path][1].assets:
        return None
    from game.builds import executable
    found = executable(project)
    data = _overlay(project)
    if found is None or data is None:
        return None
    village = villages(data, found.build.overlay).get(AREA_SETS[area])
    return None if village is None else (found, data, village)


def available(project, path, index):
    """Whether the group is an empty section whose village survives in the overlay (no plan is drawn)."""
    return _village(project, path, index) is not None


# Per area: the group of the system load table whose first texture page is the village's figure sheet;
# the palettes that research on the PAL disc named, each (file, palette number of 16 words, who, the
# subtypes it is given there, which drawing of the sheet it is on); where the front, back and left-facing
# figures of each drawing are on the sheet (texels: left, top, right, bottom). Which subtype is which drawing
# and which palette it has were in tables the disc does not hold: the research matched palettes to the
# colours of the retail screenshots and the sprites of the retail game, and guessed the subtypes. The
# facings are a guess. With `stand_in` the residents of other subtypes are drawn translucent, in the
# first palette.
FIGURES = {
    11: dict(group=61, stand_in=False,
             palettes=[('AREA11/CLUT02.GAM', 4, 'lumberjack factory worker (hard hat)', (0,), 'body', (1, 4)),
                       ('AREA11/CLUT02.GAM', 36, 'male lumberjack town resident (old man)', (), 'body', (2, 3)),
                       ('AREA11/CLUT02.GAM', 68, 'the old man cursed', (), 'body', ())],
             drawings=dict(body=dict(front=(1, 0, 23, 44), back=(74, 0, 93, 44), left=(27, 0, 45, 45)))),
    16: dict(group=76, stand_in=False,
             palettes=[('AREA16/CLUT07.GAM', 21, 'female Stonetown resident', (0,), 'woman', (3,)),
                       ('AREA16/CLUT07.GAM', 37, 'Stonetown boy', (1,), 'boy', ()),
                       ('AREA16/CLUT07.GAM', 53, 'male Stonetown resident (strongman)', (2,), 'strongman', ())],
             drawings=dict(strongman=dict(front=(75, 202, 125, 256), back=(132, 196, 180, 256), left=(39, 196, 70, 256)),
                           woman=dict(front=(107, 49, 143, 93), back=(2, 0, 39, 45), left=(153, 0, 177, 46)),
                           boy=dict(front=(81, 147, 111, 183), back=(81, 147, 111, 183), left=(176, 146, 196, 183))),
             erase=[(160, 186, 182, 209)],       # the hat of the drawing beside the back view
             move=[((137, 195, 160, 208), 8, 0)]),   # the back view's head is drawn eight texels left of its body
    17: dict(group=80, stand_in=False,
             palettes=[('AREA17/CLUT03.GAM', 1, 'Iron Town residents', (0,), 'body', (1, 2, 3, 4))],
             drawings=dict(body=dict(front=(25, 3, 48, 48), back=(145, 2, 166, 48), left=(81, 51, 105, 96)))),
}
FACINGS = {0: 'back', 1: 'right', 2: 'left', 3: 'front'}      # a resident's frame field; a guess
STAND_IN_OPACITY = 0.5


@dataclass
class Look:
    label: str
    subtypes: tuple
    images: dict            # facing: RGBA image, trimmed; 'right' is the mirror of 'left'
    file: str = ''          # the CLUT file the palette is in
    number: int = 0         # and its number there
    guessed: tuple = ()     # subtypes whose own page is lost: drawn translucent, with this look as the guess


@dataclass
class Art:
    group: int
    looks: list             # [Look]; the first is the stand-in
    stand_in: bool

    def look_for(self, subtype):
        """(Look, drawn as a stand-in) for a resident's subtype, or None for a mark."""
        for look in self.looks:
            if subtype in look.subtypes:
                return look, False
        for look in self.looks:
            if subtype in look.guessed:
                return look, True
        return (self.looks[0], True) if self.stand_in else None


def named_palettes(project, area):
    """[(file, number, who, subtypes, drawing, guessed, 16 colours)] of the palettes FIGURES names for an area that the disc has."""
    found = []
    for name, number, who, subtypes, drawing, guessed in FIGURES.get(area, {}).get('palettes', ()):
        entry = next((e for e in project.disc.files if e.path.upper() == name and not e.directory), None)
        if entry is not None:
            words = np.frombuffer(project.payload(entry), '<u2')
            found.append((name, number, who, subtypes, drawing, guessed, words[number * 16:number * 16 + 16].copy()))
    return found


def figure_art(project, path, area):
    """The Art of an area, or None where the disc lacks the group or the first palette."""
    named, palettes = FIGURES.get(area), named_palettes(project, area)
    if not named or not palettes or palettes[0][2] != named['palettes'][0][2] or named['group'] not in village_groups(project, path):
        return None
    texels = indices(project.vram(path, 1, named['group'])[0:256, 64:128])
    for x0, y0, x1, y1 in named.get('erase', ()):
        texels[y0:y1, x0:x1] = 0
    for (x0, y0, x1, y1), dx, dy in named.get('move', ()):
        piece = texels[y0:y1, x0:x1].copy()
        texels[y0:y1, x0:x1] = 0
        target = texels[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
        target[piece != 0] = piece[piece != 0]
    looks = []
    for name, number, who, subtypes, drawing, guessed, row in palettes:
        images = {}
        for facing, (x0, y0, x1, y1) in named['drawings'][drawing].items():
            picture = Image.fromarray(colours(row)[texels[y0:y1, x0:x1]])
            box = picture.getbbox()
            if box is None:
                return None
            images[facing] = picture.crop(box)
        images['right'] = images['left'].transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        looks.append(Look(f'{who} ({name} palette {number})', subtypes, images, name, number, guessed))
    return Art(named['group'], looks, named['stand_in'])


def indices(words):
    """The 4-bit texels of a texture page (64 words wide): 256 per row, the low nibble first."""
    out = np.zeros((words.shape[0], 256), np.uint8)
    for n in range(4):
        out[:, n::4] = (words >> (4 * n)) & 15
    return out


def colours(words):
    """RGBA of 15-bit colours; a zero word is transparent."""
    v = np.asarray(words).astype(np.uint32)
    out = np.zeros(v.shape + (4,), np.uint8)
    out[..., 0] = (v & 31) * 255 // 31
    out[..., 1] = ((v >> 5) & 31) * 255 // 31
    out[..., 2] = ((v >> 10) & 31) * 255 // 31
    out[..., 3] = np.where(v == 0, 0, 255)
    return out


def byte_indices(words):
    """The 8-bit texels of a run of texture pages: two to a word, the low byte first."""
    out = np.zeros((words.shape[0], words.shape[1] * 2), np.uint8)
    out[:, 0::2] = words & 255
    out[:, 1::2] = words >> 8
    return out


def building_image(sheet, palette):
    return Image.fromarray(colours(sheet.building_palettes[palette][1])[byte_indices(sheet.building_words)])


def sheet_image(sheet, palette):
    return Image.fromarray(colours(sheet.palettes[palette][1])[indices(sheet.words)])


def village_groups(project, path):
    """The groups of the system load table that bring the village overlay with texture pages."""
    from formats.archive.ldar import system_table
    groups = project.ldars.get(system_table(path))
    found = []
    for number, group in enumerate(groups or ()):
        overlay = any(a.kind == 'INS' and a.source and 'NFO2' in a.source.path.upper() for a in group.assets)
        if overlay and any(a.kind == 'GRPX' for a in group.assets):
            found.append(number)
    return found


def area_palettes(project, area):
    """[(name, row, column, 16 colours)] for each different 16-colour palette in the area's CLUT files."""
    import re
    found, seen = [], {}
    for entry in sorted(project.disc.files, key=lambda e: e.path):
        match = re.fullmatch(rf'AREA{area:02d}/(CLUT\d+)\.GAM', entry.path.upper())
        if not match or entry.directory:
            continue
        words = np.frombuffer(project.payload(entry), '<u2')
        for at in range(0, len(words) - 15, 16):
            row = words[at:at + 16]
            if len(set(row.tolist())) < 8:
                continue
            key = row.tobytes()
            if key in seen:
                seen[key][4] += 1
                continue
            seen[key] = entry = [match.group(1), at // 256, at % 256, row.copy(), 0]
            found.append(entry)
    return [(f'{name} row {r}, column {x}' + (f' (and {n} like it)' if n else ''), row) for name, r, x, row, n in found]


def area_windows256(project, area):
    """[(label, 256 colours)] for every 256 words, at each multiple of 16, of the area's CLUT files."""
    import re
    found = []
    for entry in sorted(project.disc.files, key=lambda e: e.path):
        match = re.fullmatch(rf'AREA{area:02d}/(CLUT\d+)\.GAM', entry.path.upper())
        if not match or entry.directory:
            continue
        words = np.frombuffer(project.payload(entry), '<u2')
        for at in range(0, len(words) - 255, 16):
            found.append((f'{match.group(1)} row {at // 256}, column {at % 256}', words[at:at + 256]))
    return found


GREY = ('texel value as grey: the colours are not recovered', np.array([(v >> 3) * 0x421 for v in range(256)], np.uint16))


def rank_windows(windows, texels, keep=24):
    """The windows that colour nearly every texel in use, those that make neighbouring texels most alike first.
    Judged on the pairs of neighbouring texels, so a thousand candidates cost little."""
    drawn = texels != 0
    pairs = {}
    for a, b, both in ((texels[:, :-1], texels[:, 1:], drawn[:, :-1] & drawn[:, 1:]),
                       (texels[:-1], texels[1:], drawn[:-1] & drawn[1:])):
        kinds, counts = np.unique(a[both].astype(np.int64) * 256 + b[both], return_counts=True)
        for kind, count in zip(kinds.tolist(), counts.tolist()):
            pairs[kind] = pairs.get(kind, 0) + count
    kinds = np.array([k for k, c in pairs.items() if c >= 3])
    weights = np.array([pairs[k] for k in kinds.tolist()], np.float64)
    if not len(kinds):
        return []
    first, second = kinds // 256, kinds % 256
    use = np.bincount(texels[drawn].astype(np.int64), minlength=256)
    table = np.stack([w for _label, w in windows]).astype(np.int32)
    colour = np.stack([table & 31, (table >> 5) & 31, (table >> 10) & 31], -1)
    holes = np.array([use[row == 0].sum() for row in table]) / max(1, use.sum())
    score = np.empty(len(table))
    for start in range(0, len(table), 512):
        part = colour[start:start + 512]
        score[start:start + 512] = (np.abs(part[:, first, :] - part[:, second, :]).sum(-1) * weights).sum(1) / weights.sum()
    order = [i for i in np.argsort(score) if holes[i] < 0.01]
    seen, out = set(), []
    for i in order:
        if table[i].tobytes() in seen:
            continue
        seen.add(table[i].tobytes())
        out.append((windows[i][0], windows[i][1].copy()))
        if len(out) == keep:
            break
    return out


def figure_sheets(project, path):
    """A Sheet for each village group: its first texture page, which holds the figures, and the palettes
    of the area's CLUT files that colour it completely, the one that makes neighbouring texels most alike first."""
    from formats.level.scene import area_of
    palettes = area_palettes(project, area_of(path))
    windows256 = area_windows256(project, area_of(path))
    sheets = []
    for number in village_groups(project, path):
        vram = project.vram(path, 1, number)
        words = vram[0:256, 64:128].copy()
        texels = indices(words)
        used = sorted(set(np.unique(texels).tolist()) - {0})
        sample = texels[:192:2, ::2]
        ranked = []
        for label, row in palettes:
            if not used or (row[used] == 0).any() or len(set(row[used].tolist())) < 9:
                continue
            c = row.astype(np.int32)
            rgb = np.stack([c & 31, (c >> 5) & 31, (c >> 10) & 31], -1)[sample].astype(np.int32)
            ranked.append((int(np.abs(np.diff(rgb, axis=1)).sum() + np.abs(np.diff(rgb, axis=0)).sum()), label, row))
        ranked.sort(key=lambda r: r[0])
        if FIGURES.get(area_of(path), {}).get('group') == number:
            for name, at, who, _subtypes, _drawing, _guessed, row in reversed(named_palettes(project, area_of(path))):
                ranked.insert(0, (0, f'{who} (named in the research notes): {name} palette {at}', row))
        if ranked:
            sheet = Sheet(number, words, [(label, row) for _score, label, row in ranked], 0)
            buildings = vram[0:256, 128:512].copy()
            sheet.building_words = buildings
            texels = byte_indices(buildings)
            sheet.building_palettes = [GREY] + rank_windows(windows256, texels)
            sheets.append(sheet)
    return sheets


def preview(project, path, index):
    """The Preview of the empty section a load-table group stands for, or None for any other group."""
    from formats.text import export
    located = _village(project, path, index)
    if located is None:
        return None
    found, data, village = located
    area = next(a for a, n in AREA_SETS.items() if n == village.set_number)
    notes = ["The village's background picture, collision map and the tables that say which drawing each resident "
             'subtype is are not on the disc, so this is a plan of marks and not the village as it looked.']
    cases = bank = bank_asset = None
    windows = WINDOWS.get(found.build.name)
    if windows:
        cases = dialogue_cases(data, found.build.overlay, lambda a: found.word(a) if found.holds(a, 4) else None, windows).get(village.set_number)
        bank, bank_asset = _bank(project, path)
        if cases is None or bank is None:
            notes.append('The dialogue routine of this village was not found in the overlay, so the lines are not shown.')
    else:
        notes.append('The dialogue routines of this build are not mapped, so only each resident\'s case number is shown.')
    rows = []
    for r in village.residents:
        row = Row(r.index + 1, r.subtype, 'outdoors' if not r.room else f'inside house {r.room}' if r.room != 255 else 'special',
                  r.behaviour_name, r.dialogue)
        if cases is not None and bank is not None:
            pairs = cases.get(r.dialogue)
            if pairs is None:
                row.note = 'no message: the routine has no such case'
            elif not pairs:
                row.note = 'no message in the code (it sets a flag or does nothing)'
            for g, l in pairs or ():
                entry = (bank.groups[g] if g < len(bank.groups) else 0) + l
                if entry < len(bank.dialogues):
                    row.messages.append((entry, export.plain(bank.dialogues[entry]).replace('\n', ' ')))
                else:
                    row.messages.append((None, f'(group {g}, line {l}: the line is not in this disc\'s text)'))
        rows.append(row)
    if village.cut:
        notes.insert(0, f'{village.name} (AREA{area:02d} section 0) is never loaded: its load list is empty and no exit leads into it.')
    art = figure_art(project, path, area)
    if art is not None:
        solid = [sum(1 for r in village.residents if art.look_for(r.subtype) == (look, False)) for look in art.looks]
        guessed = [sum(1 for r in village.residents if art.look_for(r.subtype) == (look, True)) for look in art.looks]
        marks = len(village.residents) - sum(solid) - sum(guessed)
        notes.append('NPCs are from the sheet of group %d, drawn solid where the page of the subtype survives: %s. '
                     'Which way each facing looks is a guess.'
                     % (art.group, '; '.join(f'{n} as the {look.label}' for n, look in zip(solid, art.looks) if n)))
        if sum(guessed):
            notes.append('Translucent figures are residents whose own page is lost (the village\'s actor table says so); the '
                         'research guessed the drawing and palette: %s.'
                         % '; '.join(f'{n} as the {look.label}' for n, look in zip(guessed, art.looks) if n))
        if marks:
            notes.append(f'The other {marks} residents stay marks: their drawing is not known.')
    # Ranking the palettes takes seconds: once for each table a session.
    sheets = project.__dict__.setdefault('cut_village_sheets', {})
    if path not in sheets:
        sheets[path] = figure_sheets(project, path)
    places = {}
    if bank is not None and bank_asset is not None:
        places['bank'] = (bank, bank_asset.source.path, bank_asset.offset, f'WFM {bank_asset.code:04X}')
    if art is not None:
        from formats.archive.ldar import system_table
        places['group'] = (system_table(path), art.group)
    if (overlay := _overlay_asset(project)) is not None:
        places['overlay'] = overlay
    return Preview(village.name, area, draw_plan(village, art), rows, notes, sheets[path], places, village, art)


def _title(text):
    from PyQt6.QtWidgets import QLabel
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


PASTEL = dict(pink='#F8BBD0', yellow='#FFF0A0', blue='#B3D9F7', green='#BCEBC6', purple='#D5C3F2')


def pastel(button, colour):
    """A large, bold button in a pastel colour (a name of PASTEL), so that it stands out from the plain controls."""
    base = PASTEL[colour]
    red, green, blue = (int(base[i:i + 2], 16) for i in (1, 3, 5))
    button.setCursor(Qt_PointingHand())
    button.setMinimumHeight(38)
    button.setStyleSheet(
        f'QPushButton {{ background-color: {base}; color: #262626; font-weight: bold; font-size: 10pt;'
        f' padding: 8px 18px; border: 2px solid rgba(0, 0, 0, 0.28); border-radius: 8px; }}'
        f'QPushButton:hover {{ background-color: white; border-color: rgba(0, 0, 0, 0.55); }}'
        f'QPushButton:pressed {{ background-color: {base}; padding-top: 10px; }}'
        # Unavailable: the same colour, faded, so each button stays easy to find.
        f'QPushButton:disabled {{ background-color: rgba({red}, {green}, {blue}, 0.4); color: rgba(128, 128, 128, 0.95);'
        f' border-color: rgba(128, 128, 128, 0.3); }}')


def Qt_PointingHand():
    from PyQt6.QtCore import Qt
    return Qt.CursorShape.PointingHandCursor


def _sheets_panel(sheets):
    """The sprite sheets of the village load groups, side by side: the figures of page 0 on the left and the
    buildings of the pages after it on the right, each with a choice of palette above its picture."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSplitter, QVBoxLayout, QWidget
    from gui.widgets.image_view import ImageView
    panel = QWidget()
    outer = QVBoxLayout(panel)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(_title(f'Sprites: the figures and buildings the village overlay can load ({len(sheets)} sets)'))
    bar = QHBoxLayout()
    sprite = QComboBox()
    sprite.addItems([f'Sprite {n} of {len(sheets)} (group {sheet.group})' for n, sheet in enumerate(sheets, 1)])
    bar.addWidget(QLabel('Sprite'))
    bar.addWidget(sprite, 1)
    outer.addLayout(bar)
    columns = QSplitter(Qt.Orientation.Horizontal)
    outer.addWidget(columns, 1)
    note = QLabel('Page 0 of each group that loads the village overlay holds 4-bit figures (256 x 256 texels), pages 1 to 6 '
                  '8-bit pictures of buildings (768 x 256): pieces of the village that were put together from data '
                  'the disc does not hold, so they are shown as they are stored. Nothing read from the game says which '
                  'village loads which group or which palette is used; the palettes are those of the area CLUT files that '
                  'colour the whole page, the named ones first, then the one that makes neighbouring texels most alike, '
                  'so pick another if the colours look wrong.')
    note.setWordWrap(True)
    outer.addWidget(note)

    def column(title, palettes_of, first_of, make):
        """One side of the pair: a title, a palette choice and the picture; returns what the sprite choice refreshes."""
        side = QWidget()
        inside = QVBoxLayout(side)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.addWidget(_title(title))
        choice = QHBoxLayout()
        palette, count = QComboBox(), QLabel()
        choice.addWidget(QLabel('Palette'))
        choice.addWidget(palette, 1)
        choice.addWidget(count)
        inside.addLayout(choice)
        picture = ImageView()
        picture.zoom.setCurrentIndex(0)     # Fit
        inside.addWidget(picture, 1)
        columns.addWidget(side)

        def fill():
            sheet = sheets[sprite.currentIndex()]
            listed = palettes_of(sheet)
            first = first_of(sheet)
            palette.blockSignals(True)
            palette.clear()
            palette.addItems([f'{n} of {len(listed)}: {label}' + (' (default)' if n - 1 == first else '')
                              for n, (label, _row) in enumerate(listed, 1)])
            palette.setCurrentIndex(first if listed else -1)
            palette.blockSignals(False)
            count.setText(f'{len(listed)} palettes')
            draw()

        def draw():
            sheet = sheets[sprite.currentIndex()]
            if palettes_of(sheet) and palette.currentIndex() >= 0:
                picture.set_image(make(sheet, palette.currentIndex()), preserve_view=False)
        palette.currentIndexChanged.connect(draw)
        return fill

    refresh = [column('NPCs: page 0, 4-bit', lambda sheet: sheet.palettes, lambda sheet: sheet.best, sheet_image),
               column('Buildings: pages 1 to 6, 8-bit', lambda sheet: sheet.building_palettes, lambda sheet: 0,
                      building_image)]
    columns.setSizes([400, 600])
    sprite.currentIndexChanged.connect(lambda: [fill() for fill in refresh])
    for fill in refresh:
        fill()
    return panel


class _BackdropBar:
    """The controls of the background picture and what they hold. `changed()` is called after each change."""
    def __init__(self, layout, backdrop):
        self.layout, self.backdrop = layout, backdrop


def _backdrop_bar(preview, changed):
    """A row of controls: choose a picture to draw under the plan, place it, clear it. Remembered for each area."""
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox
    key = f'cutVillage/{preview.area}/'
    settings = QSettings()
    bar = QHBoxLayout()
    holder = _BackdropBar(bar, None)
    choose, clear = QPushButton('Load background picture...'), QPushButton('Clear')
    pastel(choose, 'purple')
    x, y = QSpinBox(), QSpinBox()
    scale = QDoubleSpinBox()
    opacity = QSpinBox()
    for box, low, high in ((x, -4000, 4000), (y, -4000, 4000)):
        box.setRange(low, high)
    scale.setRange(5, 800)
    scale.setSuffix(' %')
    scale.setDecimals(1)
    scale.setSingleStep(5)
    opacity.setRange(5, 100)
    opacity.setSuffix(' %')
    path_label = QLabel()
    for widget in (choose, QLabel('X'), x, QLabel('Y'), y, QLabel('Scale'), scale, QLabel('Opacity'), opacity, clear):
        bar.addWidget(widget)
    bar.addWidget(path_label, 1)
    controls = (x, y, scale, opacity, clear)
    choose.setToolTip('Draw a picture (a restored view of the village, say) under the plan. Move it with X and Y, '
                      'in world units, and size it with Scale; it is kept for this village.')

    def load(path):
        from PIL import Image as PilImage
        try:
            with PilImage.open(path) as opened:
                return opened.convert('RGBA')
        except Exception as error:
            path_label.setText(f'Could not open {path}: {error}')
            return None

    def sync(editing=True):
        enabled = holder.backdrop is not None
        for widget in controls:
            widget.setEnabled(enabled)
        if enabled:
            holder.backdrop.x, holder.backdrop.y = x.value(), y.value()
            holder.backdrop.scale, holder.backdrop.opacity = scale.value(), opacity.value() / 100
            if editing:
                settings.setValue(key + 'x', x.value()); settings.setValue(key + 'y', y.value())
                settings.setValue(key + 'scale', scale.value()); settings.setValue(key + 'opacity', opacity.value())
        changed()

    def use(image, path, left, top, size, shade):
        holder.backdrop = Backdrop(image, left, top, size, shade / 100)
        for box, value in ((x, left), (y, top), (scale, size), (opacity, shade)):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        path_label.setText(path)
        sync(False)

    def pick():
        path, _ = QFileDialog.getOpenFileName(None, 'Background picture', settings.value(key + 'path', '') or '',
                                              'Pictures (*.png *.jpg *.jpeg *.bmp *.webp *.gif)')
        if not path:
            return
        image = load(path)
        if image is None:
            return
        settings.setValue(key + 'path', path)
        village = preview.village
        use(image, path, min((r.x for r in village.residents), default=0) - 40, min((r.y for r in village.residents), default=0) - 40,
            100.0, 100)
        sync()

    def remove():
        holder.backdrop = None
        settings.remove(key + 'path')
        path_label.setText('')
        sync(False)
    choose.clicked.connect(pick)
    clear.clicked.connect(remove)
    for widget in (x, y, scale, opacity):
        widget.valueChanged.connect(lambda _value: sync())
    remembered = settings.value(key + 'path', '') or ''
    if remembered and preview.village is not None:
        from pathlib import Path
        image = load(remembered) if Path(remembered).is_file() else None
        if image is not None:
            use(image, remembered, int(settings.value(key + 'x', 0)), int(settings.value(key + 'y', 0)),
                float(settings.value(key + 'scale', 100.0)), int(settings.value(key + 'opacity', 100)))
    if holder.backdrop is None:
        for widget in controls:
            widget.setEnabled(False)
    return holder


def view(preview, english=None, request=None, changed=None, jump=None):
    """The widget for a Preview. `english(text)` gives a translation of a line, or None.

    `jump(kind, payload)` takes the user to something the selection is made of: kind 'text' (payload: the bank's
    Wfm, its file, its offset, its name and the entry), 'group' (a load table and a group of it), 'asset' or
    'file' (a disc path). Without it the buttons are not shown.

    Selecting a row calls `request(texts)` with that row's lines so they are translated first;
    `changed` is a signal that fires when a translation may have arrived.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView
    from gui.widgets.image_view import ImageView
    widget = QWidget()
    layout = QVBoxLayout(widget)
    note = QLabel(' '.join(preview.notes))
    note.setWordWrap(True)
    layout.addWidget(note)
    split = QSplitter(Qt.Orientation.Horizontal)
    picture = ImageView()
    picture.zoom.setCurrentIndex(0)     # Fit: the plan is larger than its pane at 200%
    picture.set_image(preview.image)
    plan = QWidget()
    plan_layout = QVBoxLayout(plan)
    plan_layout.setContentsMargins(0, 0, 0, 0)
    redraw_hook = []
    backdrop_bar = _backdrop_bar(preview, lambda: redraw_hook and redraw_hook[0]())
    plan_layout.addLayout(backdrop_bar.layout)
    plan_layout.addWidget(picture, 1)
    info = QLabel(describe(preview, []))
    info.setWordWrap(True)
    plan_layout.addWidget(info)
    from PyQt6.QtWidgets import QHBoxLayout, QMenu, QPushButton
    jump_bar = QHBoxLayout()
    open_text = QPushButton('Open text entry')
    open_text.setToolTip('Go to the text bank and show the selected resident\'s message.')
    open_sprite = QPushButton('Open sprite sheet')
    open_sprite.setToolTip('Open the VRAM of the load group that holds the figures: the sheet is a picture there.')
    open_palette = QPushButton('Open palette file')
    open_palette.setToolTip('Go to the CLUT file that holds the palette of the selected resident\'s figure.')
    open_code = QPushButton('Open overlay code')
    open_code.setToolTip('Go to the INFO2 overlay: the residents, props and houses of the villages and their dialogue routines.')
    for button, colour in ((open_text, 'pink'), (open_sprite, 'yellow'), (open_palette, 'blue'), (open_code, 'green')):
        pastel(button, colour)
        jump_bar.addWidget(button, 1)
    jump_bar.setSpacing(10)
    if jump is not None:
        plan_layout.addLayout(jump_bar)
    else:
        for button in (open_text, open_sprite, open_palette, open_code):
            button.hide()
    split.addWidget(plan)
    if backdrop_bar.backdrop is not None:
        picture.set_image(draw_plan(preview.village, preview.art, backdrop=backdrop_bar.backdrop))
    headers = ['#', 'Where', 'Behaviour', 'Drawing', 'Case', 'Says (Japanese)'] + (['English'] if english else [])
    table = QTableWidget(len(preview.rows), len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    def lines(row):
        return [text for entry, text in row.messages if entry is not None]

    def translated(row):
        found = [english(text) for text in lines(row)]
        return ' / '.join(line for line in found if line)

    def show_english():
        column = len(headers) - 1
        for r, row in enumerate(preview.rows):
            text = translated(row)
            item = table.item(r, column)
            if item is not None and item.text() != text:
                item.setText(text)
                item.setToolTip(text)

    for r, row in enumerate(preview.rows):
        says = ' / '.join(text if entry is None else f'#{entry}: {text}' for entry, text in row.messages) or row.note
        cells = [str(row.number), row.where, row.behaviour, str(row.subtype), str(row.case), says]
        if english:
            cells.append(translated(row))
        for c, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(text)
            table.setItem(r, c, item)
    table.resizeColumnsToContents()
    table.setColumnWidth(5, min(table.columnWidth(5), 300))     # the Japanese is the shorter column
    if english:
        table.setColumnWidth(6, 560)
        table.horizontalHeader().setStretchLastSection(True)
    if english and changed is not None:
        def refresh():
            try:
                show_english()
            except RuntimeError:        # the tab was closed
                changed.disconnect(refresh)
        changed.connect(refresh)
    if request is not None:
        def selected():
            # The selected rows' lines first, then the rest of the village's.
            rows = sorted({i.row() for i in table.selectedIndexes()})
            request([text for r in rows for text in lines(preview.rows[r])]
                    + [text for row in preview.rows for text in lines(row)])
        table.itemSelectionChanged.connect(selected)
        selected()      # opening the tab already queues every line of the village
        state_selected_lines = selected
    # Selection: the table's rows and the plan's elements show each other. `syncing` stops the one
    # from answering while the other is being set.
    state = dict(selected=[], syncing=False, hits=[])
    places = preview.places

    def chosen_rows(selected):
        return [i for kind, i in selected if kind == 'resident']

    def message_entries(selected):
        return [(row, entry) for row in chosen_rows(selected) for entry, _text in preview.rows[row].messages if entry is not None]

    def chosen_looks(selected):
        if preview.art is None:
            return []
        found = [preview.art.look_for(preview.village.residents[row].subtype) for row in chosen_rows(selected)]
        return [look for look, _stand_in in (f for f in found if f)]

    def update_jumps(selected):
        open_text.setEnabled('bank' in places and bool(message_entries(selected)))
        open_sprite.setEnabled('group' in places)
        open_palette.setEnabled(bool(chosen_looks(selected)))
        open_code.setEnabled('overlay' in places)

    def go_text():
        entries = message_entries(state['selected'])
        if not entries or jump is None:
            return
        if len(entries) == 1:
            jump('text', (*places['bank'], entries[0][1]))
            return
        menu = QMenu(open_text)
        for row, entry in entries:
            action = menu.addAction(f'Resident {row + 1}: entry #{entry}')
            action.triggered.connect(lambda _checked=False, e=entry: jump('text', (*places['bank'], e)))
        menu.exec(open_text.mapToGlobal(open_text.rect().bottomLeft()))

    def go_palette():
        looks = chosen_looks(state['selected'])
        if looks and jump is not None:
            jump('file', looks[0].file)
    open_text.clicked.connect(go_text)
    open_sprite.clicked.connect(lambda: jump('group', places['group']))
    open_palette.clicked.connect(go_palette)
    open_code.clicked.connect(lambda: jump('asset', places['overlay']))
    update_jumps([])
    if preview.village is not None:
        draw_plan(preview.village, preview.art, hits=state['hits'], backdrop=backdrop_bar.backdrop)

        def redraw(selected=None):
            if selected is not None:
                state['selected'] = selected
            state['hits'][:] = []
            image = draw_plan(preview.village, preview.art, state['selected'], state['hits'], backdrop_bar.backdrop)
            picture.set_image(image, preserve_view=True)
        redraw_hook.append(redraw)

        def show(selected):
            if selected == state['selected']:
                return
            redraw(selected)
            info.setText(describe(preview, selected))
            update_jumps(selected)

        def rows_changed():
            if state['syncing']:
                return
            rows = sorted({i.row() for i in table.selectedIndexes()})
            show([('resident', r) for r in rows])

        def plan_clicked(x, y):
            found = hit_test(state['hits'], x, y)
            state['syncing'] = True
            try:
                table.clearSelection()
                if found is not None and found[0] == 'resident':
                    table.selectRow(found[1])
                    table.scrollToItem(table.item(found[1], 0))
            finally:
                state['syncing'] = False
            show([found] if found is not None else [])
            selected_lines()        # the table's own handler for translation priority

        selected_lines = state_selected_lines if request is not None else (lambda: None)
        table.itemSelectionChanged.connect(rows_changed)
        picture.canvas.clicked.connect(plan_clicked)
    residents = QWidget()
    inside = QVBoxLayout(residents)
    inside.setContentsMargins(0, 0, 0, 0)
    inside.addWidget(_title(f'Residents of {preview.name}: {len(preview.rows)} entries, the numbered marks of the plan'))
    inside.addWidget(table, 1)
    if preview.sheets:
        # Under the residents, so the plan keeps the whole height of the tab.
        right = QSplitter(Qt.Orientation.Vertical)
        right.addWidget(residents)
        right.addWidget(_sheets_panel(preview.sheets))
        right.setSizes([380, 340])
        split.addWidget(right)
    else:
        split.addWidget(residents)
    split.setSizes([480, 900])
    layout.addWidget(split, 1)
    layout.addWidget(QLabel('Red: resident outdoors. Purple: resident inside a house. Blue: house. '
                            'Green: where a patrolling resident walks. Yellow: prop. A translucent figure is a stand-in. '
                            'Numbers are the rows of the table.'))
    return widget
