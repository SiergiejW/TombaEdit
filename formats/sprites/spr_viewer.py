"""Sprite bank browser using the bank-first table layout.

The section's VRAM runs along the bottom. Its crosshair is the palette
control of the sprites above it: putting it on a palette row redraws the
selected pieces, the sprite or the whole bank through that palette, and
selecting a sprite or a piece moves it to the palette they use and outlines
where in VRAM their pixels come from.
"""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, pyqtSignal, QItemSelectionModel
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox, QComboBox)
from gui.widgets.image_view import ImageView, file_stem
from formats.images.vram_viewer import VramView
from disc.reader import FormatError
from psx.graphics import render_sprite, part_page, guess_page, palette_missing


PART_COLOURS = ((255, 80, 80, 255), (80, 220, 255, 255), (255, 220, 60, 255), (120, 255, 120, 255),
                (255, 120, 255, 255), (255, 160, 60, 255))


FRAME_COLOUR = (255, 255, 255, 255)


class SpriteView(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, frames, vram, pages=None, renderer=None, default=None, cluts=None):
        """`pages` maps frame numbers to the texture page base of an object
        that shows them; frames nobody places borrow the nearest known one,
        or `default` when the bank is not placed at all. `renderer` draws
        frames whose pixels are not in VRAM."""
        super().__init__()
        self.frames, self.vram, self.renderer = frames, vram, renderer
        self.pages = dict(pages or {})
        self.cluts = dict(cluts or {})  # CLUTs supplied by a custom drawing object
        self.known = sorted(self.pages)
        self.guess = default
        self.export_name = 'sprites'    # prefix of default file names, set by the window
        self.cache = {}
        self.clut_overrides = {}  # (sprite, part) -> palette address; preview only
        self.frame_index = 0
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
        self.frame_bounds = QCheckBox('Sprite bounds')
        self.frame_bounds.setToolTip('Draw a box around every sprite, on its own and on a sheet. '
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
        left.setMinimumWidth(410)
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel('Sprites'))
        self.bank = QTableWidget(len(frames), 6)
        self.bank.setHorizontalHeaderLabels(['Sprite', '#', 'Parts', 'W', 'H', 'Pages'])
        self.bank.verticalHeader().hide()
        self.bank.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bank.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.bank.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.bank.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.bank.setDragEnabled(False)
        self.bank.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in enumerate((0, 36, 48, 36, 36, 86)):
            if column:
                self.bank.setColumnWidth(column, width)
        self.bank.currentCellChanged.connect(self.row_changed)
        self.bank.cellDoubleClicked.connect(self.frame_sprite)
        self.bank.itemSelectionChanged.connect(self.selected)
        ll.addWidget(self.bank)
        splitter.addWidget(left)
        right = QSplitter(Qt.Orientation.Vertical)
        self.image = ImageView()
        self.image.zoom.setCurrentIndex(0)
        right.addWidget(self.image)
        pieces = QWidget()
        pl = QVBoxLayout(pieces)
        pl.addWidget(QLabel('Pieces'))
        self.parts = QTableWidget(0, 12)
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
        splitter.setSizes([410, 780])
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
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info)
        self.rebuild()

    def zoom_by(self, step):
        self.image.zoom.setCurrentIndex(max(0, min(self.image.zoom.count()-1,
                                                   self.image.zoom.currentIndex()+step)))

    def base_for(self, index):
        """Texture page base a frame is drawn with."""
        if self.page_base.value() >= 0:
            return self.page_base.value()
        if self.known:
            return self.pages[min(self.known, key=lambda frame: abs(frame - index))]
        if self.guess is None:
            self.guess = guess_page(self.frames, self.vram)
        return self.guess

    def frame_image(self, index, origin=False):
        if index not in self.cache:
            try:
                overrides = {part: clut for (sprite, part), clut in self.clut_overrides.items() if sprite == index}
                parts = [tuple(clut if col == 2 else value for col, value in enumerate(part))
                         if (clut := overrides.get(n, self.cluts.get(index))) is not None else part
                         for n, part in enumerate(self.frames[index])]
                self.cache[index] = self.renderer(index, overrides) if self.renderer else render_sprite(
                    parts, self.vram, tpage=self.base_for(index),
                    grey_missing=self.grey.isChecked())
            except FormatError:
                self.cache[index] = Image.new('RGBA', (1, 1))
        image = self.cache[index]
        if self.bounds.isChecked() and self.frames[index]:
            image = self.outlined(image, self.frames[index])
        if self.frame_bounds.isChecked() and self.frames[index]:
            image = image.copy()
            ImageDraw.Draw(image).rectangle((0, 0, image.width - 1, image.height - 1), outline=FRAME_COLOUR)
        if not origin or not self.frames[index]:
            return image
        bounds = [part for frame in self.frames for part in frame]
        left = min([part[13] for part in bounds] + [0])
        top = min([part[14] for part in bounds] + [0])
        right = max([part[13]+part[9] for part in bounds] + [1])
        bottom = max([part[14]+part[10] for part in bounds] + [1])
        out = Image.new('RGBA', (right-left, bottom-top))
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
            values = [f'Sprite {i:03d}', str(i), str(len(frame)), str(width),
                      str(height), pages]
            for col, value in enumerate(values):
                self.bank.setItem(i, col, QTableWidgetItem(value))
        self.bank.blockSignals(False)
        self.refresh()

    def row_changed(self, row, column, old_row, old_column):
        if row < 0:
            return
        self.frame_index = row
        self.whole.setChecked(False)
        self.refresh()
        frame = self.frames[row]
        if frame and not self.renderer and any(palette_missing(self.vram, part[2]) for part in frame):
            self.info.setText(self.info.text() + ' | palette row empty in this VRAM'
                              + (', shown in grey' if self.grey.isChecked() else ''))
        self.show_in_vram()
        print(f'selected: sprite {row:03d} | {len(frame)} pieces'
              + ('' if self.renderer or not frame else f' | texture page base 0x{self.base_for(row):X}'))

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
        for sprite in sprites:
            for part in range(len(self.frames[sprite])) if scope else selected:
                self.clut_overrides[sprite, part] = value
        self.cache.clear()
        self.refresh()

    def reset_palettes(self):
        self.clut_overrides.clear()
        self.cache.clear()
        self.refresh()
        self.show_in_vram()

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
        images = [self.frame_image(i, self.origin.isChecked()) for i in indices]
        width = max(im.width for im in images) + 8
        height = max(im.height for im in images) + 8
        cols = max(1, math.ceil(math.sqrt(len(indices))))
        out = Image.new('RGBA', (width*cols, height*math.ceil(len(indices)/cols)))
        records = []
        draw = ImageDraw.Draw(out)
        for n, (index, image) in enumerate(zip(indices, images)):
            x, y = n%cols*width, n//cols*height
            out.alpha_composite(image, (x, y))

            records.append(dict(sprite=index, x=x, y=y, width=image.width, height=image.height))
        return out, records

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
            image = self.frame_image(index, self.origin.isChecked())
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
            self.info.setText(f'Sprite {index:03d} | {len(frame)} pieces | {image.width} x {image.height}')
        if self.clut_overrides:
            self.info.setText(self.info.text() + ' | Recoloured from the crosshair; PNG exports include it')
        self.image.set_image(image, subject=subject)

    def selected_indices(self):
        return sorted({item.row() for item in self.bank.selectedItems()})

    def save_current(self):
        if not self.frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save sprite', f'{file_stem(self.export_name)} sprite {self.frame_index:04d}.png', 'PNG (*.png)')
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
                self.frame_image(index, self.origin.isChecked()).save(Path(folder)/f'{file_stem(self.export_name)} sprite {index:04d}.png')
