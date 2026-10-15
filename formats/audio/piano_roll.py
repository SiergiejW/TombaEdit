"""Read-only piano roll synchronized with the sequence player's transport."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QGraphicsScene, QGraphicsView, QSlider, QWidget)

COLOURS = ('#4f8dd6', '#d65f4f', '#57b36b', '#c9a227', '#8e6fd0', '#3fb0b0', '#d67fb0', '#7f8c8d')


class RollView(QGraphicsView):
    def mousePressEvent(self, event):
        point = self.mapToScene(event.pos())
        if event.button() == Qt.MouseButton.LeftButton and point.y() < 24:
            self.owner.seek(point.x())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.mapToScene(event.pos()).y() < 24:
            self.owner.seek(self.mapToScene(event.pos()).x())
            event.accept()
        else:
            super().mouseMoveEvent(event)


class SequenceRoll(QWidget):
    def __init__(self, source, player):
        super().__init__(player)
        self.source, self.player = source, player
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.program = QComboBox()
        row.addWidget(self.program)
        row.addWidget(QLabel('Horizontal zoom'))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(20, 300)
        self.zoom.setValue(80)
        row.addWidget(self.zoom)
        row.addStretch()
        layout.addLayout(row)
        self.scene = QGraphicsScene(self)
        self.view = RollView(self.scene)
        self.view.owner = self
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setBackgroundBrush(QColor('#202020'))
        layout.addWidget(self.view)
        self.program.currentIndexChanged.connect(self.redraw)
        self.zoom.valueChanged.connect(self.redraw)
        player.player.positionChanged.connect(self.position)
        self.set_source(source)

    def set_source(self, source):
        self.source = source
        self.program.blockSignals(True)
        self.program.clear()
        self.program.addItem('All programs', None)
        if source:
            for program in sorted(source.used):
                self.program.addItem(f'Program {program}', program)
        self.program.blockSignals(False)
        self.redraw()

    def seek(self, x):
        self.player.player.setPosition(round(max(0, min(self.source.length, (x - 52) / self.zoom.value())) * 1000))

    def redraw(self):
        self.scene.clear()
        if self.source is None:
            self.cursor = None
            return
        notes = self.source.notes
        pitches = [n[2] for n in notes] or [60]
        low, high = max(0, min(pitches) - 2), min(127, max(pitches) + 2)
        self.roll_height = (high - low + 1) * 14
        scale, left = self.zoom.value(), 52
        width = max(800, left + self.source.length * scale)
        for key in range(low, high + 1):
            y = (high - key) * 14 + 24
            dark = key % 12 in (1, 3, 6, 8, 10)
            self.scene.addRect(0, y, width, 14, QPen(QColor('#303030')),
                               QColor('#252525' if dark else '#343434'))
            name = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[key % 12]
            label = self.scene.addText(f'{name}{key // 12 - 1}')
            label.setDefaultTextColor(QColor('#cccccc')); label.setPos(0, y - 3)
        for second in range(int(self.source.length) + 2):
            x = left + second * scale
            self.scene.addLine(x, 24, x, self.roll_height + 24, QPen(QColor('#494949')))
            label = self.scene.addText(f'{second}s')
            label.setDefaultTextColor(QColor('#cccccc')); label.setPos(x, 0)
        selected = self.program.currentData()
        for start, end, key, velocity, state in notes:
            program = state['program']
            if selected is not None and program != selected:
                continue
            rect = self.scene.addRect(left + start * scale, 24 + (high - key) * 14,
                                      max(2, (end - start) * scale), 12,
                                      QPen(Qt.PenStyle.NoPen), QColor(COLOURS[program % len(COLOURS)]))
            rect.setToolTip(f'Program {program} | key {key} | velocity {velocity} | {start:.3f} to {end:.3f}s')
        self.cursor = self.scene.addLine(left, 24, left, self.roll_height + 24, QPen(QColor('#ff79bd'), 2))
        self.cursor.setZValue(10)
        self.scene.setSceneRect(0, 0, width + 20, self.roll_height + 45)
        self.position(self.player.player.position())

    def position(self, milliseconds):
        if self.cursor is None:
            return
        x = 52 + milliseconds / 1000 * self.zoom.value()
        self.cursor.setLine(x, 24, x, self.roll_height + 24)


class PianoRoll(QDialog):
    def __init__(self, source, player):
        super().__init__(player)
        self.setWindowTitle('Sequence: ' + source.title(-1))
        self.resize(1120, 620)
        layout = QVBoxLayout(self)
        self.roll = SequenceRoll(source, player)
        layout.addWidget(self.roll)
        row = QHBoxLayout()
        from gui.widgets.transport_icons import set_glyph
        for glyph, callback in (('play', player.toggle_play), ('stop', player.stop)):
            button = QPushButton()
            set_glyph(button, glyph)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setRange(0, round(source.length * 1000))
        self.timeline.sliderMoved.connect(player.player.setPosition)
        player.player.positionChanged.connect(self.position)
        row.addWidget(self.timeline, 1)
        export = QPushButton('Export MIDI...')
        export.clicked.connect(player.export_midi)
        row.addWidget(export)
        layout.addLayout(row)
        layout.addWidget(QLabel('Click or drag the time ruler to seek. Drag the note area to pan.'))

    def position(self, milliseconds):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(milliseconds)
