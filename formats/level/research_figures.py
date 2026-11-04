"""Pictures and animations for the JP research reports, decoded from the opened disc and shown inside the report.

A report names sprites ("SPR slot 3 frames 33-35", "frame 197, CLUT 7D12") and files. Here each named sprite that
survives is drawn from the disc itself, in the palette the report names, with a button that opens the bank it is in;
file names in the reports link to the disc tree. Nothing is bundled: the pictures are made from the user's own disc
and only for the audited Japanese retail build."""
import hashlib
import re
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

SCALE = 4
TICKS_PER_SECOND = 30        # display rate for the update ticks of an animation script; the game's own is not assumed
GROUP = ('SYS/LDAR10.BIN', 1)
BACKGROUND = (44, 44, 54, 255)
CHIEF_BANK_SHA1 = 'e3dc39e7c1eed97e3fbc487d0d69d2557cbaa787'
CHIEF_TEXTURE_SHA1 = 'f48629510d5b7838647d23b6d90d21e616ec8cdc'
EEL_BANK_SHA1 = '53c337d8a72ac14b0386dd7702e16b0da821f02e'


@dataclass
class Figure:
    key: str
    document: str            # file name of the report it belongs to
    heading: str             # the picture follows the first paragraph under the heading that contains this
    caption: str
    frames: list = field(repr=False)          # PIL images, all the same size
    delays: list = None                       # milliseconds per frame when it is an animation
    asset: object = None                      # the bank it comes from, for the open button
    button: str = 'Open the sprite bank'
    anchor: str = None                        # when given, the picture follows the paragraph with this text instead


def _resources(project):
    from formats.level.scene import loaded_resources
    return loaded_resources(project, *GROUP)


def _digest(data):
    return hashlib.sha1(bytes(data)).hexdigest()


def _scaled(image, size=None, scale=SCALE):
    image = image.convert('RGBA')
    big = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    if size is None:
        return big
    canvas = Image.new('RGBA', size, BACKGROUND)
    canvas.alpha_composite(big, ((size[0] - big.width) // 2, (size[1] - big.height) // 2))
    return canvas


def _labelled(cells, labels, scale=SCALE):
    """Pictures side by side on one dark strip, each with a small label beneath it."""
    cells = [_scaled(c, scale=scale) for c in cells]
    width = max(c.width for c in cells)
    height = max(c.height for c in cells)
    strip = Image.new('RGBA', ((width + 12) * len(cells) + 12, height + 32), BACKGROUND)
    draw = ImageDraw.Draw(strip)
    for number, (cell, label) in enumerate(zip(cells, labels)):
        x = 12 + number * (width + 12)
        strip.alpha_composite(cell, (x + (width - cell.width) // 2, 8 + height - cell.height))
        draw.text((x, height + 14), label, fill=(220, 220, 230, 255))
    return strip


def eel(project):
    """The three eel frames of AREA10, in the palette the audit found, played as the retail script times them."""
    from psx.graphics import render_sprite, sprite_frames
    asset = _resources(project)['SPR', 3]
    data = bytes(project.asset_data(asset))
    if _digest(data) != EEL_BANK_SHA1:
        return None
    frames = sprite_frames(data)
    vram = project.vram(*GROUP)
    pictures = [render_sprite(frames[n], vram, tpage=12, clut=0x7B0C) for n in (33, 34, 35)]
    size = (max(p.width for p in pictures) * SCALE + 16, max(p.height for p in pictures) * SCALE + 16)
    shown = [_scaled(p, size) for p in pictures]
    delays = [8 * 1000 // TICKS_PER_SECOND] * 2 + [1500]
    caption = ('Frames 33, 34 and 35 of the Jungle SPR slot 3, CLUT 7B0C, page base 12. The retail script changes frame every 8 update '
               'ticks and then holds frame 35; it has no loop. This preview restarts it after a pause.')
    return Figure('eel', 'jp-retail-unused-research.md', 'Electric eel: graphics and script survive together', caption,
                  shown, delays, asset, 'Open the Jungle sprite bank (SPR 3)')


def chief(project):
    """The frames of the Masakari Chief that the research matched with the PAL candidates, in the stored palette."""
    import numpy as np
    from psx.graphics import render_sprite, sprite_frames
    asset = _resources(project)['SPR', 7]
    bank = bytes(project.asset_data(asset))
    page = next(a for a in project.ldars['SYS/LDSYS.BIN'][57].assets if a.kind == 'GRPX')
    pixels = bytes(project.asset_data(page))
    if _digest(bank) != CHIEF_BANK_SHA1 or _digest(pixels) != CHIEF_TEXTURE_SHA1:
        return None
    frames = sprite_frames(bank)
    vram = project.vram(*GROUP).copy()
    vram[0:256, 64:256] = np.frombuffer(pixels, '<u2').reshape(256, 192)
    numbers = (31, 47, 48, 49, 50, 51, 52, 54, 55, 56, 57, 58)
    pictures = [render_sprite(frames[n], vram, tpage=1, clut=0x780A) for n in numbers]
    caption = ('Frames 31, 47-52 and 54-58 of the Jungle SPR slot 7, drawn with the stored CLUT 780A. The runtime palette is not '
               'established. Frame 53 is a mis-cut atlas block and is left out.')
    rows = [pictures[:6], pictures[6:]]
    strips = [_labelled(row, [f'frame {n}' for n in numbers[i * 6:i * 6 + 6]], scale=2) for i, row in enumerate(rows)]
    sheet = Image.new('RGBA', (max(s.width for s in strips), sum(s.height for s in strips)), BACKGROUND)
    sheet.alpha_composite(strips[0], (0, 0))
    sheet.alpha_composite(strips[1], (0, strips[0].height))
    return Figure('chief', 'jp-retail-unused-research.md', 'Masakari Chief — sprites, judgement dialogue and nearby text',
                  caption, [sheet], None, asset, 'Open the Chief sprite bank (SPR 7)')


# item, name, SPR slot, frame, page word, CLUT (None keeps the palette of the sprite's parts)
FUNGA = ((91, 'Wood', 3, 38, 12, None), (119, 'Leather', 4, 0, 21, 0x7D56), (122, 'Tree', 3, 111, 13, None),
         (123, 'Sap', 3, 37, 12, None), (140, 'Chief\'s Spear', 3, 93, 12, None),
         (125, 'Funga Drum', 4, 197, 20, 0x7D12), (137, 'Small Drum', 4, 197, 20, 0x7D12))


def funga(project):
    """The world sprites that the item initializer selects for the Funga materials, and the one the two drums share."""
    from psx.graphics import render_sprite, sprite_frames
    resources = _resources(project)
    vram = project.vram(*GROUP)
    banks = {}
    cells, labels = [], []
    for item, name, slot, frame, page, clut in FUNGA:
        if slot not in banks:
            banks[slot] = sprite_frames(bytes(project.asset_data(resources['SPR', slot])))
        picture = render_sprite(banks[slot][frame], vram, tpage=page, clut=clut)
        cells.append(picture)
        labels.append(f'{name} {item}' + ('' if picture.getbbox() else ' (draws nothing)'))
    caption = ('World sprites chosen by the native item initializer: SPR 3 frames 38, 111, 37 and 93, SPR 4 frame 0 for Leather '
               '(the generic berry graphic) and SPR 4 frame 197, CLUT 7D12, for both drums. The two drums are the same picture; a frame that draws nothing in the stored palette is marked.')
    return Figure('funga', 'jp-retail-unused-research.md', 'Funga materials and the drum', caption,
                  [_labelled(cells, labels)], None, resources['SPR', 3], 'Open the Jungle sprite bank (SPR 3)')


def math_beads(project):
    """Math Bead 11 is the one number item with a world descriptor of its own; the other nine use the generic one."""
    from psx.graphics import render_sprite, sprite_frames
    resources = _resources(project)
    vram = project.vram(*GROUP)
    common = sprite_frames(bytes(project.asset_data(resources['SPR', 4])))
    cells = [render_sprite(common[171], vram, tpage=20), render_sprite(common[0], vram, tpage=21, clut=0x7D56)]
    caption = ('Math Bead 11 (slot 77): descriptor 89, SPR 4 frame 171, page 20. Slots 78-86 use descriptor 0, the generic berry '
               'graphic (SPR 4 frame 0, CLUT 7D56). Every one of them says "Error" when used.')
    return Figure('beads', 'jp-retail-unused-research.md', 'Math Beads and numbered placeholders', caption,
                  [_labelled(cells, ['Bead 11 (77)', 'slots 78-86'])], None, resources['SPR', 4], 'Open the common sprite bank (SPR 4)')


def tunnel(project):
    """The AREA02 tunnel sheet: ten by three cells of 24 pixels at page 13, u 0-239, v 72-143, in a grey ramp."""
    import numpy as np
    from psx.graphics import texture_page
    asset = next((a for g in project.ldars['SYS/LDAR02.BIN'] for a in g.assets
                  if a.source and a.source.path == 'AREA02/B301.000'), None)
    group = next(i for i, g in enumerate(project.ldars['SYS/LDAR02.BIN']) if asset in g.assets)
    vram = project.vram('SYS/LDAR02.BIN', group)
    ramp = np.array([0] + [(2 * i) << 10 | (2 * i) << 5 | 2 * i for i in range(1, 16)], dtype=np.uint16)
    sheet = texture_page(vram, 13, 0, palette=ramp).crop((0, 72, 240, 144))
    for x in range(0, 240, 24):                       # the 24 pixel cells
        for y in range(72):
            if sheet.getpixel((x, y))[3] == 0:
                sheet.putpixel((x, y), (90, 90, 120, 255))
    caption = ('AREA02/B301.000, page 13, u 0-239, v 72-143: ten by three cells of 24 pixels (the first row numerals, the second '
               'pictorial symbols). Drawn in a grey ramp because the palette is not established; the blue lines mark the cells.')
    return Figure('tunnel', 'jp-retail-unused-research.md', 'Graffiti Rocks — upstream research', caption,
                  [_scaled(sheet, scale=3)], None, asset, 'Open the tunnel sheet (B301.000)', 'The adjacent AREA02 tunnel sheet')


def debug_font(project):
    """The 8 x 8 debug font of the executable, on the system texture, in the first of its four palette rows."""
    from psx.graphics import texture_page
    asset = next(a for a in project.ldars['SYS/LDSYS.BIN'][0].assets if a.source and a.source.path == 'SYSTEM/A00000.GAM')
    vram = project.vram(*GROUP)
    page = texture_page(vram, 21, 0x7C17)
    box = page.getbbox()
    if box is None:
        return None
    caption = ('SYSTEM/A00000.GAM at VRAM page 21 in the first of the four CLUT rows that begin at (368,496): the 8 x 8 font of the '
               'debug printer MAIN 80021E5C, used for the ending statistics and some game-over text.')
    return Figure('debugfont', 'jp-retail-unused-research.md', 'Graffiti Rocks — upstream research', caption,
                  [_scaled(page.crop(box), scale=3)], None, asset, 'Open the system font texture',
                  'The JP debug printer is MAIN')


BUILDERS = (eel, chief, funga, math_beads, tunnel, debug_font)


def build(project):
    """Every figure that can be made from this disc; none for a disc that is not the audited Japanese retail build."""
    from formats.level.cut_research import supported
    if not supported(project):
        return []
    found = []
    for builder in BUILDERS:
        try:
            figure = builder(project)
        except (KeyError, IndexError, StopIteration, ValueError, OSError, TypeError):
            continue
        if figure is not None:
            found.append(figure)
    return found


PATH = re.compile(r'`((?:AREA\d\d/[A-Z0-9_]+\.[A-Z0-9]+)|(?:SYSTEM/[A-Z0-9_]+\.[A-Z0-9]+)|SLPS_011\.44)`')


def decorate(report, document, figures, project=None):
    """The report's Markdown with its pictures and file links added: `fig:KEY` images and `tomba://` links."""
    lines = report.split('\n')
    out, fence = [], False
    for line in lines:
        if line.lstrip().startswith('```'):
            fence = not fence
        if not fence and project is not None:
            line = PATH.sub(lambda m: f'[`{m.group(1)}`](tomba://file/{m.group(1)})'
                            if m.group(1) in project.disc.entries else m.group(0), line)
        out.append(line)
    def block_end(start):
        """The line after the paragraph, list or table that starts at `start`."""
        while start < len(out) and not out[start].strip():
            start += 1
        while start < len(out) and out[start].strip():
            start += 1
        return start

    after = {}                                            # line index -> the figures that follow that line
    for figure in (f for f in figures if f.document == document):
        if figure.anchor:
            line = next((n for n, text in enumerate(out) if figure.anchor in text and not text.startswith('#')), None)
            end = block_end(line) if line is not None else None
        else:
            line = next((n for n, text in enumerate(out) if text.startswith('#') and figure.heading in text), None)
            end = block_end(line + 1) if line is not None else None
        if end is not None:
            after.setdefault(end, []).append(figure)
    result = []
    for number, line in enumerate(out + ['']):
        for figure in after.get(number, ()):
            result += ['', f'![{figure.key}](fig:{figure.key})', '',
                       f'*{figure.caption}* — [{figure.button}](tomba://asset/{figure.key})', '']
        if number < len(out):
            result.append(line)
    return '\n'.join(result)
