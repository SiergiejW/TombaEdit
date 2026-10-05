"""Browser for WPP picture banks."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QFileDialog, QMessageBox)
from gui.widgets.image_view import ImageView, file_stem


class WppView(QWidget):
    def __init__(self, kind, pictures, palettes=()):
        """`palettes` is [(name, sixteen colour words)] to offer for packed
        frames; TIM entries add the palettes they carry."""
        super().__init__()
        self.kind, self.pictures, self.palettes = kind, pictures, list(palettes)
        self.export_name = 'pictures'   # prefix of default file names, set by the window
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
        self.bounds = QCheckBox('Picture bounds')
        self.bounds.setToolTip('Draw a box around every picture. Saved pictures include it while this is ticked.')
        self.bounds.toggled.connect(self.refresh)
        bar.addWidget(self.bounds)
        bar.addStretch()
        layout.addLayout(bar)
        saves = QHBoxLayout()
        for label, callback in (('Save picture...', self.save_current), ('Save whole bank...', self.save_bank),
                                ('Save selected PNGs...', self.save_selected), ('Save all PNGs...', self.save_all)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            saves.addWidget(button)
        saves.addStretch()
        layout.addLayout(saves)
        split = QSplitter()
        self.table = QTableWidget(len(pictures), 5)
        self.table.setHorizontalHeaderLabels(['Picture', 'Width', 'Height', 'Packed', 'Offset'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row, picture in enumerate(pictures):
            values = (f'Picture {picture.index:03d}', str(picture.width), str(picture.height),
                      f'{picture.packed:,}', f'0x{picture.offset:06X}')
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.currentCellChanged.connect(self.select)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        split.addWidget(self.table)
        self.image = ImageView()
        self.image.zoom.setCurrentIndex(0)
        split.addWidget(self.image)
        split.setSizes([380, 800])
        layout.addWidget(split, 1)
        self.info = QLabel()
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.info)
        self.fill_palettes(0)
        self.refresh()

    def fill_palettes(self, row):
        picture = self.pictures[row] if self.pictures else None
        own = len(picture.cluts) if picture is not None and picture.cluts is not None else 0
        wanted = ([name for name, _ in self.palettes]
                  + [f'Own palette {i}' for i in range(own)] + ['Grey indices'])
        current = [self.palette.itemText(i) for i in range(self.palette.count())]
        if wanted != current:
            self.palette.blockSignals(True)
            self.palette.clear()
            self.palette.addItems(wanted)
            self.palette.blockSignals(False)

    def colours(self, picture):
        index, name = self.palette.currentIndex(), self.palette.currentText()
        if 0 <= index < len(self.palettes):
            return self.palettes[index][1]
        if name.startswith('Own') and picture.cluts is not None:
            row = int(name.split()[2])
            if row < len(picture.cluts):
                return picture.cluts[row]
        return None

    def render(self, picture):
        image = picture.image(self.colours(picture))
        if self.bounds.isChecked():
            image = image.copy()
            ImageDraw.Draw(image).rectangle((0, 0, image.width - 1, image.height - 1), outline=(255, 255, 255, 255))
        return image

    def selected_rows(self):
        return sorted({item.row() for item in self.table.selectedItems()})

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

    def selection_changed(self):
        if not self.whole.isChecked():
            self.refresh()

    def sheet(self, rows):
        """Pictures laid out on a grid, and where each one landed."""
        images = [self.render(self.pictures[row]) for row in rows]
        width = max(im.width for im in images) + 4
        height = max(im.height for im in images) + 4
        columns = max(1, math.ceil(math.sqrt(len(images) * height / width)))
        sheet = Image.new('RGBA', (width * columns, height * math.ceil(len(images) / columns)))
        records = []
        for n, (row, image) in enumerate(zip(rows, images)):
            x, y = n % columns * width, n // columns * height
            sheet.alpha_composite(image, (x, y))
            records.append(dict(picture=self.pictures[row].index, x=x, y=y, width=image.width, height=image.height))
        return sheet, records

    def refresh(self):
        if not self.pictures:
            self.info.setText('Empty picture bank')
            return
        rows = self.selected_rows()
        if self.whole.isChecked():
            self.image.set_image(self.sheet(list(range(len(self.pictures))))[0])
            self.info.setText(f'Whole bank | {len(self.pictures)} pictures')
        elif len(rows) > 1:
            image = self.sheet(rows)[0]
            self.image.set_image(image)
            self.info.setText(f'{len(rows)} selected pictures | {image.width} x {image.height}')
        else:
            picture = self.pictures[max(0, self.table.currentRow())]
            self.image.set_image(self.render(picture))
            what = 'GAM-compressed TIM' if self.kind == 'tim' else 'run-length packed frame'
            self.info.setText(f'Picture {picture.index:03d} | {what} | {picture.width} x {picture.height} | '
                              f'{picture.packed:,} bytes packed')

    def save_current(self):
        row = self.table.currentRow()
        if not 0 <= row < len(self.pictures):
            QMessageBox.information(self, 'Select a picture', 'Select a row in the picture list.')
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save picture', f'{file_stem(self.export_name)} picture {row:04d}.png', 'PNG (*.png)')
        if path:
            self.render(self.pictures[row]).save(path)
            print(f'wrote {path}')

    def save_bank(self):
        if not self.pictures:
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Save whole bank', file_stem(self.export_name) + '.png', 'PNG (*.png)')
        if path:
            image, records = self.sheet(list(range(len(self.pictures))))
            image.save(path)
            Path(path).with_suffix('.json').write_text(json.dumps({'pictures': records}, indent=2), 'utf8')
            print(f'wrote {path} and its layout')

    def save_selected(self):
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, 'Select pictures', 'Select one or more rows in the picture list.')
            return
        self.save_batch(rows)

    def save_all(self):
        self.save_batch(range(len(self.pictures)))

    def save_batch(self, rows):
        folder = QFileDialog.getExistingDirectory(self, 'Save PNG pictures')
        if folder:
            for row in rows:
                self.render(self.pictures[row]).save(Path(folder) / f'{file_stem(self.export_name)} picture {self.pictures[row].index:04d}.png')
            print(f'wrote {len(list(rows))} pictures to {folder}')
