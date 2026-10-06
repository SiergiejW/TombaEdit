"""How the pictures of a bank are set out on one sheet."""
import math
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QCheckBox, QSlider


def arrange(sizes, margin, even=False):
    """Place pictures of the given (width, height) sizes in order, `margin`
    pixels apart, and return their top-left corners and the sheet's size.

    Packed, each row is as tall as its tallest picture and pictures sit
    side by side, so small ones do not take the room of large ones. Even,
    every picture has a cell the size of the largest."""
    if not sizes:
        return [], (1, 1)
    if even:
        width = max(w for w, h in sizes) + margin
        height = max(h for w, h in sizes) + margin
        columns = max(1, math.ceil(math.sqrt(len(sizes) * height / width)))
        places = [(n % columns * width, n // columns * height) for n in range(len(sizes))]
        return places, (width * columns, height * math.ceil(len(sizes) / columns))
    # Rows are filled up to the side of a square holding everything.
    area = sum((w + margin) * (h + margin) for w, h in sizes)
    limit = max(max(w for w, h in sizes), math.ceil(math.sqrt(area) * 1.15))
    places, x, y, row, right = [], 0, 0, 0, 0
    for w, h in sizes:
        if x and x + w > limit:
            x, y, row = 0, y + row + margin, 0
        places.append((x, y))
        right = max(right, x + w)
        x += w + margin
        row = max(row, h)
    return places, (max(1, right), max(1, y + row))


class SpacingControls(QWidget):
    """The gap between the pictures of a sheet, and whether they are packed
    or given equal cells."""
    changed = pyqtSignal()

    def __init__(self, margin=4):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('Spacing:'))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 32)
        self.slider.setValue(margin)
        self.slider.setFixedWidth(110)
        self.slider.setToolTip('Pixels left between the pictures of a sheet. Saved sheets use it too.')
        layout.addWidget(self.slider)
        self.value = QLabel()
        self.value.setMinimumWidth(34)
        layout.addWidget(self.value)
        self.even = QCheckBox('Even')
        self.even.setToolTip('Give every picture a cell the size of the largest, instead of packing '
                             'them side by side.')
        layout.addWidget(self.even)
        self.slider.valueChanged.connect(self.moved)
        self.even.toggled.connect(lambda on: self.changed.emit())
        self.moved(margin)

    def moved(self, value):
        self.value.setText(f'{value} px')
        self.changed.emit()

    def arrange(self, sizes):
        return arrange(sizes, self.slider.value(), self.even.isChecked())
