"""Sprite bank browser using the bank-first table layout.

The section's VRAM runs along the bottom. Its crosshair is the palette
control of the sprites above it: putting it on a palette row redraws the
selected pieces, the sprite or the whole bank through that palette, and
selecting a sprite or a piece moves it to the palette they use and outlines
where in VRAM their pixels come from.
"""
from gui.console import announce
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, pyqtSignal, QItemSelectionModel, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox, QComboBox, QMenu, QInputDialog)
from gui.widgets.image_view import ImageView, file_stem
from gui.widgets.sheet_layout import SpacingControls
from gui.widgets.columns import adjustable, elide_at_view_edge
from game.labels import sprite_frame_key
from formats.images.vram_viewer import VramView
from disc.reader import FormatError
from psx.graphics import render_sprite, part_page, guess_page, palette_missing, palette_runtime, same_texels


PART_COLOURS = ((255, 80, 80, 255), (80, 220, 255, 255), (255, 220, 60, 255), (120, 255, 120, 255),
                (255, 120, 255, 255), (255, 160, 60, 255))


FRAME_COLOUR = (30, 30, 30, 128)       # half transparent
ORIGIN_COLOUR = (0, 0, 0, 0)    # gaps in a sprite's box in line with its origin

LABEL = 6   # the bank list's column of labels
ORIGIN = 7  # and the one saying how a sprite's texture page is known
LOOKS_OFF = 8


class SpriteView(QWidget):
    selection_changed = pyqtSignal(list)
    # How the panes were last dragged, kept from one bank to the next:
    # splitter name -> sizes.
    pane_sizes = {}

    def __init__(self, frames, vram, pages=None, renderer=None, default=None, cluts=None, *,
                 styles=None, origins=None, frame_vrams=None, unavailable=None):
        """`pages` maps frame numbers to the texture page base of an object
        that shows them; frames nobody places borrow the nearest known one,
        or `default` when the bank is not placed at all. `renderer` draws
        frames whose pixels are not in VRAM."""
        super().__init__()
        self.frames, self.vram, self.renderer = frames, vram, renderer
        self.pages = dict(pages or {})
        self.cluts = dict(cluts or {})  # CLUTs supplied by a custom drawing object
        self.styles = dict(styles or {})
        self.known = sorted(self.pages)
        self.borrowed = {}              # frame nothing places -> the page base it is drawn with
        self.lender = {}                # and the placed frame that page was taken from
        self.origins = dict(origins or {})
        self.frame_vrams = dict(frame_vrams or {})
        self.relayout = QTimer(self)
        self.relayout.setSingleShot(True)
        self.relayout.setInterval(120)
        self.relayout.timeout.connect(self.fit_sheet)
        self.names = {}                 # frame -> what it is a picture of
        self.label_set = None           # the names people give frames
        self.save_labels = None
        self.guess = default
        self.unavailable = set(unavailable or ())
        self.export_name = 'sprites'    # prefix of default file names, set by the window
        self.cache = {}
        self.texture_cache = {}
        self.clut_overrides = {}  # (sprite, part) -> palette address; preview only
        self.animation_player = None    # the Animations tab drawing these frames
        self.frame_index = 0
        self.entry_flags = None
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.whole = QPushButton('Whole bank')
        self.whole.setCheckable(True)
        self.whole.setChecked(True)
        self.whole.toggled.connect(self.refresh)
        self.whole.toggled.connect(lambda on: self.show_in_vram())
        bar.addWidget(self.whole)
        for label, callback in [('Zoom Out', lambda: self.zoom_by(-1)),
                                ('Zoom In', lambda: self.zoom_by(1)),
                                ('1:1', lambda: self.image.zoom.setCurrentIndex(1))]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
        self.origin = QCheckBox('Origin')
        self.origin.setChecked(True)
        self.origin.toggled.connect(self.refresh)
        bar.addWidget(self.origin)
        self.frame_bounds = QCheckBox('Bounds')
        self.frame_bounds.setToolTip('Draw a box round every sprite, one pixel outside it, on its own and on a sheet, with gaps '
                                     'in it in line with the sprite\'s origin. '
                                     'Saved pictures include the boxes while this is ticked.')
        self.frame_bounds.toggled.connect(self.refresh)
        bar.addWidget(self.frame_bounds)
        self.bounds = QCheckBox('Part bounds')
        self.bounds.setToolTip('Outline every part a sprite is assembled from, one colour per part. '
                               'Saved pictures include the outlines while this is ticked.')
        self.bounds.toggled.connect(self.refresh)
        bar.addWidget(self.bounds)
        self.grey = QCheckBox('Grey without palette')
        self.grey.setChecked(True)
        self.grey.setToolTip('Draw parts whose palette row is empty in this VRAM in shades of grey, '
                             'so art the game colours while it runs can still be seen.')
        self.grey.toggled.connect(self.rebuild)
        self.grey.setVisible(renderer is None)
        bar.addWidget(self.grey)
        self.page_base = QSpinBox()
        self.page_base.setRange(-1, 31)
        self.page_base.setSpecialValueText('Auto')
        self.page_base.setValue(-1)
        self.page_base.setToolTip('Parts store a page relative to a base the drawing object supplies. '
                                  'Auto uses the base of the placed object that shows the frame.')
        self.page_base.valueChanged.connect(self.rebuild)
        self.page_label = QLabel('Texture page base:')
        self.page_label.setVisible(renderer is None)
        self.page_base.setVisible(renderer is None)
        bar.addWidget(self.page_label)
        bar.addWidget(self.page_base)
        self.spacing = SpacingControls(margin=1)
        self.spacing.changed.connect(self.refresh)
        bar.addWidget(self.spacing)
        bar.addStretch()
        layout.addLayout(bar)
        export_bar = QHBoxLayout()
        for label, callback in [('Save sprite...', self.save_current),
                                ('Save whole bank...', self.save_bank),
                                ('Save selected PNGs...', self.save_selected),
                                ('Save all PNGs...', self.save_all)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            export_bar.addWidget(button)
        export_bar.addStretch()
        layout.addLayout(export_bar)
        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)
        left = QWidget()
        left.setMinimumWidth(420)
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel('Sprites'))
        self.bank = QTableWidget(len(frames), 9)
        self.bank.setHorizontalHeaderLabels(['Sprite', '#', 'Parts', 'W', 'H', 'Pages', 'Label', 'Page from', 'Looks off'])
        self.bank.horizontalHeaderItem(ORIGIN).setToolTip(
            'How the texture page a sprite is drawn from is known: from an object placed in this section, '
            'from one placed in another section (the sprite is then drawn with that section\'s textures), '
            'from an animation an object\'s code goes on to play, from the item table, from running the '
            'routine of an object nothing places, from an object or routine of another area that loads '
            'the same bank (drawn with that area\'s textures where this section\'s differ), or borrowed from '
            'the nearest sprite that is known. A borrowed page is a guess.')
        # The label is listed beside the sprite it names.
        self.bank.horizontalHeader().moveSection(LABEL, 1)
        self.bank.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bank.customContextMenuRequested.connect(self.bank_menu)
        self.bank.verticalHeader().hide()
        self.bank.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bank.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.bank.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.bank.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.bank.setDragEnabled(False)
        # Every column is wide enough for its text and can be dragged; the
        # list scrolls sideways when the pane is narrower.
        for column, width in enumerate((190, 48, 58, 48, 48, 96, 150, 120)):
            self.bank.setColumnWidth(column, width)
        self.bank.horizontalHeader().setMinimumSectionSize(44)
        adjustable(self.bank, min_widths={LABEL: 180})
        self.bank.horizontalHeader().moveSection(self.bank.horizontalHeader().visualIndex(LOOKS_OFF), 0)
        self.bank.horizontalHeader().setMinimumSectionSize(44)
        self.bank.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.bank.currentCellChanged.connect(self.row_changed)
        self.bank.cellDoubleClicked.connect(self.frame_sprite)
        self.bank.itemSelectionChanged.connect(self.selected)
        ll.addWidget(self.bank)
        splitter.addWidget(left)
        right = QSplitter(Qt.Orientation.Vertical)
        self.image = ImageView()
        self.image.zoom.currentIndexChanged.connect(self.zoom_mode_changed)
        self.image.zoom.setCurrentIndex(0)
        right.addWidget(self.image)
        pieces = QWidget()
        pl = QVBoxLayout(pieces)
        pl.addWidget(QLabel('Pieces'))
        self.parts = QTableWidget(0, 12)
        elide_at_view_edge(self.parts)
        self.parts.setHorizontalHeaderLabels(['#', 'U', 'V', 'W', 'H', 'Page', 'CLUT', 'Drawn page', 'X', 'Y', 'UV 1', 'UV 2'])
        self.parts.verticalHeader().hide()
        self.parts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.parts.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.parts.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.parts.itemSelectionChanged.connect(self.show_in_vram)
        pl.addWidget(self.parts)
        right.addWidget(pieces)
        pieces.setMinimumHeight(120)
        right.setSizes([330, 150])
        splitter.addWidget(right)
        splitter.setSizes([680, 780])
        # VRAM along the bottom; its crosshair is the sprites' palette control.
        self.vram_view = VramView(vram, {p[2] & 0x7FFF for frame in frames for p in frame}, 'VRAM', embedded=True)
        self.palette_scope = QComboBox()
        self.palette_scope.addItems(['Selected pieces', 'Whole sprite', 'Whole bank'])
        self.palette_scope.setCurrentIndex(2)
        self.palette_scope.setToolTip('What is redrawn through the palette the crosshair is put on. With no '
                                      'piece selected, the whole sprite is.')
        reset_palettes = QPushButton('Reset CLUTs')
        reset_palettes.setToolTip('Draw every piece through its own palette again.')
        reset_palettes.clicked.connect(self.reset_palettes)
        self.vram_view.add_controls(QLabel('Crosshair recolours:'), self.palette_scope, reset_palettes)
        self.vram_view.clut_picked.connect(self.override_palette)
        stack = QSplitter(Qt.Orientation.Vertical)
        stack.setChildrenCollapsible(False)
        stack.addWidget(splitter)
        stack.addWidget(self.vram_view)
        stack.setStretchFactor(0, 3); stack.setStretchFactor(1, 1)
        stack.setSizes([500, 230])
        layout.addWidget(stack, 1)
        for name, part in (('lists', splitter), ('pieces', right), ('vram', stack)):
            if name in self.pane_sizes:
                part.setSizes(self.pane_sizes[name])
            part.splitterMoved.connect(
                lambda position, index, name=name, part=part: self.pane_sizes.__setitem__(name, part.sizes()))
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info)
        self.rebuild()

    def set_check_target(self, target, store=None):
        from formats.sprites.check_view import SpriteCheckBar
        def preview():
            return dict(texture_page_base=self.page_base.value(),
                        grey_without_palette=self.grey.isChecked(),
                        clut_overrides=[dict(sprite=sprite, part=part, clut=f'0x{clut:04X}')
                                        for (sprite, part), clut in sorted(self.clut_overrides.items())])
        self.check_bar = SpriteCheckBar(target, preview, self, store=store)
        self.layout().insertWidget(2, self.check_bar)
        from formats.sprites.entry_flags import EntryFlags
        self.entry_flags = EntryFlags(self.bank, LOOKS_OFF, self.check_bar, 'sprite')
        self.entry_flags.fill(range(len(self.frames)))

    def frame_key(self, index):
        """What a frame's label is kept under (game.labels.sprite_frame_key)."""
        return sprite_frame_key(self.frames[index])

    def label(self, index):
        key = self.frame_key(index)
        return self.label_set.label_for(key) or '' if key and self.label_set is not None else ''

    def set_labels(self, label_set, save):
        """Take the label set frames are named in, and what stores it."""
        self.label_set, self.save_labels = label_set, save
        self.reload_labels()

    def reload_labels(self):
        self.bank.blockSignals(True)
        for index in range(len(self.frames)):
            self.bank.item(index, LABEL).setText(self.label(index))
        self.bank.blockSignals(False)

    def bank_menu(self, point):
        rows = self.selected_indices()
        if not rows or self.label_set is None:
            return
        menu = QMenu(self)
        rename = menu.addAction('Rename...' if len(rows) == 1 else f'Rename {len(rows)} sprites...')
        clear = menu.addAction('Clear label' if len(rows) == 1 else 'Clear labels')
        clear.setEnabled(any(self.label(row) for row in rows))
        chosen = menu.exec(self.bank.viewport().mapToGlobal(point))
        if chosen is rename:
            self.rename_frames(rows)
        elif chosen is clear:
            self.label_frames(rows, '')

    def rename_frames(self, rows):
        """Ask for one name and give it to every selected frame."""
        old = {self.label(row) for row in rows}
        name, accepted = QInputDialog.getText(
            self, 'Name sprite' if len(rows) == 1 else f'Name {len(rows)} sprites',
            'Label (empty removes it):', text=old.pop() if len(old) == 1 else '')
        if accepted:
            self.label_frames(rows, name.strip())

    def rename_selection(self):
        rows = self.selected_indices()
        if rows and self.label_set is not None:
            self.rename_frames(rows)

    def label_frames(self, rows, name):
        for row in rows:
            key = self.frame_key(row)
            if key:
                self.label_set.rename(key, name, kind='SPR frame')
        if self.save_labels:
            self.save_labels()
        self.reload_labels()

    def title(self, index):
        """A frame's row: its number. What it is called is its label."""
        return f'{index:02X}'

    def set_names(self, names):
        """Take the classes of object each frame is drawn by, for the line
        printed when a frame is selected."""
        self.names = dict(names)

    def zoom_by(self, step):
        self.image.zoom.setCurrentIndex(max(0, min(self.image.zoom.count()-1,
                                                   self.image.zoom.currentIndex()+step)))

    def resizeEvent(self, event):
        """A sheet is laid out again for the new shape of its pane."""
        super().resizeEvent(event)
        self.relayout.start()

    def origin_of(self, index):
        """How the page a frame is drawn from is known."""
        if self.renderer:
            return 'picture bank'
        if self.page_base.value() >= 0:
            return 'set by hand'
        if index in self.unavailable:
            return 'not initialized by this screen'
        if index in self.origins:
            return self.origins[index]
        return 'object' if index in self.pages else 'borrowed' if self.known else 'guess'

    def set_origins(self, origins, vrams=None):
        """Say where the pages of frames come from, and give the VRAM of
        another section to the frames only that section shows."""
        self.origins, self.frame_vrams = dict(origins), dict(vrams or {})
        self.rebuild()

    def columns(self, index):
        """The columns of VRAM a frame's palettes are in."""
        return {part[2] & 63 for part in self.frames[index]} if index < len(self.frames) else set()

    def base_for(self, index):
        """Texture page base a frame is drawn with."""
        if self.page_base.value() >= 0:
            return self.page_base.value()
        if index in self.pages:
            return self.pages[index]
        if self.known:
            if index not in self.borrowed:
                # A frame nothing places goes with the nearest known frame
                # whose palette is in the same column of VRAM: the art and the
                # palettes of one thing are loaded side by side. One that an
                # object of the area is placed showing goes first. Failing
                # that, with the last known frame before it, since a
                # character's frames follow one another.
                columns = self.columns(index)
                same = [frame for frame in self.known if columns & self.columns(frame)]
                same = [frame for frame in same if self.origin_of(frame).startswith(('object', 'section'))] or same
                before = [frame for frame in self.known if frame <= index]
                self.lender[index] = (min(same, key=lambda frame: abs(frame - index)) if same
                                      else before[-1] if before else self.known[0])
                self.borrowed[index] = self.pages[self.lender[index]]
            return self.borrowed[index]
        if self.guess is None:
            self.guess = guess_page(self.frames, self.vram)
        return self.guess

    def frame_image(self, index, origin=False):
        if index not in self.cache:
            try:
                overrides = {part: clut for (sprite, part), clut in self.clut_overrides.items() if sprite == index}
                if index in self.unavailable and self.page_base.value() < 0 and not overrides:
                    return Image.new('RGBA', (1, 1))
                base = None if self.renderer else self.base_for(index)
                # A frame that borrows its page is drawn with the same
                # section's textures as the frame it borrows from, and with
                # that frame's palette if its own is one the game sets.
                lender = self.lender.get(index) if index not in self.pages else None
                own = self.cluts.get(index)
                vram = self.frame_vrams.get(index, self.frame_vrams.get(lender, self.vram))
                # A traced object field can resemble a palette address even
                # when that row was never uploaded by this section. Preserve
                # a frame's embedded palette instead of using an empty row.
                # A user-picked override remains explicit and is unaffected.
                if own is not None and palette_missing(vram, own):
                    own = None
                if own is None and lender is not None and self.frames[index] and (
                        all(palette_runtime(part[2]) for part in self.frames[index])
                        or {part[2] for part in self.frames[index]} <= {part[2] for part in self.frames[lender]}):
                    # ...or one the two frames share: an object that brings a
                    # palette of its own draws all its frames through it.
                    own = self.cluts.get(lender)
                if (index not in self.frame_vrams and vram is not self.vram
                        and self.origin_of(lender).startswith('section') and self.frames[index]
                        and same_texels(self.vram, vram, self.frames[index], base, pixels_only=True)
                        and not any(palette_missing(self.vram, part[2]) for part in self.frames[index])):
                    # The pixels are loaded here as well: the frame keeps this
                    # section's palettes.
                    vram = self.vram
                parts = [tuple(clut if col == 2 else value for col, value in enumerate(part))
                         if (clut := overrides.get(n, own)) is not None else part
                         for n, part in enumerate(self.frames[index])]
                self.cache[index] = self.renderer(index, overrides) if self.renderer else render_sprite(
                    parts, vram, tpage=base,
                    grey_missing=self.grey.isChecked(),
                    texture_cache=self.texture_cache)
            except FormatError:
                self.cache[index] = Image.new('RGBA', (1, 1))
        image, border = self.cache[index], 0
        if self.bounds.isChecked() and self.frames[index]:
            image = self.outlined(image, self.frames[index])
        if self.frame_bounds.isChecked() and self.frames[index]:
            # The box goes round the sprite, one pixel outside its own.
            framed = Image.new('RGBA', (image.width + 2, image.height + 2))
            framed.alpha_composite(image, (1, 1))
            image, border = framed, 1
            draw = ImageDraw.Draw(image)
            right, bottom = image.width - 1, image.height - 1
            draw.rectangle((0, 0, right, bottom), outline=FRAME_COLOUR)
            # One pixel of each side is left out where the column or the row
            # of the sprite's origin crosses the box.
            x = 1 - min(part[13] for part in self.frames[index])
            y = 1 - min(part[14] for part in self.frames[index])
            if 0 < x < right:
                draw.point([(x, 0), (x, bottom)], fill=ORIGIN_COLOUR)
            if 0 < y < bottom:
                draw.point([(0, y), (right, y)], fill=ORIGIN_COLOUR)
        if not origin or not self.frames[index]:
            return image
        bounds = [part for frame in self.frames for part in frame]
        left = min([part[13] for part in bounds] + [0])
        top = min([part[14] for part in bounds] + [0])
        right = max([part[13]+part[9] for part in bounds] + [1])
        bottom = max([part[14]+part[10] for part in bounds] + [1])
        out = Image.new('RGBA', (right-left + 2*border, bottom-top + 2*border))
        out.alpha_composite(image, (min(p[13] for p in self.frames[index])-left,
                                    min(p[14] for p in self.frames[index])-top))
        return out

    @staticmethod
    def outlined(image, frame):
        """A copy with each part's rectangle drawn over it, one colour per part."""
        image = image.copy()
        draw = ImageDraw.Draw(image)
        left, top = min(p[13] for p in frame), min(p[14] for p in frame)
        for n, part in enumerate(frame):
            x, y = part[13] - left, part[14] - top
            draw.rectangle((x, y, x + part[9] - 1, y + part[10] - 1), outline=PART_COLOURS[n % len(PART_COLOURS)])
        return image

    def rebuild(self):
        self.cache.clear()
        self.texture_cache.clear()
        self.bank.blockSignals(True)
        for i, frame in enumerate(self.frames):
            if frame:
                x = min(p[13] for p in frame)
                y = min(p[14] for p in frame)
                width = max(p[13]+p[9] for p in frame)-x
                height = max(p[14]+p[10] for p in frame)-y
                pages = ('picture bank' if self.renderer else
                         ', '.join(sorted({f'{part_page(p, self.base_for(i)) & 31:02X}' for p in frame})))
            else:
                width = height = 0
                pages = ''
            values = [self.title(i), f'{i:02X}', str(len(frame)), str(width),
                      str(height), pages, self.label(i), self.origin_of(i) if frame else '']
            for col, value in enumerate(values):
                self.bank.setItem(i, col, QTableWidgetItem(value))
        self.bank.blockSignals(False)
        if self.entry_flags is not None:
            self.entry_flags.fill(range(len(self.frames)))
        self.refresh()

    def row_changed(self, row, column, old_row, old_column):
        if row < 0:
            return
        self.frame_index = row
        self.whole.setChecked(False)
        self.refresh()
        frame = self.frames[row]
        if row in self.unavailable and self.page_base.value() < 0:
            self.info.setText(self.info.text() + ' | This screen does not initialize this frame. Choose another screen or set a page and CLUT manually.')
        palettes = [self.part_clut(row, n) for n in range(len(frame))]
        vram = self.frame_vrams.get(row, self.vram)
        if frame and not self.renderer and any(palette_missing(vram, word) for word in palettes):
            self.info.setText(self.info.text() + (
                ' | palette set by the game while it runs' if any(palette_runtime(word) for word in palettes)
                else ' | palette row empty in this VRAM')
                              + (', shown in grey' if self.grey.isChecked() else ''))
        self.show_in_vram()
        announce(f'sprite {row:02X} | ' + (f'"{self.label(row)}" | ' if self.label(row) else '')
              + f'{", ".join(self.names.get(row, ())) or "not placed"} | {len(frame)} pieces'
              + ('' if self.renderer or not frame else f' | texture page base 0x{self.base_for(row):X}'))

    def set_animations(self, player):
        # Sprite inspection remains static. Playback belongs to AnimationView,
        # which draws the frames as this view does, palette overrides too.
        self.animation_player = player
        player.set_palette_source(self)

    def frame_sprite(self, row, column):
        if row < 0:
            return
        self.frame_index = row
        self.whole.setChecked(False)
        self.image.zoom.setCurrentIndex(0)
        self.refresh()
        self.image.scale_image()

    def part_clut(self, sprite, part):
        """The palette a piece is drawn through at the moment."""
        return self.clut_overrides.get((sprite, part), self.cluts.get(sprite, self.frames[sprite][part][2])) & 0x7FFF

    def show_in_vram(self):
        """Point the VRAM panel at the sprite on screen: the crosshair goes
        to the palette of the first selected piece (the first piece if none
        is), and every piece's source rectangle is outlined, the selected
        ones brightly."""
        if self.whole.isChecked() or not self.frames or len(self.selected_indices()) > 1:
            self.vram_view.canvas.outlines = []
            self.vram_view.canvas.update()
            return
        index = min(self.frame_index, len(self.frames) - 1)
        frame = self.frames[index]
        chosen = sorted({item.row() for item in self.parts.selectedItems() if item.row() < len(frame)})
        outlines = []
        for n, part in enumerate(frame):
            if self.renderer:
                break               # these pixels are in a picture bank, not in VRAM
            page = part_page(part, self.base_for(index))
            # A page is 64 words across. Eight-bit pages hold half as many
            # texels to the word as four-bit ones.
            wide = 2 if (page >> 7) & 3 == 1 else 4
            colour = PART_COLOURS[n % len(PART_COLOURS)] if not chosen or n in chosen else (150, 150, 150, 160)
            outlines.append(((page & 15) * 64 + part[0] / wide, (page >> 4 & 1) * 256 + part[1],
                             part[9] / wide, part[10], colour))
        self.vram_view.canvas.outlines = outlines
        if frame:
            self.vram_view.show_clut(self.part_clut(index, chosen[0] if chosen else 0), flash=False)
            focus = [outlines[n] for n in (chosen or range(len(outlines))) if n < len(outlines)]
            if focus:
                left, top = min(o[0] for o in focus), min(o[1] for o in focus)
                self.vram_view.canvas.show_words(left, top, max(o[0] + o[2] for o in focus) - left,
                                                 max(o[1] + o[3] for o in focus) - top)
        self.vram_view.canvas.update()

    def override_palette(self, value, scope=None):
        """Redraw through the palette the crosshair was put on."""
        scope = self.palette_scope.currentIndex() if scope is None else scope
        selected = {item.row() for item in self.parts.selectedItems()}
        if scope == 0 and not selected:
            scope = 1               # nothing picked out: the sprite as a whole
        if scope < 2 and self.whole.isChecked():
            self.info.setText('Select a sprite to recolour it, or set the crosshair to recolour the whole bank.')
            return
        sprites = range(len(self.frames)) if scope == 2 else [self.frame_index]
        self.recolour([(sprite, part) for sprite in sprites
                       for part in (range(len(self.frames[sprite])) if scope else selected)], value)

    def recolour(self, targets, value):
        """Draw these (sprite, piece) pairs through palette `value`."""
        for sprite, part in targets:
            self.clut_overrides[sprite, part] = value
        self.palettes_changed()

    def reset_palettes(self):
        self.clut_overrides.clear()
        self.palettes_changed()
        self.show_in_vram()

    def palettes_changed(self):
        self.cache.clear()
        self.refresh()
        if self.animation_player is not None:
            self.animation_player.pictures_changed()

    def selected(self):
        indices = self.selected_indices()
        self.selection_changed.emit(indices)
        if not self.whole.isChecked():
            self.refresh()

    def restore_state(self, indices):
        if not indices:
            return
        self.bank.blockSignals(True)
        for index in indices:
            if 0 <= index < self.bank.rowCount():
                model_index = self.bank.model().index(index, 0)
                self.bank.selectionModel().select(model_index,
                    QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.bank.blockSignals(False)
        self.selected()

    def sheet(self, indices):
        if not indices:
            return Image.new('RGBA', (1, 1)), []
        # Packed, each sprite is cut to its own pixels; the room round its
        # origin is only kept where every sprite has an equal cell.
        origin = self.origin.isChecked() and self.spacing.even.isChecked()
        images = [self.frame_image(i, origin) for i in indices]
        places, size = self.spacing.arrange([im.size for im in images], self.image.view)
        out = Image.new('RGBA', size)
        records = []
        for index, image, (x, y) in zip(indices, images, places):
            out.alpha_composite(image, (x, y))

            records.append(dict(sprite=index, x=x, y=y, width=image.width, height=image.height))
        return out, records

    def fit_sheet(self):
        """Lay the sheet out for the pane as it now is, and fit it."""
        if self.frames and self.image.zoom.currentIndex() == 0 and (
                self.whole.isChecked() or len(self.selected_indices()) > 1):
            self.image.subject = None
            self.refresh()

    def refresh(self):
        if not self.frames:
            self.info.setText('No sprites in this bank')
            return
        if self.whole.isChecked():
            subject = ('bank',)
            image, _ = self.sheet(list(range(len(self.frames))))
            self.parts.setRowCount(0)
            self.info.setText(f'Whole bank | {len(self.frames)} sprites')
            if image.getbbox() is None and any(self.frames):
                self.info.setText(self.info.text() + ' | Nothing to draw: the texture page these parts '
                                  'name is empty in this VRAM. Try another texture page base or section.')
        elif len(self.selected_indices()) > 1:
            indices = self.selected_indices()
            subject = ('sheet', tuple(indices))
            image, _ = self.sheet(indices)
            self.parts.setRowCount(0)
            self.info.setText(f'{len(indices)} selected sprites | {image.width} x {image.height}')
        else:
            index = min(self.frame_index, len(self.frames)-1)
            subject = ('sprite', index)
            fit = self.image.zoom.currentIndex() == 0
            image = self.frame_image(index, self.origin.isChecked() and not fit)
            if fit and (visible := image.getbbox()) is not None:
                image = image.crop(visible)
            frame = self.frames[index]
            selected_parts = {item.row() for item in self.parts.selectedItems()}
            self.parts.blockSignals(True)
            self.parts.setRowCount(len(frame))
            for row, part in enumerate(frame):
                values = [str(row), str(part[0]), str(part[1]), str(part[9]), str(part[10]),
                          f'0x{part[5] | part[6] << 8:04X}',
                          f'0x{self.clut_overrides.get((index, row), self.cluts.get(index, part[2])):04X}',
                          '' if self.renderer else f'0x{part_page(part, self.base_for(index)):03X}', str(part[13]),
                          str(part[14]), str((part[3], part[4])), str((part[7], part[8]))]
                for col, value in enumerate(values):
                    self.parts.setItem(row, col, QTableWidgetItem(value))
            self.parts.clearSelection()
            for row in selected_parts:
                if row < len(frame):
                    self.parts.selectionModel().select(self.parts.model().index(row, 0),
                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            self.parts.blockSignals(False)
            self.info.setText(f'{index:02X} | {len(frame)} pieces | {image.width} x {image.height}')
        if self.clut_overrides:
            self.info.setText(self.info.text() + ' | Recoloured from the crosshair; PNG exports include it')
        self.image.set_image(image, subject=subject)

    def zoom_mode_changed(self, index):
        if not hasattr(self, 'parts'):
            return
        self.refresh()
        if index == 0:
            self.image.scale_image()

    def selected_indices(self):
        return sorted({item.row() for item in self.bank.selectedItems()})

    def save_current(self):
        if not self.frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save sprite', f'{file_stem(self.export_name)} sprite {self.frame_index:02X}.png', 'PNG (*.png)')
        if path:
            self.frame_image(self.frame_index, self.origin.isChecked()).save(path)

    def save_bank(self):
        if not self.frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save whole bank', file_stem(self.export_name) + '.png', 'PNG (*.png)')
        if path:
            image, records = self.sheet(list(range(len(self.frames))))
            image.save(path)
            Path(path).with_suffix('.json').write_text(json.dumps({'sprites': records}, indent=2), 'utf8')

    def save_selected(self):
        indices = self.selected_indices()
        if not indices:
            QMessageBox.information(self, 'Select sprites', 'Select one or more rows in the sprite list.')
            return
        self.save_batch(indices)

    def save_all(self):
        self.save_batch(range(len(self.frames)))

    def save_batch(self, indices):
        folder = QFileDialog.getExistingDirectory(self, 'Save PNG sprites')
        if folder:
            for index in indices:
                self.frame_image(index, self.origin.isChecked()).save(Path(folder)/f'{file_stem(self.export_name)} sprite {index:02X}.png')
