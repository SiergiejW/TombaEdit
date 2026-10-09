"""How the pictures of a bank are set out on one sheet."""
import math
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QCheckBox, QSlider


def arrange(sizes, margin, even=False, aspect=1.0):
    """Place pictures of the given (width, height) sizes in order, `margin`
    pixels apart, and return their top-left corners and the sheet's size.
    The sheet is made about `aspect` times as wide as it is tall, so that it
    fills the pane it is shown in.

    Packed, each row is as tall as its tallest picture and pictures sit
    side by side, so small ones do not take the room of large ones. Even,
    every picture has a cell the size of the largest."""
    if not sizes:
        return [], (1, 1)
    if even:
        width = max(w for w, h in sizes) + margin
        height = max(h for w, h in sizes) + margin
        columns = max(1, min(len(sizes), round(math.sqrt(len(sizes) * height / width * aspect))))
        places = [(n % columns * width, n // columns * height) for n in range(len(sizes))]
        return places, (width * columns, height * math.ceil(len(sizes) / columns))
    # Rows are filled up to the width of a sheet of that shape holding
    # everything; rows of unequal pictures waste some room, so a few widths
    # round it are tried and the one nearest the shape is kept.
    area = sum((w + margin) * (h + margin) for w, h in sizes)
    widest = max(w for w, h in sizes)
    best = None
    for slack in (1.0, 1.05, 1.1, 1.15, 1.2, 1.3, 1.4):
        places, size = pack(sizes, margin, max(widest, math.ceil(math.sqrt(area * aspect) * slack)))
        miss = abs(math.log(size[0] / size[1] / aspect))
        if best is None or miss < best[0]:
            best = (miss, places, size)
    return best[1], best[2]


def pack(sizes, margin, limit):
    """Rows of pictures, each row no wider than `limit`."""
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

    def arrange(self, sizes, pane=None):
        """Places and sheet size for these pictures; `pane` is the widget
        the sheet is shown in, whose shape the sheet takes."""
        aspect = 1.0
        if pane is not None and pane.width() > 50 and pane.height() > 50:
            aspect = pane.width() / pane.height()
        return arrange(sizes, self.slider.value(), self.even.isChecked(), aspect)
