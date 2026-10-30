"""English display previews using saved, recognised Tomba ROM glyphs."""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import json
import unicodedata
from PIL import Image, ImageDraw


@lru_cache(maxsize=1)
def fonts():
    root = Path(__file__).with_name('fonts')
    metadata = json.loads((root / 'english.json').read_text(encoding='utf8'))
    result = {}
    for height, font in metadata['fonts'].items():
        with Image.open(root / font['image']) as image:
            result[int(height)] = {char: image.crop(record['box']).convert('RGBA')
                                   for char, record in font['glyphs'].items()}
    return result


def typical_width(font):
    """The usual width of a letter in a saved font: the median of its letters."""
    letters = sorted(image.width for char, image in font.items() if char.isalpha())
    return letters[len(letters) // 2] if letters else 8


def render(wfm, index, text):
    """Reflow a translation; never borrow Japanese character positions/control timing.

    Prefer Latin glyphs in this bank, then the closest saved English font.
    Return the image and characters for which a Tomba question mark was needed.
    """
    dialogue = wfm.dialogues[index]
    heights = Counter(im.height for im in wfm.glyphs if im.height >= 10)
    target = heights.most_common(1)[0][0] if heights else 16
    saved = fonts()
    preferred = min(saved, key=lambda h: (abs(h - target), -h))
    glyphs = dict(saved[preferred])
    widths = {height: typical_width(font) for height, font in saved.items()}
    for height in sorted(saved, key=lambda h: abs(h - target)):
        for char, image in saved[height].items():
            if char not in glyphs:
                # A letter borrowed from another size keeps its place in that font's proportions: the
                # 8 pixel font's letters are square and the 16 pixel font's are half as wide as they are
                # tall, so scaling by height alone would make a borrowed letter twice as wide as its neighbours.
                wide = max(1, round(image.width * widths[preferred] / widths[height]))
                glyphs[char] = image.resize((wide, preferred), Image.Resampling.NEAREST)
    for char, image in zip(wfm.characters, wfm.glyphs):
        if char and len(char) == 1 and char.isascii() and image.height == preferred:
            glyphs[char] = image
    aliases = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '–': '-', '—': '-', '…': '...'})
    text = unicodedata.normalize('NFKC', text).translate(aliases).replace('\r\n', '\n').replace('\r', '\n')
    bubble = next((args for word, args in dialogue.tokens if word == 0xFFFA), (256, 48))
    width = max(96, min(1024, bubble[0]))
    space = max(4, preferred // 3)
    missing = set()

    def glyph(char):
        if char.isspace():
            return Image.new('RGBA', (space, preferred))
        if char in glyphs:
            return glyphs[char]
        # Diacritics can fall back to the corresponding Tomba base letter.
        base = ''.join(c for c in unicodedata.normalize('NFKD', char) if not unicodedata.combining(c))
        if base in glyphs:
            return glyphs[base]
        missing.add(char)
        return glyphs['?']

    import re

    def flow(part):
        """The lines of one frame's text. All characters and line breaks are kept, long words wrapped too."""
        lines, line, used = [], [], 0
        for token in re.findall(r'\n|[^\S\n]+|[^\s]+', part):
            if token == '\n':
                lines.append(line); line, used = [], 0
                continue
            images = [glyph(c) for c in token]
            token_width = sum(im.width for im in images)
            if line and used + token_width > width and not token.isspace():
                lines.append(line); line, used = [], 0
            for image in images:
                if used + image.width > width and line:
                    lines.append(line); line, used = [], 0
                line.append(image); used += image.width
        lines.append(line)
        return lines

    # One frame for each frame of the original: a blank line in the translation is where the original clears the
    # box. A frame whose English is longer than the original's grows taller; a translation with more blank
    # lines than the original has frames keeps the extra text in the last frame.
    try:
        heights = [wfm.render(index, page).height for page in range(len(wfm.pages(index)))]
    except Exception:
        heights = []
    parts = [p for p in re.split(r'\n[^\S\n]*\n\s*', text.strip('\n')) if p.strip()] or ['']
    if heights and len(parts) > len(heights):
        parts[len(heights) - 1:] = ['\n\n'.join(parts[len(heights) - 1:])]
    panels = []
    for number, part in enumerate(parts):
        page = flow(part)
        height = max(min(bubble[1], 512) + 8, len(page) * (preferred + 2) + 16, heights[number] if number < len(heights) else 0)
        panel = Image.new('RGBA', (width + 16, height), (220, 216, 194, 255))
        draw = ImageDraw.Draw(panel)
        draw.rectangle((0, 0, panel.width - 1, height - 1), outline=(32, 24, 16), width=2)
        draw.rectangle((3, 3, panel.width - 4, height - 4), outline=(255, 252, 230))
        for row, images in enumerate(page):
            x = 8
            for image in images:
                panel.alpha_composite(image, (x, 8 + row * (preferred + 2))); x += image.width
        panels.append(panel)
    total_height = sum(p.height for p in panels) + 8 * (len(panels) - 1)
    if total_height > 16384:
        raise ValueError('Translated display exceeds preview size limit; the full translation is in the text pane.')
    result = Image.new('RGBA', (width + 16, total_height))
    y = 0
    for panel in panels:
        result.alpha_composite(panel, (0, y)); y += panel.height + 8
    return result, missing
