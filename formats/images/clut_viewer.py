"""Read-only PlayStation CLUT browser with selectable colour cells."""
import math
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QGridLayout, QPushButton, QScrollArea
from psx.graphics import rgba


class ClutView(QWidget):
    def __init__(self, data, words_per_row=256):
        super().__init__()
        self.words = np.frombuffer(data[:len(data)//2*2], dtype='<u2')
        self.words_per_row = words_per_row
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.row = QComboBox()
        self.row.addItems(f'Palette row {i:02d}' for i in range(math.ceil(len(self.words)/words_per_row)))
        self.row.currentIndexChanged.connect(self.refresh)
        controls.addWidget(QLabel('CLUT row:'))
        controls.addWidget(self.row)
        self.zoom = QComboBox()
        self.zoom.addItems(['100%', '150%', '200%', '300%'])
        self.zoom.currentIndexChanged.connect(self.resize_cells)
        controls.addWidget(QLabel('Swatch size:'))
        controls.addWidget(self.zoom)
        controls.addStretch()
        layout.addLayout(controls)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.buttons = []
        for i in range(words_per_row):
            button = QPushButton()
            button.setFixedSize(20, 20)
            button.clicked.connect(lambda checked=False, col=i: self.select(col))
            self.grid.addWidget(button, i//16, i%16)
            self.buttons.append(button)
        scroll.setWidget(host)
        layout.addWidget(scroll)
        self.details = QLabel()
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        self.refresh()

    def resize_cells(self):
        size = (20, 30, 40, 60)[self.zoom.currentIndex()]
        for button in self.buttons:
            button.setFixedSize(size, size)

    def refresh(self):
        start = self.row.currentIndex()*self.words_per_row
        for i, button in enumerate(self.buttons):
            if start+i >= len(self.words):
                button.hide()
                continue
            button.show()
            word = int(self.words[start+i])
            r, g, b, a = rgba(np.array([word], dtype=np.uint16))[0]
            button.setStyleSheet(f'background-color: rgb({r},{g},{b}); border: none; padding: 0;')
            button.setToolTip(f'Index {start+i} | PSX 0x{word:04X} | RGB #{r:02X}{g:02X}{b:02X}')
        self.select(0)

    def select(self, col):
        index = self.row.currentIndex()*self.words_per_row+col
        if index >= len(self.words):
            return
        word = int(self.words[index])
        for i, button in enumerate(self.buttons):
            value = int(self.words[self.row.currentIndex()*self.words_per_row+i]) if self.row.currentIndex()*self.words_per_row+i < len(self.words) else 0
            rgb = rgba(np.array([value], dtype=np.uint16))[0]
            border = '2px solid white' if i == col else 'none'
            button.setStyleSheet(f'background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]}); border: {border}; padding: 0;')
        r, g, b, a = rgba(np.array([word], dtype=np.uint16))[0]
        self.details.setText(f'Colour {index} | row {self.row.currentIndex()} column {col} | PSX 0x{word:04X} | RGB #{r:02X}{g:02X}{b:02X} | STP {(word>>15)&1} | Alpha {a}')
