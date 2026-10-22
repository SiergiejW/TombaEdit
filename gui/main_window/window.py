"""Disc folders and LDAR area/section browser."""
from pathlib import Path
import struct
import sys
import traceback
from PyQt6.QtCore import Qt, QSize, QSettings, QTimer, QObject, QRunnable, QThreadPool, pyqtSignal, QEvent
from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSplitter, QTreeWidget, QTreeWidgetItem, QTabWidget, QFileDialog,
    QMessageBox, QToolBar, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QMenu, QApplication, QStyle, QComboBox, QInputDialog)
from disc.reader import DiscEntry, FormatError
from formats.archive.ldar import Project, Asset, area_number, table_name, system_table, bank_screens
from game.areas import AREAS, section_name, language_name
from gui.theme import apply_theme
from gui.viewers import text_view, ImageView, DialogueView, GlyphView, SpriteView, ModelView, VramView
from formats.text.wfm import Wfm
from formats.models.wmd import parse_wmd
from psx.graphics import sprite_frames
from icons.icons import icon
from game import labels
from game.builds import executable
from main import version
import hashlib

ROLE = Qt.ItemDataRole.UserRole
DISC_SUFFIXES = (".bin", ".cue", ".iso", ".img", ".ccd")


class ResourceTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        self.user_horizontal = 0
        self.restore_horizontal = QTimer(self)
        self.restore_horizontal.setSingleShot(True)
        self.restore_horizontal.timeout.connect(lambda: self.horizontalScrollBar().setValue(self.user_horizontal))
        bar = self.horizontalScrollBar()
        bar.sliderMoved.connect(self.remember_horizontal)
        bar.actionTriggered.connect(lambda action: self.remember_horizontal(bar.sliderPosition()))

    def remember_horizontal(self, position):
        self.user_horizontal = position

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        # Qt otherwise hides the review columns when ensuring a deep name
        # cell is visible. Deliberate horizontal scrolling still works.
        if dx and hasattr(self, 'restore_horizontal'):
            self.restore_horizontal.start(0)


class Signals(QObject):
    result = pyqtSignal(int, object, str)


class Job(QRunnable):
    def __init__(self, generation, callback, receiver):
        super().__init__()
        self.generation, self.callback = generation, callback
        self.signals = Signals()
        self.signals.result.connect(receiver)

    def run(self):
        try:
            result, error = self.callback(), ''
        except Exception as exc:
            result, error = None, f"{type(exc).__name__}: {exc}"
        try:
            self.signals.result.emit(self.generation, result, error)
        except RuntimeError:
            # The window may have closed while the worker was finishing.
            pass


def hex_dump(data, total=None):
    rows = []
    for offset in range(0, min(len(data), 65536), 16):
        row = data[offset:offset + 16]
        ascii_text = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
        rows.append(f"{offset:08X}  {row.hex(' ').upper():47s}  {ascii_text}")
    total = total if total is not None else len(data)
    if total > 65536:
        rows.append(f"\nShowing first 65,536 of {total:,} bytes. Export for the complete file.")
    return "\n".join(rows)


def find_all(data, needle, limit=64):
    """Offsets of `needle` in `data`, up to `limit` of them."""
    found, at = [], data.find(needle)
    while at >= 0 and len(found) < limit:
        found.append(at)
        at = data.find(needle, at + len(needle))
    return found


def folder_vram(project, node):
    """VRAM with every TIM beside a file uploaded: the textures of a model
    are the pictures shipped in its folder."""
    import numpy as np
    from formats.images import tim
    vram = np.zeros((512, 1024), np.uint16)
    folder = node.path.rsplit('/', 1)[0] + '/' if '/' in node.path else ''
    for entry in project.disc.files:
        rest = entry.path[len(folder):]
        if entry.path.startswith(folder) and '/' not in rest and rest.upper().endswith('.TIM') and entry.size < 4 << 20:
            try:
                tim.upload(vram, tim.parse(project.disc.read(entry)))
            except FormatError:
                continue
    return vram


def stock_preview(project, node, data, result):
    """Open a disc file that is in one of the console's stock formats, or
    an archive of them, whatever game it belongs to."""
    from formats.archive import containers
    from formats.audio import smf, sources as sound, vab
    from formats.images import tim
    name, upper = Path(node.path).name, node.path.upper()
    kind = containers.sniff(data)
    entries = project.disc.entries
    if upper.endswith('.WVD'):
        result['audio'] = ('Sounds', name, sound.wvd_sources(data))
    elif kind == 'TIM':
        result['tim'] = tim.parse(data)
    elif kind == 'TMD':
        from formats.models import tmd
        result['tmd'] = tmd.parse(data)
        result['vram'] = folder_vram(project, node)
    elif kind == 'MIDI':
        result['audio'] = ('Music', name, sound.sequence_sources(
            smf.to_seq(data), Path(name).stem, sound.disc_banks(project), near=node.path))
    elif kind == 'VAB':
        result['audio'] = ('Sounds', name, [sound.BankSource(name, vab.whole(data)[0])])
    elif kind == 'VAB header' or upper.endswith('.VB'):
        # A header and its waveforms are two files of one name.
        stem = upper.rsplit('.', 1)[0]
        head = data if kind == 'VAB header' else next(
            (project.disc.read(entries[stem + ext]) for ext in ('.VH', '.VA') if stem + ext in entries), b'')
        body = entries.get(stem + '.VB') if kind == 'VAB header' else node
        if vab.header_size(head) and body is not None:
            waves = data if body is node else project.disc.read(body)
            result['audio'] = ('Sounds', name, [sound.BankSource(Path(stem).name, vab.canonical(head, waves))])
    if any(key in result for key in ('audio', 'tim', 'tmd')) or data[:4] == b'pQES' \
            or project.by_source.get(node.path) or len(data) > 48 << 20:
        return
    layout, items = containers.contents(data)
    if layout in ('LVL', 'RAQ') or any(item.kind != 'Data' for item in items):
        result['contents'] = (layout, items)
    elif len(data) < 1 << 16 and readable(data):
        result['text'] = readable(data)


def readable(data):
    """The file as text if that is what it is, else ''. Configuration and
    script files are ASCII or Shift-JIS with ordinary line ends."""
    raw = bytes(data).rstrip(b'\0')
    if not raw or any(byte < 9 or 13 < byte < 32 for byte in raw):
        return ''
    for encoding in ('ascii', 'shift_jis'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ''


def executable_header(data):
    """What a PS-X EXE header says, as lines for the Information tab."""
    if bytes(data[:8]) != b'PS-X EXE' or len(data) < 0x800:
        return ''
    entry, _gp, base, size = struct.unpack_from('<4I', data, 0x10)
    stack = struct.unpack_from('<I', data, 0x30)[0]
    region = bytes(data[0x4C:0x80]).split(b'\0')[0].decode('ascii', 'replace')
    return (f'PlayStation executable\nLoads at: 0x{base:08X}\nCode and data: {size:,} bytes '
            f'(to 0x{base + size:08X})\nStarts at: 0x{entry:08X}\nStack: 0x{stack:08X}\n'
            + (f'Marker: {region}\n' if region else ''))


def prepare_preview(project, node, context=None):
    """Reuse expensive sprite context traces while browsing the same disc."""
    if not isinstance(node, Asset) or node.kind != 'SPR':
        return _prepare_preview(project, node, context)
    from collections import OrderedDict
    cache = project.__dict__.setdefault('sprite_preview_cache', OrderedDict())
    key = (node.ldar, node.group, node.record_offset, context)
    if key not in cache:
        from formats.sprites import preview_cache
        try:
            saved = preview_cache.cache_path(project, node, context)
        except OSError:
            saved = None
        result = preview_cache.load(saved, node) if saved else None
        if result is None:
            result = _prepare_preview(project, node, context)
            if saved:
                preview_cache.save(saved, result)
        cache[key] = result
    cache.move_to_end(key)
    result = cache[key]
    while len(cache) > 8:
        cache.popitem(last=False)
    return result


def _prepare_preview(project, node, context=None):
    result = {"node": node, "notes": [], "data": None, "preview_context": context}
    if isinstance(node, tuple):
        _, path, index = node
        result["group"] = project.ldars[path][index]
        result["vram"] = project.vram(path, index)
        if index:
            from formats.level.scene import build_scene
            result['level'] = build_scene(project, path, index)
        return result
    if isinstance(node, Asset):
        data = project.asset_data(node)
        result["data"] = data
        result["size"] = len(data)
        if node.kind in ('VH', 'WVD') and node.source and node.source.path.endswith(('.VH', '.VA', '.VB')):
            stock_preview(project, node.source, data, result)
        if node.kind in ("SPR", "WMD", "GRPX", "WPP"):
            groups = project.ldars[node.ldar]
            # Past the area's own groups the choice is a system screen, laid
            # over the area's base group.
            screen = None
            if node.kind == 'SPR':
                screens, first = bank_screens(project, node.ldar, (node.code >> 8) & 15)
                if context is not None and context >= len(groups):
                    screen = screens[context - len(groups)]
                elif context is None and first is not None:
                    screen = screens[first]
                if screen is not None:
                    context = 0
            context = node.group if context is None else context
            if node.kind in ('SPR', 'WPP') and context == 0 and len(project.ldars[node.ldar]) > 1 and screen is None:
                context = 1
            result["vram"] = project.vram(node.ldar, context, screen)
            # Resources loaded next to this one: its own group, the base and
            # the section chosen for VRAM.
            loaded = [a for i in dict.fromkeys((node.group, 0, context)) for a in groups[i].assets]
        if node.kind == "SPR":
            from formats.level.scene import sprite_pages
            from formats.sprites.wpp import parse_wpp
            frames = result["sprites"] = sprite_frames(data)
            if screen is None:
                from formats.level.town import shared_bank_preview
                town_bank = shared_bank_preview(project, node, context, frames)
                if town_bank is not None:
                    result.update(town_bank)
                    result['notes'].append(town_bank['context_note'])
                    return result
            if screen is not None:
                from formats.sprites.screens import screen_bank
                slot = (node.code >> 8) & 15
                vram, pages, cluts = screen_bank(project, node.ldar, screen, slot, frames)
                result.update(vram=vram, sprite_pages=pages, sprite_cluts=cluts,
                              sprite_origins={i: 'system screen code' for i in pages},
                              sprite_names={}, sprite_vrams={}, sprite_default=next(iter(pages.values()), 1),
                              sprite_unavailable={i for i, frame in enumerate(frames) if frame and i not in pages})
                result['notes'].append(f'System screen {screen}: pages and palettes traced from its code. '
                                      'Frames not initialized by this screen are listed without a guessed image. '
                                      'Choose another screen, or set a texture page and palette manually to inspect them.')
                return result
            from formats.level.runtime import table_pages
            slot = (node.code >> 8) & 15
            result['sprite_pages'] = sprite_pages(project, node.ldar, context).get(slot, {})
            from formats.level.scene import sprite_cluts, lend_palettes, sprite_owners, bank_sections, loaded_resources
            # The sections of the area that have this bank loaded, under
            # this record or another with the same bytes, in any slot.
            sections = [(index, their_slot) for path, index, their_slot in bank_sections(project, data)
                        if path == node.ldar and index]
            # A frame is named for the objects that show it, in this section
            # first and then in the others of the area.
            result['sprite_names'] = {}
            for index, their_slot in sorted(sections, key=lambda section: section[0] != context):
                for frame, users in sprite_owners(project, node.ldar, index).get(their_slot, {}).items():
                    known = result['sprite_names'].setdefault(frame, [])
                    known += [user for user in users if user not in known]
            result['sprite_cluts'] = dict(sprite_cluts(project, node.ldar, context).get(slot, {}))
            from formats.level.scene import sprite_coded
            result['sprite_pages'] = dict(result['sprite_pages'])
            origins = {frame: 'object code' for frame in sprite_coded(project, node.ldar, context).get(slot, ())}
            result['sprite_origins'], result['sprite_vrams'] = origins, {}
            # A bank can be shown by other sections than the one chosen:
            # their objects say which page a frame is on, and the frame is
            # drawn with their textures, which this section has not loaded.
            vrams, deferred = {}, []

            def from_section(frame, page, index, word, code):
                if index not in vrams:
                    vrams[index] = project.vram(node.ldar, index)
                result['sprite_pages'][frame] = page
                result['sprite_vrams'][frame] = vrams[index]
                origins[frame] = f'section {index - 1:02d}' + (' code' if code else '')
                if word is not None:
                    result['sprite_cluts'][frame] = word
                else:
                    result['sprite_cluts'].pop(frame, None)
            for index, their_slot in sections:
                if index == context:
                    continue
                theirs = sprite_pages(project, node.ldar, index).get(their_slot, {})
                coded = sprite_coded(project, node.ldar, index).get(their_slot, ())
                palettes = sprite_cluts(project, node.ldar, index).get(their_slot, {})
                # Through another record of the bank only what objects are
                # placed showing counts, not what their code goes on to show.
                other_record = loaded_resources(project, node.ldar, index).get(('SPR', their_slot)) is not node
                for frame, page in theirs.items():
                    if frame in coded:
                        # What another section's objects only go on to show
                        # ranks below this section's own routines.
                        if not other_record:
                            deferred.append((frame, page, index, palettes.get(frame)))
                        continue
                    if frame in result['sprite_pages'] and origins.get(frame) != 'object code':
                        continue
                    from_section(frame, page, index, palettes.get(frame), False)
            # Items are drawn with the page and the palette their descriptor
            # in the executable names, wherever they are placed.
            from formats.level.runtime import item_sprites
            code = next((a for a in loaded if a.kind == 'INS'), None)
            try:
                code = bytes(project.asset_data(code)) if code is not None else None
            except FormatError:
                code = None
            items = item_sprites(project, node.ldar, code, {slot: len(frames)}).get(slot, {})
            # The code loaded with the bank holds its animation scripts.
            runs = executable(project, node.ldar)
            if runs is not None:
                result['animation_code'] = ([('overlay', runs.build.overlay, code)] if code else []) + [
                    ('executable', runs.base, runs.data[0x800:])]
                # The game steps animations once per update, one update per
                # field: 50 a second on the European disc, 60 on the others.
                result['update_rate'] = 50 if 'European' in runs.build.name else 60
                from formats.level.scene import sprite_animations
                result['animation_users'] = sprite_animations(project, node.ldar, context).get(slot, {})
            if items:
                result['sprite_pages'] = dict(result['sprite_pages'])
            for frame, (page, word) in items.items():
                if frame not in result['sprite_pages']:
                    result['sprite_pages'][frame] = page
                    origins[frame] = 'item table'
                if word is not None:
                    result['sprite_cluts'].setdefault(frame, word)
            from formats.level.palettes import upload_sprite_pages
            for frame, page in upload_sprite_pages(project, node.ldar, context, frames).items():
                if frame not in result['sprite_pages'] or (origins.get(frame) == 'item table' and frame not in result['sprite_cluts']):
                    result['sprite_pages'][frame] = page
                    origins[frame] = 'texture and palette uploads'
            # What is left may be shown by objects nothing places: effects
            # other objects create. Their routines are run to find out.
            if screen is None and any(frame and i not in result['sprite_pages'] for i, frame in enumerate(frames)):
                from formats.level.scene import sprite_routines
                for frame, (page, word) in sprite_routines(project, node.ldar, context).get(slot, {}).items():
                    if frame not in result['sprite_pages']:
                        result['sprite_pages'][frame] = page
                        origins[frame] = 'routine'
                        if word is not None:
                            result['sprite_cluts'].setdefault(frame, word)
                result['sprite_styles'] = project.__dict__.get('sprite_style_cache', {}).get((node.ldar, context), {}).get(slot, {})
                result['animation_users'] = project.__dict__.get('sprite_animation_cache', {}).get((node.ldar, context), {}).get(slot, {})
            for frame, page, index, word in deferred:
                if frame not in result['sprite_pages']:
                    from_section(frame, page, index, word, True)
            # A frame this section does not place may be placed, with a
            # palette of its object's own, in another section of the area.
            from psx.graphics import palette_missing
            for other in groups[1:]:
                if other.index == context or not other.assets or not any(
                        i not in result['sprite_cluts'] and any(palette_missing(result['vram'], part[2]) for part in frame)
                        for i, frame in enumerate(frames)):
                    continue
                for frame, word in sprite_cluts(project, node.ldar, other.index).get(slot, {}).items():
                    result['sprite_cluts'].setdefault(frame, word)
            result['vram'], lent = lend_palettes(project, node.ldar, context, frames, result['vram'],
                                                 result['sprite_cluts'], data)
            result['sprite_styles'] = project.__dict__.get('sprite_style_cache', {}).get((node.ldar, context), {}).get(slot, {})
            if lent:
                here = sorted({group - 1 for _, donor, group in lent if donor == node.ldar})
                away = sorted({Path(donor).stem for _, donor, group in lent if donor != node.ldar})
                result['notes'].append(
                    f'{len(lent)} palettes this section does not load were taken from '
                    + ' and '.join(filter(None, (
                        here and 'section ' + ', '.join(f'{s:02d}' for s in here) + ' of the area',
                        away and 'the same bank in ' + ', '.join(away)))) + '.')
            from psx.graphics import guess_page
            # Pages where this bank's own group, then the section, start a
            # texture upload.
            starts = [a.rect[0] // 64 + a.rect[1] // 256 * 16
                      for i in dict.fromkeys((node.group, context)) for a in groups[i].assets
                      if a.rect and a.rect[3] >= 128]
            default = table_pages(project, node.ldar).get(slot)
            if screen is not None:
                # A system screen's bank starts where the screen's pictures do.
                starts = [a.rect[0] // 64 + a.rect[1] // 256 * 16
                          for a in project.ldars[system_table(node.ldar)][screen].assets
                          if a.rect and a.rect[3] >= 128]
                # The bank's art is the first picture the screen loads.
                default = min(starts) if starts else None
                result['notes'].append(
                    f'Drawn with the pictures of system load group {screen}, whose code reads this bank.')
            result['sprite_default'] = guess_page(frames, result['vram'], starts) if default is None else default
            from formats.level.scene import area_of, loaded_resources
            from formats.level.town import town_graphics
            town = town_graphics(project, loaded_resources(project, node.ldar, context),
                                  area_of(node.ldar), context - 1)
            if town is not None and slot == town.bank:
                result['sprite_pages'].update(town.pages)
                result['sprite_cluts'].update(town.cluts)
            elif not result['sprite_pages'] and executable(project, node.ldar) is not None:
                # A bank nothing places: the characters a town overlay spawns.
                from formats.level.town import character_pages
                known = executable(project, node.ldar)
                overlay = next((a for a in loaded if a.kind == 'INS'), None)
                if overlay is not None:
                    result['sprite_pages'] = character_pages(project.asset_data(overlay), known.build.overlay,
                                                             slot, len(frames))
            # What nothing in this area shows may be shown in another area
            # that loads the same bank. Such frames are drawn with that
            # area's textures unless this section holds the same pixels.
            # Another area may draw the bank with other art, so a frame that
            # shares a palette with one an object of this area shows stays
            # with it, and one whose palette is in the same column of VRAM
            # as a known frame's only takes a page that shows the same
            # pixels here.
            drawn = {i: {result['sprite_cluts'].get(i, part[2]) & 0x7FFF for part in frames[i]}
                     for i in result['sprite_pages'] if i < len(frames)}
            placed = set().union(*[words for i, words in drawn.items()
                                   if origins.get(i, 'object').startswith(('object', 'section'))])
            columns = {word & 63 for words in drawn.values() for word in words}
            unknown = [i for i, frame in enumerate(frames) if frame and i not in result['sprite_pages']
                       and not placed & {part[2] & 0x7FFF for part in frame}]
            if unknown and slot:
                from formats.sprites.shared import other_areas
                elsewhere = other_areas(project, node, data, frames, unknown, result['vram'],
                                        [i for i in unknown if columns & {part[2] & 63 for part in frames[i]}])
                for frame, (page, word, vram, origin, names) in elsewhere.items():
                    result['sprite_pages'][frame] = page
                    origins[frame] = origin
                    if word is not None:
                        result['sprite_cluts'][frame] = word
                    if vram is not None:
                        result['sprite_vrams'][frame] = vram
                    known = result['sprite_names'].setdefault(frame, [])
                    known += [name for name in names if name not in known]
            # Tomba's own banks have no pixels in VRAM; a picture bank with
            # one entry per frame supplies them.
            for candidate in loaded:
                if candidate.kind == 'WPP':
                    try:
                        kind, pictures = parse_wpp(project.asset_data(candidate))
                    except (FormatError, ValueError):
                        continue
                    if kind == 'frames' and len(pictures) == len(frames):
                        result['pictures'] = pictures
                        if slot == 0 and 'animation_code' in result:
                            from formats.sprites.animations import player_scripts
                            result['animation_users'] = player_scripts(result['animation_code'], len(frames)) or result['animation_users']
                        break
        if node.kind == 'WPP':
            from formats.sprites.wpp import parse_wpp
            result['wpp'] = kind, pictures = parse_wpp(data)
            for candidate in loaded:
                if candidate.kind != 'SPR' or kind != 'frames':
                    continue
                try:
                    frames = sprite_frames(project.asset_data(candidate))
                except FormatError:
                    continue
                if len(frames) == len(pictures):
                    result['paired_sprites'] = frames
                    result['paired_asset'] = candidate
                    result['paired_tomba'] = (candidate.code >> 8) & 15 == 0
                    known = executable(project, node.ldar)
                    overlay = next((a for a in reversed(loaded) if a.kind == 'INS'), None)
                    if known is not None:
                        regions = ([('overlay', known.build.overlay, project.asset_data(overlay))] if overlay else [])
                        regions += [('executable', known.base, known.data[0x800:])]
                        result['animation_code'] = regions
                        result['update_rate'] = 50 if 'European' in known.build.name else 60
                        from formats.sprites.animations import player_scripts
                        if result['paired_tomba']:
                            result['animation_users'] = player_scripts(regions, len(frames))
                        else:
                            from formats.level.scene import sprite_animations
                            result['animation_users'] = sprite_animations(project, node.ldar, context).get(candidate.slot, {})
                    result['paired_key'] = labels.content_key(project.asset_data(candidate))
                    break
        if node.kind == 'APD':
            from formats.level.scene import build_scene
            section = context if context is not None else node.group
            if not section and len(project.ldars[node.ldar]) > 1:
                section = 1
            if section:
                result['placement_scene'] = build_scene(project, node.ldar, section)
        if node.kind == "WMD":
            result["meshes"] = parse_wmd(data)
        if node.kind == 'FOUR':
            from formats.models.four import parse_four
            from formats.level.scene import loaded_resources
            context = node.group or (1 if len(project.ldars[node.ldar]) > 1 else 0)
            result['four'] = parse_four(data)
            result['vram'] = project.vram(node.ldar, context)
            result['four_candidates'] = []
            for (kind, slot), asset in loaded_resources(project, node.ldar, context).items():
                if kind == 'WMD':
                    for i, mesh in enumerate(parse_wmd(project.asset_data(asset))):
                        result['four_candidates'].append((f'WMD {asset.code:04X} model {i:03d}', mesh, (slot, i)))
            result['four_preferred'] = ((1, (node.code >> 8) - 0x40 + 1)
                if area_number(node.ldar) == 0 and 0x40 <= node.code >> 8 <= 0x42 else None)
    else:
        if node.directory:
            result["folder"] = node
            return result
        result["raw"] = project.disc.read(node, 65536)
        result["size"] = node.size
        from formats.audio import sources as sound
        # A file of streaming sectors is not read as bytes: its sound is in
        # the part of each sector an ordinary read leaves out.
        stream = sound.stream_kind(project.disc, node)
        if stream == 'movie' or not stream and node.path.upper().endswith('.STR'):
            result['movie'] = node.path
            return result
        if stream:
            first, count = project.disc.start + node.lba, (node.size + 2047) // 2048
            source = (sound.XaSource if stream == 'xa' else sound.PcmSource)(node.path, project.disc.path, first, count)
            result['audio'] = ('Streams' if stream == 'xa' else 'CD audio', Path(node.path).name, [source])
            return result
        if node.size > 64 * 1024 * 1024:
            result["notes"].append("Large file: preview limited to the first 64 KiB.")
            return result
        data = project.payload(node)
        result["data"] = data
        result["size"] = len(data)
        stock_preview(project, node, data, result)
    if 'audio' not in result and (isinstance(node, Asset) and node.kind == 'WVD' or data[:4] == b'pQES'):
        from formats.audio import sources as sound
        source = node.source.path if isinstance(node, Asset) and node.source else getattr(node, 'path', '')
        name = Path(source).name or 'Sound'
        if data[:4] == b'pQES':
            from formats.archive.containers import sequence
            sound_build = executable(project, node.ldar if isinstance(node, Asset) else None)
            resident = sound.resident_banks(project, node.ldar, node.group) if isinstance(node, Asset) else None
            music_bank = (2 if resident and any(a.kind == 'VH' for a in project.ldars[node.ldar][0].assets)
                          else 2 if sound_build and sound_build.build.early else 1)
            result['audio'] = ('Music', name, sound.sequence_sources(
                sequence(data)[0] or data, Path(source).stem or 'Sequence', sound.disc_banks(project), near=source,
                embedded_area=area_number(node.ldar) if isinstance(node, Asset) and node.kind == 'SEQ' else None,
                resident=resident, embedded_bank=music_bank))
        else:
            result['audio'] = ('Sounds', name, sound.wvd_sources(data))
    from formats.annotate import regions
    name = Path(node.path).name.upper() if isinstance(node, DiscEntry) else ''
    kind = node.kind if isinstance(node, Asset) else 'INS' if name.startswith('X') and name.endswith('.BIN') else ''
    known = executable(project, node.ldar if isinstance(node, Asset) else None)
    result['overlay_base'] = known.build.overlay if known else None
    result['regions'] = regions(kind, data, result['overlay_base'])
    if bytes(data[:4]) == b'W\x00S\x00':
        # An event script: listed as the instructions it is made of.
        from formats.script.wss import Wss, game_ops
        try:
            result['script'] = Wss(data, game_ops(known.build.script_tail if known else None)).listing()
        except FormatError as exc:
            result['notes'].append(f'WSS script: {exc}')
    # WFM can also be embedded in instruction binaries and standalone GAMs.
    wfms = []
    from formats.text.wfm import MAGICS
    starts = sorted(at for magic in MAGICS for at in find_all(data, magic))
    from formats.text.titles import attach, language_of
    for start in starts[:16]:
        try:
            wfm = Wfm(data[start:])
        except FormatError as exc:
            result["notes"].append(f"WFM candidate at {start:X}: {exc}")
            continue
        # Event titles take their spaces and line breaks from the overlays.
        if isinstance(node, Asset):
            laid = attach(wfm, project, table_name(node.ldar)[0])
        else:
            laid = attach(wfm, project, language_of(getattr(node, 'path', '')))
        if laid:
            result["notes"].append(f"{laid} event titles are spaced and broken into lines as the "
                                   "game lays them out; the bank itself holds only their letters.")
        wfms.append((start, wfm))
    result["wfms"] = wfms
    return result


def tolerant_console():
    """Let selection lines carry any text. Names on a disc can be Japanese,
    and a console in a Western code page refuses to print them."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(errors='replace')
            except (ValueError, OSError):
                pass


class MainWindow(QMainWindow):
    labels_indexed = pyqtSignal(int, object, object)
    def eventFilter(self, watched, event):
        if (event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress)
                and event.key() == Qt.Key.Key_F2 and QApplication.activeModalWidget() is None
                and isinstance(watched, QWidget) and watched.window() is self):
            if event.type() == QEvent.Type.KeyPress and not self.loading.isVisible():
                self.rename_selected()
            event.accept()
            return True
        if event.type() == QEvent.Type.MouseButtonPress:
            widget = watched
            clicked_list = False
            while isinstance(widget, QWidget):
                if widget is getattr(self, 'disc_tree', None):
                    self.rename_target = None
                    break
                if hasattr(widget, 'rename_selection'):
                    self.rename_target = widget
                    break
                clicked_list = clicked_list or isinstance(widget, QAbstractItemView)
                if widget is self and clicked_list:
                    self.rename_target = False
                widget = widget.parentWidget()
        return super().eventFilter(watched, event)

    def __init__(self, label_path=None):
        super().__init__()
        tolerant_console()
        self.settings = QSettings()
        from game.label_autosave import LabelAutosave
        self.label_autosave = LabelAutosave(label_path)
        self.saved_label_snapshot = None
        from game.sprite_checks import default_store, SpriteChecks
        try:
            self.sprite_checks = (SpriteChecks(self.label_autosave.path.with_name('sprite_checks.json'))
                                  if label_path else default_store())
        except (OSError, ValueError, TypeError) as exc:
            self.sprite_checks = SpriteChecks(self.label_autosave.path.with_name('sprite_checks.json'))
            print(f'Could not migrate old sprite reviews: {exc}', flush=True)
        self.review_items = {}
        try:
            self.label_autosave.migrate(self.settings)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Cannot autosave labels',
                                f'{self.label_autosave.path}\n\n{exc}\nExisting label files have not been overwritten.')
        self.load_glyphs()
        self.project = None
        self.current_node = None
        self.current_data = None
        self.generation = 0
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.label_pool = QThreadPool(self)
        self.label_pool.setMaxThreadCount(1)
        self.label_index_epoch = 0
        self.label_index_running = False
        self.labels_indexed.connect(self.apply_label_index)
        self.asset_items = {}
        self.file_items = {}
        self.tree_icons = {}
        self.labels = labels.LabelSet()
        self.builtin_labels = {}
        self.label_hashes = {}
        self.persistent = set()
        self.sprite_states = {}
        self.restore_tab = None
        self.setWindowTitle(f"TombaEdit {version}")
        from gui.widgets.loading import LoadingOverlay
        self.loading = LoadingOverlay(self)
        self.rename_target = None
        QApplication.instance().installEventFilter(self)
        self.setWindowIcon(icon("app"))
        self.resize(1380, 880)
        self.setAcceptDrops(True)
        self.build_ui()
        self.set_theme(self.settings.value("theme", "dark"))
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.welcome()

    def action(self, menu, label, callback, shortcut=None):
        action = QAction(label, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    def build_ui(self):
        file_menu = self.menuBar().addMenu("&File")
        open_action = self.action(file_menu, "&Open BIN / CUE / ISO...", self.open_dialog, QKeySequence.StandardKey.Open)
        open_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveDVDIcon))
        self.export_action = self.action(file_menu, "Export decoded &file (binary)...", self.export_payload, "Ctrl+E")
        self.raw_action = self.action(file_menu, "Export original disc &file...", self.export_raw)
        self.action(file_menu, "Export &text...", self.export_text, "Ctrl+T")
        file_menu.addSeparator()
        self.action(file_menu, "E&xit", self.close, "Alt+F4")
        view = self.menuBar().addMenu("&View")
        self.action(view, "Collapse tree", lambda: self.current_tree().collapseAll())
        self.action(view, "Expand tree", lambda: self.current_tree().expandAll())
        self.map_action = self.action(view, "Game &map", self.open_game_map)
        self.map_action.setToolTip('Open the world map used by the Select-menu Map screen.')
        self.map_action.setEnabled(False)
        themes = self.menuBar().addMenu("&Settings").addMenu("Theme")
        group = QActionGroup(self)
        self.theme_actions = {}
        for key, label in [("dark", "Classic Dark (default)"), ("bright", "Classic Bright")]:
            a = QAction(label, self, checkable=True)
            a.triggered.connect(lambda checked, theme=key: self.set_theme(theme))
            group.addAction(a)
            themes.addAction(a)
            self.theme_actions[key] = a
        label_menu = self.menuBar().addMenu('&Labels')
        self.action(label_menu, 'Rename selected...', self.rename_selected, 'F2')
        self.action(label_menu, 'Import labels...', self.import_labels)
        self.action(label_menu, 'Export labels...', self.export_labels)
        label_menu.addSeparator()
        self.action(label_menu, 'Import glyph characters...', self.import_glyphs)
        self.action(label_menu, 'Export glyph characters...', self.export_glyphs)
        if not getattr(sys, 'frozen', False):
            self.action(label_menu, 'Save glyph characters as built-in', self.save_builtin_glyphs)
        if not getattr(sys, 'frozen', False):
            # Running from source: names can be made part of the tool.
            self.action(label_menu, 'Save as built-in labels', self.save_builtin_labels)
        help_menu = self.menuBar().addMenu("&Help")
        self.action(help_menu, "About / supported formats", self.about)
        toolbar = QToolBar("File", self)
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.addAction(open_action)
        self.export_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        toolbar.addSeparator()
        toolbar.addAction(self.export_action)
        self.addToolBar(toolbar)
        self.split = QSplitter()
        left = QWidget()
        layout = QVBoxLayout(left)
        layout.setContentsMargins(4, 4, 4, 4)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter files, areas, types or offsets...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_tree)
        layout.addWidget(self.search)
        self.disc_tree = self.make_tree()
        self.area_tree = self.disc_tree
        self.navigation = self.disc_tree
        layout.addWidget(self.disc_tree)
        self.count_label = QLabel("No disc open")
        layout.addWidget(self.count_label)
        self.split.addWidget(left)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 4, 4, 4)
        self.path_label = QLabel("TombaEdit")
        self.path_label.setTextFormat(Qt.TextFormat.PlainText)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        rl.addWidget(self.path_label)
        self.context = QComboBox()
        self.context.setToolTip("Choose the section whose texture and CLUT uploads should be applied to this resource")
        self.context.currentIndexChanged.connect(self.context_changed)
        self.context.hide()
        rl.addWidget(self.context)
        self.tabs = QTabWidget()
        rl.addWidget(self.tabs)
        # A stable GL child exists before the top-level window is shown.
        self.model_view = ModelView()
        self.tabs.addTab(self.model_view, 'Geometry')
        self.persistent.add(self.model_view)
        self.map_view = ModelView()
        self.persistent.add(self.map_view)
        from formats.level.viewer import LevelView
        from formats.models.four_viewer import FourView
        self.level_view = LevelView()
        self.level_view.open_resource.connect(self.jump_asset)
        self.level_view.open_location.connect(self.jump_group)
        self.four_view = FourView()
        for viewer, title in ((self.level_view, 'Level editor'), (self.four_view, 'Deformation')):
            self.tabs.addTab(viewer, title)
            self.persistent.add(viewer)
        self.split.addWidget(right)
        self.split.setSizes([440, 940])
        self.split.setStretchFactor(1, 1)
        self.setCentralWidget(self.split)
        self.export_action.setEnabled(False)
        self.raw_action.setEnabled(False)
        self.statusBar().showMessage("Open a Tomba! data-track BIN, CUE or ISO.")

    def make_tree(self):
        tree = ResourceTree()
        tree.setHeaderLabels(["Name / resource", "Label", "Bytes", "SPR", "ANIM"])
        tree.headerItem().setToolTip(3, 'Sprite review. Drag the column edge to expand.')
        tree.headerItem().setToolTip(4, 'Animation review. Drag the column edge to expand.')
        tree.header().moveSection(3, 0)
        tree.header().moveSection(tree.header().visualIndex(4), 1)
        tree.header().setMinimumSectionSize(24)
        for column in (3, 4):
            tree.header().setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            tree.setColumnWidth(column, 30)
            item_font = tree.headerItem().font(column)
            item_font.setPointSize(7)
            tree.headerItem().setFont(column, item_font)
        tree.setTreePosition(0)
        from gui.widgets.columns import elide_at_view_edge
        elide_at_view_edge(tree)
        tree.setColumnWidth(0, 370)
        tree.setColumnWidth(1, 160)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(False)
        tree.setStyleSheet("QTreeWidget::item:selected {background-color: #555555; color: white;} QTreeWidget::item:selected:!active {background-color: #494949; color: white;}")
        tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        tree.currentItemChanged.connect(lambda item, old: self.select_item(item))
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(lambda point: self.context_menu(tree, point))
        return tree

    def set_theme(self, theme):
        theme = theme if theme in self.theme_actions else "dark"
        apply_theme(theme == "dark")
        self.theme_actions[theme].setChecked(True)
        self.settings.setValue("theme", theme)

    def current_tree(self):
        return self.disc_tree

    def clear_tabs(self):
        while self.tabs.count():
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            widget.hide()
            if widget not in self.persistent:
                widget.deleteLater()

    def welcome(self):
        self.clear_tabs()
        self.tabs.addTab(text_view(
            f"TombaEdit {version}\n\nOpen a BIN / CUE / ISO from File > Open or drop it here.\n\n"
            "Disc folders\n  The original ISO9660 directory and files. Expand a file to inspect its LDAR resources.\n\n"
            "Areas / sections\n  Base resources and section-specific load groups, named from the area reference.\n"
            "  Select a group to inspect its load records and reconstructed VRAM.\n\n"
            "Viewers\n  Level editor with placed models, animated sprites and collision\n"
            "  WMD models and FOUR deformations\n  SPR frames and WPP picture banks\n"
            "  VRAM with palette crosshair\n  WHM collision planes and CLM maps\n"
            "  WFM3 dialogue and font atlas\n  Music, sample banks and movies\n\n"
            "Assets can be browsed and exported. Discs are not modified."
        ), "Welcome")

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Tomba! disc", self.settings.value("last_dir", str(Path.cwd() / "rom")),
                                              "Disc images (*.cue *.bin *.iso *.img *.ccd);;All files (*)")
        if path:
            self.open_path(path)

    def submit(self, callback, receiver):
        self.generation += 1
        self.pool.clear()
        self.loading.begin(self.statusBar().currentMessage())
        def finished(generation, result, error):
            if generation != self.generation:
                return
            try:
                receiver(generation, result, error)
            finally:
                self.loading.hide()
        self.pool.start(Job(self.generation, callback, finished))

    def open_path(self, path):
        self.statusBar().showMessage("Reading disc folders and resolving LDAR file links...")
        self.disc_tree.setEnabled(False)
        self.export_action.setEnabled(False)
        self.raw_action.setEnabled(False)
        self.submit(lambda: Project(path), self.opened)

    def open_game_map(self):
        """Show the dedicated world-map model, with the system screen VRAM.

        SUBMAP.WMD is not ordinary area geometry. LDAR system group 07 loads
        it together with the artwork and palette used by the pause-menu Map
        screen, so it must use that group's final VRAM state.
        """
        if self.project is None:
            return
        assets = self.project.by_source.get('SYSTEM/SUBMAP.WMD', [])
        asset = next((item for item in assets if item.ldar == 'SYS/LDSYS.BIN' and item.group == 7), None)
        if asset is None:
            QMessageBox.information(self, 'Game map',
                                    'This disc does not provide the SYSTEM/SUBMAP.WMD world-map resource.')
            return
        self.statusBar().showMessage('Loading game map...')
        self.submit(lambda: prepare_preview(self.project, asset, 7), self.game_map_ready)

    def game_map_ready(self, generation, result, error):
        if generation != self.generation:
            return
        if error:
            QMessageBox.warning(self, 'Game map unavailable', error)
            self.statusBar().showMessage('Game map unavailable')
            return
        meshes, vram = result.get('meshes'), result.get('vram')
        if not meshes or vram is None:
            QMessageBox.warning(self, 'Game map unavailable', 'SYSTEM/SUBMAP.WMD did not decode as a map model.')
            self.statusBar().showMessage('Game map unavailable')
            return
        source = result['node']
        key = labels.content_key(result['data'])
        def rename(rows, name):
            for row in rows:
                self.labels.rename(key, name, kind='World map model', start=meshes[row].offset)
            self.persist_labels()
        self.map_view.set_data(meshes, vram, source.code, {0: 'World map'}, rename,
                               spread=False, label_lookup=lambda _row: self.labels.label_for(key))
        self.map_view.canvas.stats_label.setText(
            'Select-menu Map | SYSTEM/SUBMAP.WMD | system group 07 VRAM\n'
            'F: frame selected | Double-click a row: frame it')
        self.map_view.canvas.stats_label.adjustSize()
        existing = self.tabs.indexOf(self.map_view)
        if existing < 0:
            existing = self.tabs.addTab(self.map_view, 'Game map')
        self.tabs.setCurrentIndex(existing)
        self.statusBar().showMessage('Game map ready')

    def opened(self, generation, project, error):
        if generation != self.generation:
            return
        self.disc_tree.setEnabled(True)
        if error:
            self.statusBar().showMessage("Could not open disc")
            QMessageBox.warning(self, "Cannot open disc", error)
            return
        self.project = project
        self.map_action.setEnabled(any(item.ldar == 'SYS/LDSYS.BIN' and item.group == 7
                                       for item in project.by_source.get('SYSTEM/SUBMAP.WMD', [])))
        self.label_index_epoch += 1
        self.label_pool.clear()
        self.label_index_running = False
        self.review_items.clear()
        self.label_hashes.clear()
        self.label_hashes.update(project.__dict__.get('label_content_hashes', {}))
        serial = Path(project.catalog.executable).name if project.catalog else project.disc.volume
        from game.label_store import local_identity
        self.labels = labels.LabelSet(name=project.disc.source.stem, build=local_identity(project), serial=serial)
        # The names that come with the tool for this build, from its labels
        # folder; names given on this machine are laid over them.
        self.builtin_labels = {}
        try:
            from game.label_store import builtin_library
            shipped = builtin_library(serial, build=self.labels.build)
            self.labels.entries.update(shipped.entries)
            self.labels.bins.update(shipped.bins)
            self.labels.areas.update(shipped.areas)
            self.builtin_labels = {key: entry.name for key, entry in shipped.entries.items()}
        except ValueError:
            pass
        from game.label_autosave import snapshot
        try:
            own = self.label_autosave.load(self.labels.build, serial)
            self.labels.entries.update(own.entries)
            self.labels.bins.update(own.bins)
            self.labels.areas.update(own.areas)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Cannot load saved labels', f'{self.label_autosave.path}\n\n{exc}')
        self.saved_label_snapshot = snapshot(self.labels)
        self.context.hide()
        self.current_node = None
        self.current_data = None
        self.asset_items.clear()
        self.file_items.clear()
        self.search.clear()
        self.disc_tree.blockSignals(True)
        self.disc_tree.setUpdatesEnabled(False)
        self.disc_tree.clear()
        self.populate_disc(project.disc.root, self.disc_tree.invisibleRootItem())
        languages = sorted({table_name(path)[0] for path in project.ldars} - {None})
        first_language = languages[0] if languages else None
        other_languages = {}
        for path, groups in sorted(project.ldars.items(), key=lambda kv: (table_name(kv[0])[0] or 0, kv[0])):
            area = area_number(path)
            directory = f'AREA{area:02d}' if area >= 0 else 'SYS'
            parent = self.file_items.get(directory)
            if parent is None:
                parent = next((item for name, item in self.file_items.items()
                               if name.endswith('/' + directory)), None)
            if parent is None:
                parent = self.disc_tree.invisibleRootItem()
            tongue = table_name(path)[0]
            if tongue in (None, first_language):
                root = self.item(parent, 'Sections', ('sections', path, 0))
                parent.takeChild(parent.indexOfChild(root))
                parent.insertChild(0, root)
            else:
                # The other languages of a disc that has several are the
                # same sections again with their own text: kept together,
                # one folder a language, below the first language's.
                others = other_languages.get(id(parent))
                if others is None:
                    others = self.item(parent, 'Other languages', ('languages', path, 0))
                    parent.takeChild(parent.indexOfChild(others))
                    parent.insertChild(1, others)
                    other_languages[id(parent)] = others
                root = self.item(others, language_name(tongue), ('sections', path, 0))
            root.setToolTip(0, f'{path}: base load group followed by sections in LDAR order')
            for g in groups:
                label = "Base - Shared area resources" if g.index == 0 else f"Section {g.index - 1:02d} - {section_name(area, g.index - 1)}"
                group_item = self.item(root, label, ("group", path, g.index))
                group_item.setToolTip(0, f"{path} | Load group {g.index} | LDAR offset 0x{g.offset:X}")
                for asset in g.assets:
                    item = self.item(group_item, asset.label, asset, asset.size)
                    self.asset_items[(path, asset.record_offset)] = item
        self.disc_tree.blockSignals(False)
        self.disc_tree.setUpdatesEnabled(True)
        self.setWindowTitle(f"TombaEdit {version} - {project.disc.source.name}")
        self.settings.setValue("last_dir", str(project.disc.source.parent))
        assets = sum(len(g.assets) for gs in project.ldars.values() for g in gs)
        self.count_label.setText(f"{len(project.disc.files):,} files | {len(project.ldars)} LDARs | {assets:,} resources")
        self.clear_tabs()
        self.path_label.setText(str(project.disc.source))
        catalog = project.catalog
        summary = f"Disc: {project.disc.source}\nData track: {project.disc.path}\nSector size: {project.disc.stride}\nVolume: {project.disc.volume or '(unnamed)'}\n\n{self.count_label.text()}\n"
        if catalog:
            summary += f"\nFile-link table: {catalog.executable} +0x{catalog.offset:X}\n{catalog.matched:,} links matched to disc files.\n"
        if project.warnings:
            summary += "\nDiagnostics\n" + "\n".join(project.warnings)
        summary += "\nSelect a file or expand an area/section to open its resources."
        self.tabs.addTab(text_view(summary), "Disc overview")
        self.refresh_labels()
        self.refresh_review_status()
        if self.labels.entries:
            self.index_labels()
        self.statusBar().showMessage("Disc ready" + (f" | {len(project.warnings)} diagnostic(s); see overview" if project.warnings else ""))

    def item(self, parent, label, node, size=None):
        item = QTreeWidgetItem(parent, [label, '', f"{size:,}" if size is not None else ""])
        item.setData(0, ROLE, node)
        if isinstance(node, Asset) and node.kind == 'SPR':
            self.review_items.setdefault((node.ldar, node.group, node.record_offset), []).append(item)
        folder = isinstance(node, tuple) or isinstance(node, DiscEntry) and node.directory
        standard = QStyle.StandardPixmap.SP_DirIcon
        if isinstance(node, tuple) and node[0] == 'group':
            item.setIcon(0, icon('LEVEL'))      # a load group opens as a level
        elif folder:
            if standard not in self.tree_icons:
                self.tree_icons[standard] = self.style().standardIcon(standard)
            item.setIcon(0, self.tree_icons[standard])
        else:
            kind = node.kind if isinstance(node, Asset) else Path(node.path).suffix[1:].upper()
            if isinstance(node, DiscEntry) and Path(node.path).name.upper().startswith('CLUT'):
                kind = 'CLUT'
            if isinstance(node, DiscEntry) and Path(node.path).stem.upper().startswith('LD') \
                    and table_name(node.path) != (None, -1):
                kind = 'LDAR'
            item.setIcon(0, icon(kind))
        item.setData(0, ROLE + 1, label)
        return item

    def populate_disc(self, folder, parent):
        for e in sorted(folder.children, key=lambda e: (not e.directory, e.path)):
            label = e.path.split("/")[-1]
            if e.directory and label.startswith("AREA") and label[4:].isdigit():
                label += f" - {AREAS.get(int(label[4:]), 'Unknown area')}"
            item = self.item(parent, label, e, None if e.directory else e.size)
            item.setToolTip(0, f"{e.path}\nLBA {e.lba} | {e.size:,} bytes")
            self.file_items[e.path] = item
            if e.directory:
                self.populate_disc(e, item)
            else:
                seen = set()
                for asset in self.project.by_source.get(e.path, []):
                    key = (asset.code, asset.offset, asset.size, asset.ldar, asset.group)
                    if key not in seen:
                        context = "base" if asset.group == 0 else f"section {asset.group - 1:02d}"
                        self.item(item, f"{asset.label} ({context})", asset, asset.size)
                        seen.add(key)

    def select_item(self, item):
        if not item or not self.project:
            return
        node = item.data(0, ROLE)
        self.restore_tab = None
        if isinstance(node, DiscEntry) and not node.directory and item.childCount():
            item.setExpanded(True)
        self.current_node = node
        self.context.blockSignals(True)
        self.context.clear()
        has_context = isinstance(node, Asset) and node.kind in ("SPR", "WMD", "GRPX", "WPP", "APD")
        self.context.setVisible(has_context)
        if has_context:
            area = area_number(node.ldar)
            for g in self.project.ldars[node.ldar]:
                name = "Base only" if not g.index else f"Base + section {g.index - 1:02d} - {section_name(area, g.index - 1)}"
                self.context.addItem("VRAM: " + name)
            default = node.group
            if default == 0 and node.kind in ("SPR", "WMD", "WPP") and self.context.count() > 1:
                default = 1
            if node.kind == 'SPR':
                # System screens whose code reads this bank, after the
                # area's own groups.
                screens, first = bank_screens(self.project, node.ldar, (node.code >> 8) & 15)
                system = self.project.ldars.get(system_table(node.ldar), [])
                for screen in screens:
                    code = next((Path(a.source.path).name for a in system[screen].assets
                                 if a.kind == 'INS' and a.source), 'code')
                    self.context.addItem(f'VRAM: Base + system group {screen:02d} ({code})')
                if first is not None:
                    default = len(self.project.ldars[node.ldar]) + first
            self.context.setCurrentIndex(default)
        self.context.blockSignals(False)
        if isinstance(node, Asset):
            print(f'Selected Item: {item.text(0)} | type 0x{node.code:04X} | '
                  f'offset 0x{node.offset:X}, {node.size:,} bytes | {node.ldar} group {node.group}')
        elif isinstance(node, DiscEntry):
            print(f'Selected Item: {node.path} | LBA {node.lba} | {node.size:,} bytes')
        else:
            print(f'Selected Item: {item.text(0)} | {node[1]} load group {node[2]}')
        self.load_selection(item.text(0))

    def context_changed(self):
        if self.current_node is not None:
            # Same resource under another section's VRAM: come back to the
            # tab that was open.
            self.restore_tab = self.tabs.tabText(self.tabs.currentIndex())
            self.load_selection(self.path_label.text())

    def load_selection(self, title):
        node = self.current_node
        self.current_data = None
        self.export_action.setEnabled(False)
        self.raw_action.setEnabled(False)
        self.path_label.setText(title)
        if isinstance(node, DiscEntry) and node.directory:
            self.generation += 1
            self.pool.clear()
            self.preview_ready(self.generation, prepare_preview(self.project, node), '')
            return
        self.statusBar().showMessage(f'Decoding {title}...')
        project = self.project
        context = self.context.currentIndex() if self.context.isVisible() else None
        # The viewer on screen stays until its replacement is ready.
        self.submit(lambda: prepare_preview(project, node, context), self.preview_ready)
    def preview_ready(self, generation, result, error):
        if generation != self.generation:
            return
        self.clear_tabs()
        if error:
            self.tabs.addTab(text_view(error + "\n\nThis resource could not be decoded. Its original disc file can still be exported."), "Diagnostic")
            self.raw_action.setEnabled(self.source_entry() is not None)
            self.statusBar().showMessage("Preview unavailable")
            return
        node = result["node"]
        self.current_data = result.get("data")
        if self.current_data is not None:
            self.remember_label_hash(node, labels.content_key(self.current_data))
            self.refresh_labels()
        self.export_action.setEnabled(self.current_data is not None)
        self.raw_action.setEnabled(self.source_entry() is not None)
        try:
            if "folder" in result:
                folder = result["folder"]
                self.add_table([(e.path.split("/")[-1], self.node_label(e), "Folder" if e.directory else Path(e.path).suffix,
                                 str(e.size), str(e.lba)) for e in folder.children],
                               ["Name", "Label", "Type", "Bytes", "LBA"], "Contents",
                               lambda row: self.jump_file(folder.children[row].path))
            if "group" in result:
                group = result["group"]
                if 'level' in result:
                    self.level_view.set_scene(result['level'])
                    self.tabs.addTab(self.level_view, 'Level editor')
                self.asset_table(group.assets)
            if 'four' in result:
                self.four_view.set_four(result['four'], result['four_candidates'],
                                        result['vram'], result['four_preferred'])
                self.tabs.addTab(self.four_view, 'Deformation')
            if 'movie' in result:
                from formats.movie.movie_panel import MoviePanel
                self.tabs.addTab(MoviePanel(self.project, result['movie']), 'Movie')
            if 'audio' in result:
                from formats.audio.audio_viewer import AudioView
                tab, title, found = result['audio']
                for source in found:
                    source.labels = self.labels
                self.tabs.addTab(AudioView(found, title, self.labels, self.persist_labels,
                                           self.export_stem(node)), tab)
            if 'tim' in result:
                from formats.images.tim_viewer import TimView
                self.tabs.addTab(TimView(result['tim']), 'Picture')
            if 'text' in result:
                self.tabs.addTab(text_view(result['text']), 'Text')
            if 'tmd' in result:
                from formats.models.tmd import jointed
                self.model_view.set_data(result['tmd'], result['vram'], level=False, spread=jointed(result['tmd']))
                self.tabs.addTab(self.model_view, 'Model')
            if 'contents' in result:
                from formats.archive.container_viewer import ContainerView
                from formats.audio.sources import disc_banks
                project = self.project
                self.tabs.addTab(ContainerView(result['contents'][0], result['contents'][1], node.path,
                                               lambda: disc_banks(project), self.labels, self.persist_labels),
                                 'Contents')
            if "meshes" in result:
                meshes = result['meshes']
                keys = [labels.content_key(self.current_data[m.offset:
                    meshes[i + 1].offset if i + 1 < len(meshes) else len(self.current_data)])
                    for i, m in enumerate(meshes)]
                def rename_models(rows, name):
                    for row in rows:
                        self.labels.rename(keys[row], name, kind='WMD model', start=meshes[row].offset)
                    self.persist_labels()
                self.model_view.set_data(meshes, result['vram'], node.code, None, rename_models,
                                         label_lookup=lambda row: self.labels.label_for(keys[row]))
                self.tabs.addTab(self.model_view, "Geometry")
            if "sprites" in result:
                renderer = None
                if 'pictures' in result:
                    from formats.sprites.wpp import renderer as picture_renderer
                    renderer = picture_renderer(result['sprites'], result['pictures'], result['vram'],
                                                (node.code >> 8) & 15 == 0)
                view = SpriteView(result['sprites'], result['vram'], result.get('sprite_pages'), renderer,
                                  result.get('sprite_default'), result.get('sprite_cluts'),
                                  styles=result.get('sprite_styles'), origins=result.get('sprite_origins'),
                                  frame_vrams=result.get('sprite_vrams'), unavailable=result.get('sprite_unavailable'))
                view.set_names(result.get('sprite_names', {}))
                view.set_labels(self.labels, self.persist_labels)
                if node.kind == 'SPR':
                    from game.sprite_checks import review_target
                    view.set_check_target(review_target(self.project, node, self.current_data,
                                                       result.get('preview_context'), len(result['sprites'])),
                                          store=self.sprite_checks)
                    view.check_bar.review_changed.connect(self.refresh_review_status)
                key = self.node_key(node)
                view.restore_state(self.sprite_states.get(key, []))
                view.selection_changed.connect(lambda state, k=key: self.sprite_states.__setitem__(k, state))
                self.tabs.addTab(view, 'Sprites')
                if 'animation_code' in result:
                    from formats.sprites.anim_viewer import AnimationView
                    frames = result['sprites']

                    def picture(frame, view=view, frames=frames):
                        """A frame as the Sprites tab draws it, with its offset."""
                        if not 0 <= frame < len(frames) or not frames[frame]:
                            return None
                        view.frame_image(frame)
                        image = view.cache.get(frame)
                        if image is None or image.width <= 1:
                            return None
                        return image, min(p[13] for p in frames[frame]), min(p[14] for p in frames[frame])
                    animations = AnimationView(result['animation_code'], len(frames), picture,
                                               result.get('animation_users'), result.get('update_rate', 60),
                                               node.label.split('|')[0].strip())
                    animations.set_labels(self.labels, self.persist_labels, labels.content_key(result['data']))
                    animations.set_check_target(review_target(self.project, node, self.current_data,
                                                             result.get('preview_context'), len(frames), 'anim'),
                                                self.sprite_checks)
                    animations.check_bar.review_changed.connect(self.refresh_review_status)
                    self.tabs.addTab(animations, 'Animations')
                    view.set_animations(animations)
            if isinstance(node, Asset) and node.kind == 'APD':
                from formats.collision.structured_viewer import StructuredView
                placements = StructuredView(self.current_data, node.kind)
                self.tabs.addTab(placements, 'Placements')
                if 'placement_scene' in result:
                    scene = result['placement_scene']
                    self.level_view.set_scene(scene)
                    self.tabs.addTab(self.level_view, 'Placements in level')
                    by_offset = {e.placement.offset: i for i, e in enumerate(scene.entries)
                                 if e.source is node and e.placement is not None}
                    def select_placement(row, *_, view=self.level_view, offsets=by_offset, table=placements):
                        if 0 <= row < len(table.placements):
                            i = offsets.get(table.placements[row].offset)
                            if i is not None:
                                view.objects.setCurrentCell(i, 1)
                    placements.table.currentCellChanged.connect(select_placement)
            if isinstance(node, Asset) and node.kind == 'WHM':
                from formats.collision.whm_viewer import WhmView
                from formats.collision.structured_viewer import StructuredView
                self.tabs.addTab(WhmView(self.current_data), 'Collision planes')
                self.tabs.addTab(StructuredView(self.current_data, 'WHM'), 'WHM words')
            if isinstance(node, Asset) and node.kind == 'CLM':
                from formats.archive.data_viewer import CollisionMapView
                self.tabs.addTab(CollisionMapView(self.current_data, node.code), 'Collision map')
            if 'wpp' in result:
                from formats.sprites.wpp_viewer import WppView
                from formats.sprites.wpp import renderer as picture_renderer
                kind, pictures = result['wpp']
                from formats.sprites.wpp import bank_palettes
                pictures_view = WppView(kind, pictures, bank_palettes(
                    result['vram'], result.get('paired_sprites'), result.get('paired_tomba', True))
                    if kind == 'frames' else (), result['vram'])
                self.tabs.addTab(pictures_view, 'Pictures')
                pictures_view.set_labels(self.labels, self.persist_labels)
                if 'paired_sprites' in result:
                    view = SpriteView(result['paired_sprites'], result['vram'], renderer=picture_renderer(
                        result['paired_sprites'], pictures, result['vram'], result['paired_tomba']))
                    pictures_view.table.currentCellChanged.connect(
                        lambda row, col, old_row, old_col, sprite=view:
                            sprite.bank.setCurrentCell(row, 0) if 0 <= row < sprite.bank.rowCount() else None)
                    view.set_labels(self.labels, self.persist_labels)
                    paired = result['paired_asset']
                    from game.sprite_checks import review_target
                    paired_data = self.project.asset_data(paired)
                    view.set_check_target(review_target(self.project, paired, paired_data,
                                                       result.get('preview_context'), len(result['paired_sprites'])),
                                          self.sprite_checks)
                    view.check_bar.review_changed.connect(self.refresh_review_status)
                    self.tabs.addTab(view, 'Assembled frames')
                    if 'animation_code' in result:
                        from formats.sprites.anim_viewer import AnimationView
                        frames = result['paired_sprites']
                        def wpp_picture(frame, view=view, frames=frames):
                            if not 0 <= frame < len(frames) or not frames[frame]:
                                return None
                            view.frame_image(frame)
                            return view.cache[frame], min(p[13] for p in frames[frame]), min(p[14] for p in frames[frame])
                        animations = AnimationView(result['animation_code'], len(frames), wpp_picture,
                                                   result.get('animation_users'), result.get('update_rate', 60), self.export_stem(node))
                        animations.set_labels(self.labels, self.persist_labels, result['paired_key'])
                        animations.set_check_target(review_target(self.project, paired, paired_data,
                                                                 result.get('preview_context'), len(frames), 'anim'),
                                                    self.sprite_checks)
                        animations.check_bar.review_changed.connect(self.refresh_review_status)
                        self.tabs.addTab(animations, 'Animations')
                        view.set_animations(animations)
                    pictures_view.clut_selected.connect(
                        lambda word, sprite=view: sprite.override_palette(word, scope=2))
                    view.vram_view.clut_picked.connect(
                        lambda word, pictures=pictures_view, sprite=view:
                            pictures.override_palette(word, announce=False)
                            if sprite.palette_scope.currentIndex() == 2 else None)
            from gui.widgets.hex_view import HexView
            code = isinstance(node, Asset) and node.kind == 'INS' or (
                isinstance(node, DiscEntry) and bool(result.get('regions')))
            if code and self.current_data is not None:
                # Code overlays have no viewer of their own; the annotated
                # bytes are the view.
                from formats.annotate import OVERLAY_BASE
                base = result.get('overlay_base') or OVERLAY_BASE
                from formats.script.ins_viewer import InsView
                self.tabs.addTab(InsView(self.current_data, base), 'Code')
                self.tabs.addTab(HexView(self.current_data, result.get('regions', ()),
                                         note=f'addresses assume the overlay base 0x{base:08X}'), 'Structure')
            if isinstance(node, Asset) and node.kind in ('WPP', 'FOUR', 'SPC', 'SAP', 'Unknown'):
                from formats.archive.data_viewer import DataView
                data_view = DataView(self.current_data, node.kind, node.code, node.ram)
                self.tabs.addTab(data_view, f'{node.kind} records')
            if (self.current_data is not None and isinstance(node, DiscEntry)
                    and Path(node.path).name.upper().startswith('CLUT')):
                from formats.images.clut_viewer import ClutView
                self.tabs.addTab(ClutView(self.current_data), 'CLUT colours')
            if 'script' in result:
                self.tabs.addTab(text_view(result['script']), 'Script')
            for offset, wfm in result.get("wfms", []):
                suffix = f" @{offset:X}" if offset else ""
                source = node.source.path if isinstance(node, Asset) and node.source else getattr(node, 'path', '')
                dialogue = DialogueView(wfm, self.export_stem(node) + suffix, source,
                                        (node.offset if isinstance(node, Asset) else 0) + offset)
                glyphs = GlyphView(wfm)
                # A character typed for a glyph is kept, and shows in the entries at once.
                glyphs.changed.connect(dialogue.relist)
                glyphs.changed.connect(self.persist_glyphs)
                self.tabs.addTab(dialogue, "Dialogue" + suffix)
                self.tabs.addTab(glyphs, "Glyphs" + suffix)
            if "vram" in result and 'sprites' not in result:
                # Sprites carry the section's VRAM in their own tab.
                cluts = {p['clut'] for m in result.get('meshes', []) for p in m.polygons if p['page'] >= 0}
                cluts |= {part[2] & 0x7FFF for frame in result.get('sprites', []) for part in frame}
                self.tabs.addTab(VramView(result["vram"], cluts, self.path_label.text()), "VRAM")
            if isinstance(node, DiscEntry) and not node.directory:
                assets = self.project.by_source.get(node.path, [])
                if assets:
                    self.asset_table(assets)
            self.tabs.addTab(text_view(self.metadata(node, result)), "Information")
            if self.current_data is not None and not code:
                self.tabs.addTab(HexView(self.current_data, result.get('regions', ())), "Decoded file hex")
            if "raw" in result:
                shown = len(result["raw"])
                self.tabs.addTab(HexView(result["raw"], note='' if shown >= node.size else
                                         f'first {shown:,} of {node.size:,} bytes on disc'), "Disc hex")
            # Exports are offered under the name of what is open.
            stem = self.export_stem(node)
            from gui import console
            where = (f'{node.ldar} group {node.group}' if isinstance(node, Asset) else
                     node.path if isinstance(node, DiscEntry) else f'{node[1]} group {node[2]}')
            console.context = ' | '.join(dict.fromkeys(
                ((node.label,) if isinstance(node, Asset) else ()) + (where, stem)))
            for i in range(self.tabs.count()):
                widget = self.tabs.widget(i)
                for viewer in [widget] + widget.findChildren(ImageView):
                    if hasattr(viewer, 'export_name'):
                        viewer.export_name = stem
            for label in self.tabs.findChildren(QLabel):
                if not label.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents):
                    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            wanted, self.restore_tab = self.restore_tab, None
            for i in range(self.tabs.count()):
                if wanted and self.tabs.tabText(i) == wanted:
                    self.tabs.setCurrentIndex(i)
            self.statusBar().showMessage("Ready | " + self.path_label.text())
        except Exception as exc:
            self.tabs.addTab(text_view(f"Viewer error: {exc}\n\n{traceback.format_exc()}"), "Diagnostic")
            self.statusBar().showMessage("Viewer error; raw data remains available")

    def export_stem(self, node):
        """Area, section and resource of a node, as the start of a file name."""
        if isinstance(node, DiscEntry):
            return Path(node.path).stem
        path, index = (node.ldar, node.group) if isinstance(node, Asset) else node[1:]
        area = area_number(path)
        place = f'AREA{area:02d}' if area >= 0 else 'SYSTEM'
        place += ' base' if not index else f' section {index - 1:02d} {section_name(area, index - 1)}'
        if isinstance(node, Asset):
            name = self.labels.label_for(self.label_hashes.get(self.node_key(node), ''))
            place += f' - {name or f"{node.kind} {node.code:04X}"}'
        return place

    def metadata(self, node, result):
        if isinstance(node, Asset):
            text = f"Type: {node.kind} (0x{node.code:04X})\nSource: {node.source.path if node.source else 'Unresolved'}\nFile ID: 0x{node.file_id:04X}\nLDAR: {node.ldar}\nLoad group: {node.group} (0 = base)\nLDAR record: 0x{node.record_offset:X}\nPayload offset: 0x{node.offset:X}\nPayload length: {node.size:,}\nRAM address: 0x{node.ram:08X}\nContinuation: {node.continuation}\n"
            if node.rect:
                text += f"VRAM rectangle (word units): {node.rect}\n"
        elif isinstance(node, DiscEntry):
            text = f"Path: {node.path}\nLBA: {node.lba}\nDisc bytes: {node.size:,}\n"
            if result.get("data") is not None:
                text += f"Decoded bytes: {len(result['data']):,}\n"
            if result.get("raw", b"").startswith(b"GAM\0"):
                text += "Compression: GAM LZ\nExpand this file or use Resources to select LDAR-defined ranges.\n"
            text += executable_header(result.get("raw", b""))
        else:
            text = f"LDAR: {node[1]}\nGroup: {node[2]}\nBase VRAM is loaded first, then this group's uploads overwrite it.\n"
        if result["notes"]:
            text += "\nDiagnostics\n" + "\n".join(result["notes"])
        return text

    def add_table(self, rows, headers, title, callback=None):
        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(False)
        table.setStyleSheet("QTableWidget::item:selected {background-color: #555555; color: white;} QTableWidget::item:selected:!active {background-color: #494949; color: white;}")
        table.verticalHeader().hide()
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(value))
        from gui.widgets.columns import adjustable
        adjustable(table, fit=True)
        if callback:
            table.cellDoubleClicked.connect(lambda row, col: callback(row))
        self.tabs.addTab(table, title)

    def asset_table(self, assets):
        self.add_table([(a.source.path if a.source else "Unresolved", self.node_label(a), f"{a.kind} {a.code:04X}",
                         f"{a.offset:06X}", f"{a.size:,}", "base" if not a.group else f"{a.group - 1:02d}",
                         str(a.rect) if a.rect else f"{a.ram:08X}") for a in assets],
                       ["Source file (double-click to open)", "Label", "Type", "Offset", "Bytes", "Section", "VRAM / RAM"],
                       "Resources", lambda row: self.jump_asset(assets[row]))

    def node_label(self, node):
        key = self.node_key(node)
        return (self.labels.label_for(self.label_hashes.get(key, ''))
                or self.labels.bins.get(repr(key).upper(), ''))

    def jump_file(self, path):
        self.search.clear()
        item = self.file_items[path]
        self.disc_tree.setCurrentItem(item)
        self.disc_tree.scrollToItem(item)

    def jump_group(self, path, index):
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        self.search.clear()
        iterator = QTreeWidgetItemIterator(self.area_tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, ROLE) == ('group', path, index):
                parent = item.parent()
                while parent is not None:
                    parent.setExpanded(True)
                    parent = parent.parent()
                self.area_tree.setCurrentItem(item)
                self.area_tree.scrollToItem(item)
                return
            iterator += 1

    def jump_asset(self, asset):
        self.search.clear()
        item = self.asset_items[(asset.ldar, asset.record_offset)]
        self.area_tree.setCurrentItem(item)
        self.area_tree.scrollToItem(item)

    def filter_tree(self, text):
        needle = text.casefold().strip()
        def visit(item, parent_match=False):
            own = parent_match or not needle or needle in (' '.join((item.text(0), item.text(1), item.toolTip(0)))).casefold()
            child_match = False
            for i in range(item.childCount()):
                child_match = visit(item.child(i), own) or child_match
            item.setHidden(not (own or child_match))
            if needle and child_match:
                item.setExpanded(True)
            return own or child_match
        for i in range(self.disc_tree.topLevelItemCount()):
            visit(self.disc_tree.topLevelItem(i))

    def source_entry(self):
        node = self.current_node
        if isinstance(node, Asset):
            return self.project.disc.entries.get(node.source.path) if node.source else None
        if isinstance(node, DiscEntry) and not node.directory:
            return node
        return None

    def destination(self, name):
        path, _ = QFileDialog.getSaveFileName(self, "Export", name, "All files (*)")
        if path and Path(path).resolve() in (self.project.disc.source.resolve(), self.project.disc.path.resolve()):
            QMessageBox.warning(self, "Choose another destination", "Export cannot overwrite the open disc or CUE.")
            return None
        return path

    def export_payload(self):
        if self.current_data is None:
            return
        node = self.current_node
        name = f"{Path(node.source.path).name}.{node.offset:06X}.{node.code:04X}.{node.kind}" if isinstance(node, Asset) else Path(node.path).name + ".decoded"
        path = self.destination(name)
        if path:
            try:
                Path(path).write_bytes(self.current_data)
                self.statusBar().showMessage(f"Exported {path}")
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def export_raw(self):
        entry = self.source_entry()
        if entry is None:
            return
        path = self.destination(Path(entry.path).name)
        if path:
            try:
                with open(path, "wb") as output:
                    for offset in range(0, entry.size, 1024 * 1024):
                        output.write(self.project.disc.read(entry, 1024 * 1024, offset))
                self.statusBar().showMessage(f"Exported {path}")
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Export failed", str(exc))

    def context_menu(self, tree, point):
        item = tree.itemAt(point)
        if not item:
            return
        tree.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction(self.export_action)
        menu.addAction(self.raw_action)
        rename = menu.addAction('Rename...')
        rename.triggered.connect(self.rename_selected)
        copy = menu.addAction("Copy name")
        copy.triggered.connect(lambda: QApplication.clipboard().setText(item.text(0)))
        menu.exec(tree.viewport().mapToGlobal(point))

    def node_key(self, node):
        if isinstance(node, Asset):
            return ('asset', node.ldar, node.record_offset)
        if isinstance(node, DiscEntry):
            return ('file', node.path)
        return node

    def remember_label_hash(self, node, digest):
        """All LDAR links to one byte range are identical without another read."""
        self.label_hashes[self.node_key(node)] = digest
        if isinstance(node, Asset) and node.source is not None:
            identity = (node.source.lba, node.source.size, node.offset, node.size)
            for groups in self.project.ldars.values():
                for group in groups:
                    for other in group.assets:
                        if other.source is not None and (other.source.lba, other.source.size, other.offset, other.size) == identity:
                            self.label_hashes[self.node_key(other)] = digest
        elif isinstance(node, DiscEntry):
            for other in self.project.disc.files:
                if (other.lba, other.size) == (node.lba, node.size):
                    self.label_hashes[self.node_key(other)] = digest
        self.project.__dict__.setdefault('label_content_hashes', {}).update(self.label_hashes)

    def persist_labels(self):
        if self.project is None:
            return False
        try:
            self.saved_label_snapshot = self.label_autosave.save(self.labels, self.saved_label_snapshot)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Cannot autosave labels',
                                f'{self.label_autosave.path}\n\n{exc}\nKeep this window open and export your labels.')
            return False
        print(f'Labels autosaved: {self.label_autosave.path}', flush=True)
        self.refresh_labels()
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if hasattr(widget, 'reload_labels'):
                widget.reload_labels()
        if not self.project.__dict__.get('label_index_complete') and not self.label_index_running:
            self.index_labels()
        return True

    def builtin_path(self, serial):
        return str(Path(labels.labels_dir()) / (serial + '.json'))

    def save_builtin_labels(self):
        """Write every name into the labels folder, as the set that is
        packaged with the tool for this build of the game."""
        if self.project is None:
            return
        from game.label_store import content_identity
        path = self.builtin_path('shared')
        try:
            Path(path).parent.mkdir(exist_ok=True)
            shared = labels.LabelSet(name='Shared content labels', build='shared',
                                    entries={k: v for k, v in self.labels.entries.items() if content_identity(k)})
            labels.save(shared, path, keep_existing=False)
            local = labels.LabelSet(name=self.labels.name, serial=self.labels.serial, build=self.labels.build,
                                    bins=self.labels.bins, areas=self.labels.areas,
                                    entries={k: v for k, v in self.labels.entries.items() if not content_identity(k)})
            filename = self.labels.build.replace(':', '-') if self.labels.serial in ('TOMBA.EXE', 'MAIN0.EXE') else self.labels.serial
            labels.save(local, self.builtin_path(filename), keep_existing=False)
        except OSError as exc:
            QMessageBox.warning(self, 'Cannot save labels', str(exc))
            return
        self.builtin_labels = {key: entry.name for key, entry in self.labels.entries.items()}
        self.persist_labels()
        self.statusBar().showMessage(f'{self.labels.named} names written to {path}')

    def rename_selected(self):
        target = self.rename_target
        if target is not None:
            if target is False:
                self.statusBar().showMessage('This view has no nameable entry.')
                return
            try:
                if target.isVisible() and hasattr(target, 'rename_selection'):
                    target.rename_selection()
                    return
            except RuntimeError:
                self.rename_target = None
            self.statusBar().showMessage('Select an entry in the visible viewer, or click a disc tree item to name that file.')
            return
        node = self.current_node
        if node is None or self.project is None:
            return
        key = self.node_key(node)
        content = self.label_hashes.get(key)
        if isinstance(node, (tuple, DiscEntry)) and (isinstance(node, tuple) or node.directory):
            identity = repr(key).upper()
            old = self.labels.bins.get(identity, '')
        elif self.current_data is not None:
            content = labels.content_key(self.current_data)
            self.remember_label_hash(node, content)
            old = self.labels.label_for(content)
        else:
            self.statusBar().showMessage('Wait for the file to finish loading before naming it.')
            return
        name, ok = QInputDialog.getText(self, 'Name selection', 'Label (empty restores the original name):', text=old)
        if not ok:
            return
        if content:
            self.labels.rename(content, name.strip(), kind=node.kind if isinstance(node, Asset) else Path(node.path).suffix[1:],
                               start=node.offset if isinstance(node, Asset) else 0,
                               end=max(0, len(self.current_data) - 1))
        else:
            self.labels.bins[identity] = name.strip()
        self.persist_labels()
        self.refresh_labels()

    def refresh_labels(self):
        def visit(item):
            node = item.data(0, ROLE)
            original = item.data(0, ROLE + 1)
            if original:
                key = self.node_key(node)
                name = self.labels.label_for(self.label_hashes.get(key, ''))
                if not name:
                    name = self.labels.bins.get(repr(key).upper(), '')
                text = original
                folder = isinstance(node, tuple) or isinstance(node, DiscEntry) and node.directory
                if item.childCount() or folder:
                    text += f' ({item.childCount()})'
                item.setText(0, text)
                item.setText(1, name or '')
            for i in range(item.childCount()):
                visit(item.child(i))
        for i in range(self.disc_tree.topLevelItemCount()):
            visit(self.disc_tree.topLevelItem(i))

    def refresh_review_status(self):
        if self.project is None:
            return
        from game.label_store import local_identity
        from game.sprite_checks import review_badge, review_statuses
        try:
            entries = self.sprite_checks.document()['entries']
        except (OSError, ValueError, TypeError) as exc:
            self.statusBar().showMessage(f'Cannot read sprite checks: {exc}')
            return
        by_asset = {}
        build = local_identity(self.project)
        for entry in entries:
            if entry.get('build') == build:
                key = (entry.get('ldar'), entry.get('group'), entry.get('record_offset'))
                by_asset.setdefault(key, []).append(entry)
        for key, items in self.review_items.items():
            for item in items:
                asset = item.data(0, ROLE)
                digest = self.label_hashes.get(self.node_key(asset))
                matches = [e for e in by_asset.get(key, []) if not digest or e.get('spr_sha256', '').startswith(digest)]
                for column, kind in ((3, 'spr'), (4, 'anim')):
                    reviews = [e for e in matches if e.get('review_kind', 'spr') == kind]
                    item.setText(column, review_badge(reviews))
                    item.setTextAlignment(column, Qt.AlignmentFlag.AlignCenter)
                    names = dict(review_statuses(kind), looks_off='Looks off')
                    item.setToolTip(column, '\n'.join(f"{names.get(e.get('status'), 'Other')}"
                                                     + (f" | {e['entry_kind']} {e.get('entry_id')}" if e.get('entry_kind') else '')
                                                     + f" | VRAM context {e.get('vram_context')}"
                                                     for e in reviews))

    def load_glyphs(self):
        """Characters typed for glyphs on this machine, kept between sessions."""
        import json
        from formats.text import wfm
        try:
            saved = json.loads(self.settings.value('glyphs/characters', '') or '{}')
        except ValueError:
            saved = {}
        wfm.USER_GLYPHS.update({key: value for key, value in saved.items()
                                if isinstance(key, str) and isinstance(value, str)})

    def persist_glyphs(self):
        import json
        from formats.text import wfm
        self.settings.setValue('glyphs/characters', json.dumps(wfm.USER_GLYPHS, ensure_ascii=False))

    def reread_glyphs(self):
        """Show a changed set of glyph characters in the text tabs that are open."""
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, GlyphView):
                widget.wfm.recognise()
                widget.refill()
            elif isinstance(widget, DialogueView):
                widget.wfm.recognise()
                widget.relist()

    def import_glyphs(self):
        import json
        from formats.text import wfm
        path, _ = QFileDialog.getOpenFileName(self, 'Import glyph characters', '', 'Glyph characters (*.json)')
        if not path:
            return
        try:
            loaded = json.loads(Path(path).read_text('utf-8'))
            if not isinstance(loaded, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in loaded.items()):
                raise ValueError('the file is not a table of glyph keys and characters')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot import glyph characters', str(exc))
            return
        wfm.USER_GLYPHS.update(loaded)
        self.persist_glyphs()
        self.reread_glyphs()
        self.statusBar().showMessage(f'{len(loaded)} glyph characters imported.')

    def export_glyphs(self):
        import json
        from formats.text import wfm
        path, _ = QFileDialog.getSaveFileName(self, 'Export glyph characters', 'glyph characters.json',
                                              'Glyph characters (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(wfm.USER_GLYPHS, ensure_ascii=False, indent=1, sort_keys=True) + '\n',
                                      'utf-8')
            except OSError as exc:
                QMessageBox.warning(self, 'Cannot export glyph characters', str(exc))

    def save_builtin_glyphs(self):
        """Add the characters typed here to the dictionary packaged with the tool."""
        import json
        from formats.text import wfm
        path = Path(wfm.__file__).with_name('glyph_dictionary.json')
        try:
            merged = json.loads(path.read_text('utf-8'))
            merged.update({key: value for key, value in wfm.USER_GLYPHS.items() if value})
            path.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + '\n', 'utf-8')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot save glyph characters', str(exc))
            return
        wfm.GLYPH_DICTIONARY.update(merged)
        self.statusBar().showMessage(f'{len(merged)} glyph characters in {path}')

    def export_text(self):
        """Ask what text to export and how, and write it."""
        if self.project is None:
            return
        from gui.text_export import TextExportDialog
        from formats.text import export
        node = self.current_node
        table = node.ldar if isinstance(node, Asset) else node[1] if isinstance(node, tuple) else None
        tongue, area = table_name(table) if table else (None, -1)
        dialog = TextExportDialog(self, self.project, area if area >= 0 else None, tongue,
                                  self.project.disc.source.stem + ' text')
        if not dialog.exec():
            return
        chosen = dialog.options()
        project, title = self.project, self.project.disc.source.stem
        self.statusBar().showMessage('Reading text banks...')

        def work():
            banks = export.collect(project, chosen['area'], chosen['language'])
            written = export.write(banks, chosen['target'], chosen['kind'], chosen['layout'], title,
                                   chosen['controls'], chosen['unknown'], chosen['raw'])
            return (len(banks), sum(len(bank.wfm.dialogues) for bank in banks),
                    sum(bank.unknown for bank in banks), written)

        def done(generation, result, error):
            if error or result is None:
                QMessageBox.warning(self, 'Text not exported', error or 'Nothing was written.')
                return
            banks, entries, unknown, written = result
            self.statusBar().showMessage(
                f'{entries:,} entries of {banks} text banks written to {len(written)} file'
                + ('s' if len(written) != 1 else '') + (f'; {unknown} glyphs have no character yet' if unknown else ''))
        self.submit(work, done)

    def import_labels(self):
        if self.project is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Import labels', '', 'Labels (*.json)')
        if not path:
            return
        try:
            incoming = labels.load(path)
            from game.label_store import content_identity
            positional = (incoming.build == self.labels.build or (incoming.serial == self.labels.serial
                          and self.labels.serial not in ('TOMBA.EXE', 'MAIN0.EXE') and incoming.build == self.labels.serial))
            self.labels.entries.update({k: v for k, v in incoming.entries.items() if content_identity(k) or positional})
            # Named folders/sections are positional and restricted to their build.
            if positional:
                self.labels.bins.update(incoming.bins)
                self.labels.areas.update(incoming.areas)
            self.persist_labels()
            self.index_labels()
            # Lists of sprites and models that are open show the new names.
            for index in range(self.tabs.count()):
                if hasattr(self.tabs.widget(index), 'reload_labels'):
                    self.tabs.widget(index).reload_labels()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Cannot import labels', str(exc))

    def index_labels(self):
        # Hash all small logical files/resources off the UI thread. Exact content
        # matches can safely carry names between regional releases.
        project = self.project
        if self.label_index_running:
            return
        if project.__dict__.get('label_index_complete'):
            self.label_hashes.update(project.__dict__.get('label_content_hashes', {}))
            self.refresh_labels()
            return
        from copy import copy
        from collections import OrderedDict
        reader = copy(project)
        reader.cache, reader.cache_bytes = OrderedDict(), 0
        epoch = self.label_index_epoch
        known = dict(self.label_hashes)
        self.label_index_running = True
        def collect():
            out, seen = known, {}
            nodes = [a for groups in project.ldars.values() for group in groups for a in group.assets if a.source]
            nodes += [e for e in project.disc.files if e.size <= 4 * 1024 * 1024]
            nodes.sort(key=lambda n: n.source.lba if isinstance(n, Asset) else n.lba)
            for number, node in enumerate(nodes):
                if epoch != self.label_index_epoch or project is not self.project:
                    return None
                key = self.node_key(node)
                if key not in out:
                    source = node.source if isinstance(node, Asset) else node
                    identity = ((source.lba, source.size, node.offset, node.size) if isinstance(node, Asset)
                                else (source.lba, source.size, 'file'))
                    try:
                        if identity not in seen:
                            data = reader.asset_data(node) if isinstance(node, Asset) else reader.payload(node)
                            seen[identity] = labels.content_key(data)
                        out[key] = seen[identity]
                    except ValueError:
                        continue
                if number % 64 == 0:
                    self.labels_indexed.emit(epoch, project, dict(out))
            return out
        def ready(generation, result, error):
            if epoch == self.label_index_epoch and project is self.project:
                self.label_index_running = False
                if result is not None:
                    project.label_index_complete = True
                    self.apply_label_index(epoch, project, result)
                elif error:
                    print(f'Label content scan: {error}', flush=True)
        # Selection changes cancel preview jobs, but must not discard this scan.
        self.label_pool.start(Job(epoch, collect, ready))

    def apply_label_index(self, epoch, project, result):
        if epoch != self.label_index_epoch or project is not self.project:
            return
        self.label_hashes.update(result)
        project.__dict__.setdefault('label_content_hashes', {}).update(result)
        self.refresh_labels()
        self.refresh_review_status()

    def export_labels(self):
        if self.project is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Export labels', (self.labels.serial or 'tomba') + '.labels.json', 'Labels (*.json)')
        if path:
            try:
                labels.save(self.labels, path, keep_existing=False)
            except OSError as exc:
                QMessageBox.warning(self, 'Cannot export labels', str(exc))

    def about(self):
        QMessageBox.about(self, f"TombaEdit {version}", "Tomba! disc and asset browser\n\nBIN/CUE/ISO/IMG | LDAR | GAM | WMD | FOUR | SPR | WPP | WHM | APD | WFM | SEQ | WVD | STR\nTIM | TMD | VAB | MIDI | XA | archives of other games\n\nFormat research: vervalkon, zerovii, Woolmagician, hansbonini/psx_tomba, afsenovilla/Tombi-Decomp.\nSee README.md and docs/formats.md for format details and known gaps.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in DISC_SUFFIXES for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in DISC_SUFFIXES:
                self.open_path(url.toLocalFile())
                break

    def closeEvent(self, event):
        if self.project is not None and not self.persist_labels():
            event.ignore()
            return
        self.generation += 1
        self.label_index_epoch += 1
        self.label_pool.clear()
        self.pool.clear()
        self.settings.setValue("geometry", self.saveGeometry())
        self.clear_tabs()
        super().closeEvent(event)
