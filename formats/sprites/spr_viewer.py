"""Sprite bank browser using the bank-first table layout."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, pyqtSignal, QItemSelectionModel
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox, QComboBox)
from gui.widgets.image_view import ImageView, file_stem
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
        palette_bar = QHBoxLayout()
        self.palette_scope = QComboBox()
        self.palette_scope.addItems(['Selected pieces', 'Whole sprite', 'Whole bank'])
        self.palette_choice = QComboBox()
        self.palette_choice.addItem('Original CLUTs', None)
        import numpy as np
        used = {p[2] & 0x7FFF for frame in frames for p in frame}
        occupied = set(np.flatnonzero(vram.reshape(512, 64, 16).any(axis=2)).tolist())
        for address in sorted(used | occupied):
            x, y = (address & 63) * 16, address >> 6
            self.palette_choice.addItem(f'0x{address:04X} | X {x}, Y {y}', address)
        self.palette_address = QSpinBox()
        self.palette_address.setRange(-1, 0x7FFF)
        self.palette_address.setDisplayIntegerBase(16)
        self.palette_address.setPrefix('0x')
        self.palette_address.setSpecialValueText('Original')
        self.palette_address.setValue(-1)
        self.palette_choice.currentIndexChanged.connect(self.choose_palette)
        self.palette_address.valueChanged.connect(self.override_palette)
        reset_palettes = QPushButton('Reset CLUTs')
        reset_palettes.clicked.connect(self.reset_palettes)
        for widget in (QLabel('Preview CLUT:'), self.palette_scope, self.palette_choice,
                       self.palette_address, reset_palettes):
            palette_bar.addWidget(widget)
        pl.addLayout(palette_bar)
        self.parts = QTableWidget(0, 12)
        self.parts.setHorizontalHeaderLabels(['#', 'U', 'V', 'W', 'H', 'Page', 'CLUT', 'Drawn page', 'X', 'Y', 'UV 1', 'UV 2'])
        self.parts.verticalHeader().hide()
        self.parts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.parts.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.parts.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.parts.itemSelectionChanged.connect(self.show_part_palette)
        pl.addWidget(self.parts)
        right.addWidget(pieces)
        right.setSizes([650, 200])
        splitter.addWidget(right)
        splitter.setSizes([410, 780])
        layout.addWidget(splitter, 1)
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

    def show_part_palette(self):
        rows = sorted({item.row() for item in self.parts.selectedItems()})
        if not rows:
            return
        value = self.clut_overrides.get((self.frame_index, rows[0]), -1)
        self.palette_address.blockSignals(True)
        self.palette_address.setValue(value)
        self.palette_address.blockSignals(False)

    def choose_palette(self):
        value = self.palette_choice.currentData()
        # Selecting the same address should still apply it to a new part.
        self.palette_address.blockSignals(True)
        self.palette_address.setValue(-1 if value is None else value)
        self.palette_address.blockSignals(False)
        self.override_palette(self.palette_address.value())

    def override_palette(self, value):
        scope = self.palette_scope.currentIndex()
        selected = {item.row() for item in self.parts.selectedItems()}
        if scope == 0 and not selected:
            self.info.setText('Select one or more pieces first, or choose Whole sprite / Whole bank.')
            return
        sprites = range(len(self.frames)) if scope == 2 else [self.frame_index]
        for sprite in sprites:
            for part in range(len(self.frames[sprite])) if scope else selected:
                key = sprite, part
                if value < 0:
                    self.clut_overrides.pop(key, None)
                else:
                    self.clut_overrides[key] = value
        self.cache.clear()
        self.refresh()

    def reset_palettes(self):
        self.clut_overrides.clear()
        self.cache.clear()
        self.refresh()

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
            image, _ = self.sheet(list(range(len(self.frames))))
            self.parts.setRowCount(0)
            self.info.setText(f'Whole bank | {len(self.frames)} sprites')
            if image.getbbox() is None and any(self.frames):
                self.info.setText(self.info.text() + ' | Nothing to draw: the texture page these parts '
                                  'name is empty in this VRAM. Try another texture page base or section.')
        elif len(self.selected_indices()) > 1:
            indices = self.selected_indices()
            image, _ = self.sheet(indices)
            self.parts.setRowCount(0)
            self.info.setText(f'{len(indices)} selected sprites | {image.width} x {image.height}')
        else:
            index = min(self.frame_index, len(self.frames)-1)
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
            self.info.setText(self.info.text() + ' | Preview CLUT overrides active; PNG exports include them')
        self.image.set_image(image, preserve_view=self.image.image is not None)

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
