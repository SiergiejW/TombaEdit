"""Browser for WPP picture banks."""
import math
from pathlib import Path
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog)
from gui.widgets.image_view import ImageView
from formats.sprites.wpp import tomba_palettes


class WppView(QWidget):
    def __init__(self, kind, pictures, vram=None):
        super().__init__()
        self.kind, self.pictures = kind, pictures
        self.outfits = tomba_palettes(vram) if vram is not None and kind == 'frames' else []
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.whole = QPushButton('Whole bank')
        self.whole.setCheckable(True)
        self.whole.setChecked(True)
        self.whole.toggled.connect(self.refresh)
        bar.addWidget(self.whole)
        bar.addWidget(QLabel('Palette:'))
        self.palette = QComboBox()
        self.palette.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.palette)
        save = QPushButton('Save all PNGs...')
        save.clicked.connect(self.save_all)
        bar.addWidget(save)
        bar.addStretch()
        layout.addLayout(bar)
        split = QSplitter()
        self.table = QTableWidget(len(pictures), 5)
        self.table.setHorizontalHeaderLabels(['Picture', 'Width', 'Height', 'Packed', 'Offset'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row, picture in enumerate(pictures):
            values = (f'Picture {picture.index:03d}', str(picture.width), str(picture.height),
                      f'{picture.packed:,}', f'0x{picture.offset:06X}')
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.currentCellChanged.connect(self.select)
        split.addWidget(self.table)
        self.image = ImageView()
        self.image.zoom.setCurrentIndex(3)
        split.addWidget(self.image)
        split.setSizes([380, 800])
        layout.addWidget(split, 1)
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info)
        self.fill_palettes(0)
        self.refresh()

    def fill_palettes(self, row):
        """Outfit rows for Tomba's frames; a TIM entry brings its own."""
        picture = self.pictures[row] if self.pictures else None
        own = len(picture.cluts) if picture is not None and picture.cluts is not None else 0
        wanted = ([f'Outfit {i}' for i in range(len(self.outfits))]
                  + [f'Own palette {i}' for i in range(own)] + ['Grey indices'])
        current = [self.palette.itemText(i) for i in range(self.palette.count())]
        if wanted != current:
            self.palette.blockSignals(True)
            self.palette.clear()
            self.palette.addItems(wanted)
            self.palette.blockSignals(False)

    def colours(self, picture):
        name = self.palette.currentText()
        if name.startswith('Outfit'):
            return self.outfits[int(name.split()[1])]
        if name.startswith('Own') and picture.cluts is not None:
            row = int(name.split()[2])
            if row < len(picture.cluts):
                return picture.cluts[row]
        return None

    def render(self, picture):
        return picture.image(self.colours(picture))

    def select(self, row, column=0, old_row=-1, old_column=-1):
        if not 0 <= row < len(self.pictures):
            return
        self.fill_palettes(row)
        if self.whole.isChecked():
            self.whole.setChecked(False)
        else:
            self.refresh()
        picture = self.pictures[row]
        print(f'selected: WPP picture {picture.index:03d} | {picture.width} x {picture.height} | '
              f'{picture.packed:,} packed bytes @ 0x{picture.offset:06X}')

    def refresh(self):
        if not self.pictures:
            self.info.setText('Empty picture bank')
            return
        if self.whole.isChecked():
            images = [self.render(p) for p in self.pictures]
            width = max(im.width for im in images) + 4
            height = max(im.height for im in images) + 4
            columns = max(1, math.ceil(math.sqrt(len(images) * height / width)))
            sheet = Image.new('RGBA', (width * columns, height * math.ceil(len(images) / columns)))
            for n, image in enumerate(images):
                sheet.alpha_composite(image, (n % columns * width, n // columns * height))
            self.image.set_image(sheet)
            self.info.setText(f'Whole bank | {len(images)} pictures')
            return
        picture = self.pictures[max(0, self.table.currentRow())]
        self.image.set_image(self.render(picture))
        what = 'GAM-compressed TIM' if self.kind == 'tim' else 'run-length packed frame'
        self.info.setText(f'Picture {picture.index:03d} | {what} | {picture.width} x {picture.height} | '
                          f'{picture.packed:,} bytes packed')

    def save_all(self):
        folder = QFileDialog.getExistingDirectory(self, 'Save PNG pictures')
        if folder:
            for picture in self.pictures:
                self.render(picture).save(Path(folder) / f'picture_{picture.index:04d}.png')
            print(f'wrote {len(self.pictures)} pictures to {folder}')
