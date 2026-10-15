"""Read-only piano roll synchronized with the sequence player's transport."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QComboBox, QGraphicsScene, QGraphicsView, QSlider)

COLOURS = ('#4f8dd6', '#d65f4f', '#57b36b', '#c9a227', '#8e6fd0', '#3fb0b0', '#d67fb0', '#7f8c8d')


class PianoRoll(QDialog):
    def __init__(self, source, player):
        super().__init__(player)
        self.source, self.player = source, player
        self.setWindowTitle('Sequence: ' + source.title(-1))
        self.resize(1120, 620)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.program = QComboBox()
        self.program.addItem('All programs', None)
        for program in sorted(source.used):
            self.program.addItem(f'Program {program}', program)
        row.addWidget(self.program)
        row.addWidget(QLabel('Horizontal zoom'))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(20, 300)
        self.zoom.setValue(80)
        row.addWidget(self.zoom)
        row.addStretch()
        layout.addLayout(row)
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.view.setBackgroundBrush(QColor('#202020'))
        layout.addWidget(self.view)
        controls = QHBoxLayout()
        for name, callback in (('Play / pause', player.toggle_play), ('Stop', player.stop),
                               ('Export MIDI...', player.export_midi)):
            button = QPushButton(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(QLabel('Time runs left to right, pitch runs bottom to top. Drag to pan. '
                                'Notes show program, pitch and velocity on hover.'))
        self.program.currentIndexChanged.connect(self.redraw)
        self.zoom.valueChanged.connect(self.redraw)
        player.player.positionChanged.connect(self.position)
        self.redraw()

    def redraw(self):
        self.scene.clear()
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
        x = 52 + milliseconds / 1000 * self.zoom.value()
        self.cursor.setLine(x, 24, x, self.roll_height + 24)
