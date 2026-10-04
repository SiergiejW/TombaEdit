"""Sprite bank browser using the bank-first table layout."""
import json
import math
from pathlib import Path
from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox, QCheckBox)
from gui.widgets.image_view import ImageView
from psx.graphics import render_sprite


class SpriteView(QWidget):
    selection_changed = pyqtSignal(list)

    def __init__(self, frames, vram, page_base=0, renderer=None):
        super().__init__()
        self.frames, self.vram, self.renderer = frames, vram, renderer
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
        self.page_base = QSpinBox()
        self.page_base.setRange(0, 31)
        self.page_base.setValue(page_base)
        self.page_base.valueChanged.connect(self.rebuild)
        bar.addWidget(QLabel('Texture page offset:'))
        bar.addWidget(self.page_base)
        bar.addStretch()
        for label, callback in [('Save sprite...', self.save_current),
                                ('Save whole bank...', self.save_bank),
                                ('Save selected PNGs...', self.save_selected),
                                ('Save all PNGs...', self.save_all)]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
        layout.addLayout(bar)
        splitter = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel('Sprites'))
        self.bank = QTableWidget(len(frames), 7)
        self.bank.setHorizontalHeaderLabels(['Name', '#', 'Pieces', 'W', 'H', 'Pages', 'At'])
        self.bank.verticalHeader().hide()
        self.bank.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.bank.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.bank.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.bank.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.bank.setDragEnabled(False)
        self.bank.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.bank.currentCellChanged.connect(self.row_changed)
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
        self.parts.setHorizontalHeaderLabels(['#', 'U', 'V', 'W', 'H', 'Page', 'CLUT', 'Flip', 'X', 'Y', 'UV 2', 'UV 3'])
        self.parts.verticalHeader().hide()
        self.parts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.parts.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        pl.addWidget(self.parts)
        right.addWidget(pieces)
        right.setSizes([650, 200])
        splitter.addWidget(right)
        splitter.setSizes([340, 850])
        layout.addWidget(splitter, 1)
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info)
        self.rebuild()

    def zoom_by(self, step):
        self.image.zoom.setCurrentIndex(max(0, min(self.image.zoom.count()-1,
                                                   self.image.zoom.currentIndex()+step)))

    def frame_image(self, index, origin=False):
        if index not in self.cache:
            self.cache[index] = self.renderer(index) if self.renderer else render_sprite(
                self.frames[index], self.vram, self.page_base.value())
        image = self.cache[index]
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

    def rebuild(self):
        self.cache.clear()
        self.bank.blockSignals(True)
        for i, frame in enumerate(self.frames):
            if frame:
                x = min(p[13] for p in frame)
                y = min(p[14] for p in frame)
                width = max(p[13]+p[9] for p in frame)-x
                height = max(p[14]+p[10] for p in frame)-y
                pages = ', '.join(f'{p[5]:02X}' for p in frame[:3])
            else:
                width = height = 0
                pages = ''
            values = [f'Sprite {i:03d}', str(i), str(len(frame)), str(width),
                      str(height), pages, '']
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

    def selected(self):
        self.selection_changed.emit(self.selected_indices())

    def restore_state(self, indices):
        if not indices:
            return
        self.bank.blockSignals(True)
        for index in indices:
            if 0 <= index < self.bank.rowCount():
                self.bank.selectRow(index)
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
        else:
            index = min(self.frame_index, len(self.frames)-1)
            image = self.frame_image(index, self.origin.isChecked())
            frame = self.frames[index]
            self.parts.setRowCount(len(frame))
            for row, part in enumerate(frame):
                values = [str(row), str(part[0]), str(part[1]), str(part[9]), str(part[10]),
                          f'0x{part[5]:04X}', f'0x{part[2]:04X}', '', str(part[13]),
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
