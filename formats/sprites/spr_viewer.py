"""Sprite bank browser using the bank-first table layout."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, pyqtSignal, QItemSelectionModel
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox)
from gui.widgets.image_view import ImageView
from disc.reader import FormatError
from psx.graphics import render_sprite, part_page


PART_COLOURS = ((255, 80, 80, 255), (80, 220, 255, 255), (255, 220, 60, 255), (120, 255, 120, 255),
                (255, 120, 255, 255), (255, 160, 60, 255))


class SpriteView(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, frames, vram, pages=None, renderer=None, default=None):
        """`pages` maps frame numbers to the texture page base of an object
        that shows them; frames nobody places borrow the nearest known one,
        or `default` when the bank is not placed at all. `renderer` draws
        frames whose pixels are not in VRAM."""
        super().__init__()
        self.frames, self.vram, self.renderer = frames, vram, renderer
        self.pages = dict(pages or {})
        self.known = sorted(self.pages)
        self.guess = default
        self.cache = {}
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
        self.bounds = QCheckBox('Boundaries')
        self.bounds.setToolTip('Outline every part of a frame, and each frame on a sheet. '
                               'Saved pictures include the outlines while this is ticked.')
        self.bounds.toggled.connect(self.refresh)
        bar.addWidget(self.bounds)
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
        self.parts = QTableWidget(0, 12)
        self.parts.setHorizontalHeaderLabels(['#', 'U', 'V', 'W', 'H', 'Page', 'CLUT', 'Drawn page', 'X', 'Y', 'UV 1', 'UV 2'])
        self.parts.verticalHeader().hide()
        self.parts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.parts.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
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
            # Nothing places this bank: take the base under which the most
            # pixels of a few frames come out opaque.
            sample = [f for f in self.frames if f][:12]
            def opaque(base):
                try:
                    return sum(sum(render_sprite(f, self.vram, tpage=base).getchannel('A').histogram()[1:])
                               for f in sample)
                except FormatError:
                    return -1
            self.guess = max(range(32), key=opaque) if sample else 0
        return self.guess

    def frame_image(self, index, origin=False):
        if index not in self.cache:
            try:
                self.cache[index] = self.renderer(index) if self.renderer else render_sprite(
                    self.frames[index], self.vram, tpage=self.base_for(index))
            except FormatError:
                self.cache[index] = Image.new('RGBA', (1, 1))
        image = self.cache[index]
        if self.bounds.isChecked() and self.frames[index]:
            image = self.outlined(image, self.frames[index])
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
        print(f'selected: sprite {row:03d} | {len(frame)} pieces'
              + ('' if self.renderer or not frame else f' | texture page base 0x{self.base_for(row):X}'))

    def frame_sprite(self, row, column):
        if row < 0:
            return
        self.frame_index = row
        self.whole.setChecked(False)
        self.image.zoom.setCurrentIndex(0)
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
            if self.bounds.isChecked():
                draw.rectangle((x, y, x + width - 1, y + height - 1), outline=(255, 255, 255, 90))
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
                self.info.setText(self.info.text() + ' | Nothing to draw: the texture page or palette rows '
                                  'these parts name are empty in this VRAM. The game fills them while it runs.')
        elif len(self.selected_indices()) > 1:
            indices = self.selected_indices()
            image, _ = self.sheet(indices)
            self.parts.setRowCount(0)
            self.info.setText(f'{len(indices)} selected sprites | {image.width} x {image.height}')
        else:
            index = min(self.frame_index, len(self.frames)-1)
            image = self.frame_image(index, self.origin.isChecked())
            frame = self.frames[index]
            self.parts.setRowCount(len(frame))
            for row, part in enumerate(frame):
                values = [str(row), str(part[0]), str(part[1]), str(part[9]), str(part[10]),
                          f'0x{part[5] | part[6] << 8:04X}', f'0x{part[2]:04X}',
                          '' if self.renderer else f'0x{part_page(part, self.base_for(index)):03X}', str(part[13]),
                          str(part[14]), str((part[3], part[4])), str((part[7], part[8]))]
                for col, value in enumerate(values):
                    self.parts.setItem(row, col, QTableWidgetItem(value))
            self.info.setText(f'Sprite {index:03d} | {len(frame)} pieces | {image.width} x {image.height}')
        self.image.set_image(image)

    def selected_indices(self):
        return sorted({item.row() for item in self.bank.selectedItems()})

    def save_current(self):
        if not self.frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save sprite', f'sprite_{self.frame_index:04d}.png', 'PNG (*.png)')
        if path:
            self.frame_image(self.frame_index, self.origin.isChecked()).save(path)

    def save_bank(self):
        if not self.frames:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save whole bank', 'sprites.png', 'PNG (*.png)')
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
                self.frame_image(index, self.origin.isChecked()).save(Path(folder)/f'sprite_{index:04d}.png')
