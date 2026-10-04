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
        controls.addStretch()
        layout.addLayout(controls)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setSpacing(2)
        self.buttons = []
        for i in range(words_per_row):
            button = QPushButton()
            button.setFixedSize(30, 30)
            button.clicked.connect(lambda checked=False, col=i: self.select(col))
            self.grid.addWidget(button, i//16, i%16)
            self.buttons.append(button)
        scroll.setWidget(host)
        layout.addWidget(scroll)
        self.details = QLabel()
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.details)
        self.refresh()

    def refresh(self):
        start = self.row.currentIndex()*self.words_per_row
        for i, button in enumerate(self.buttons):
            if start+i >= len(self.words):
                button.hide()
                continue
            button.show()
            word = int(self.words[start+i])
            r, g, b, a = rgba(np.array([word], dtype=np.uint16))[0]
            button.setStyleSheet(f'background-color: rgb({r},{g},{b}); border: 1px solid #777;')
            button.setToolTip(f'Index {start+i} | PSX 0x{word:04X} | RGB #{r:02X}{g:02X}{b:02X}')
        self.select(0)

    def select(self, col):
        index = self.row.currentIndex()*self.words_per_row+col
        if index >= len(self.words):
            return
        word = int(self.words[index])
        r, g, b, a = rgba(np.array([word], dtype=np.uint16))[0]
        self.details.setText(f'Colour {index} | row {self.row.currentIndex()} column {col} | PSX 0x{word:04X} | RGB #{r:02X}{g:02X}{b:02X} | STP {(word>>15)&1} | Alpha {a}')
