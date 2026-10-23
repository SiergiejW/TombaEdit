"""GIFs of the level view: the whole view, the selected sprites, or the
texture of a model whose UVs move, over one cycle of every animation in it
or a chosen run of updates."""
import math
from PyQt6.QtWidgets import (QDialog, QFormLayout, QComboBox, QSpinBox, QRadioButton, QDialogButtonBox,
                             QHBoxLayout, QWidget, QLabel)

# Longest run a full cycle may come to, in updates (a minute at 50 a second).
LONGEST = 3000
SIZES = ((640, 480), (1280, 720), (1920, 1080))


def cycle_length(cycles, longest=LONGEST):
    """Updates after which all the given cycles (in updates each) are back
    where they started, at most `longest`."""
    total = 1
    for ticks in cycles:
        if ticks > 0:
            total = total * ticks // math.gcd(total, ticks)
            if total > longest:
                return longest
    return total


def step_at(frames, tick):
    """Index into [(mesh, ticks)] shown `tick` updates after the first."""
    total = sum(ticks for _, ticks in frames)
    tick %= max(1, total)
    for index, (_, ticks) in enumerate(frames):
        if tick < ticks:
            return index
        tick -= ticks
    return len(frames) - 1


def gif_ticks(start, count, rate):
    """The updates a GIF shows and each one's duration in milliseconds. A GIF
    counts in hundredths of a second and players stretch anything under 20 ms,
    so at 60 updates a second every other update is shown."""
    every = 1 if 1000 / rate >= 20 else 2
    shown = list(range(start, start + count, every)) or [start]
    times = [round((tick - start) * 100 / rate) * 10 for tick in shown + [start + count]]
    return shown, [max(20, b - a) for a, b in zip(times, times[1:])]


class GifDialog(QDialog):
    """What to save, at what size, over which updates."""

    def __init__(self, parent, subjects, view_size, cycle, rate):
        super().__init__(parent)
        self.setWindowTitle('Save GIF')
        form = QFormLayout(self)
        self.subject = QComboBox()
        for label, key in subjects:
            self.subject.addItem(label, key)
        form.addRow('Save:', self.subject)
        self.size = QComboBox()
        width, height = view_size
        self.size.addItem(f'View size ({width} x {height})', (width, height))
        self.size.addItem(f'Half ({width // 2} x {height // 2})', (width // 2, height // 2))
        for w, h in SIZES:
            self.size.addItem(f'{w} x {h}', (w, h))
        form.addRow('Size:', self.size)
        self.subject.currentIndexChanged.connect(
            lambda: self.size.setEnabled(self.subject.currentData() == 'view'))
        self.whole = QRadioButton(f'One cycle of every animation ({cycle} updates, '
                                  f'{cycle / rate:.1f} s)' + (' - cut short' if cycle >= LONGEST else ''))
        self.whole.setChecked(True)
        self.chosen = QRadioButton('Updates:')
        self.start, self.count = QSpinBox(), QSpinBox()
        self.start.setRange(0, 100000)
        self.count.setRange(1, LONGEST)
        self.count.setValue(min(cycle, 120))
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        for widget in (self.chosen, QLabel('from'), self.start, QLabel('for'), self.count):
            line.addWidget(widget)
        form.addRow('Frames:', self.whole)
        form.addRow('', row)
        form.addRow('', QLabel(f'The game makes {rate} updates a second; a count of 1 saves that one update.'))
        self.cycle = cycle
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def choice(self):
        """(subject key, (width, height), first update, number of updates)"""
        if self.whole.isChecked():
            return self.subject.currentData(), self.size.currentData(), 0, self.cycle
        return self.subject.currentData(), self.size.currentData(), self.start.value(), self.count.value()
