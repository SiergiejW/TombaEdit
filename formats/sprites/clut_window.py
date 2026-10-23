"""A window that recolours sprite pieces from the Animations tab: the pieces
of the frame on screen, which of them a palette goes to, and the VRAM to
pick the palette in. It writes the same palette overrides as the Sprites
tab, so both tabs and the animation playback draw with them."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton, QTableWidget,
                             QTableWidgetItem, QAbstractItemView, QSplitter)
from formats.images.vram_viewer import VramView

SCOPES = ('Selected pieces', 'Whole frame', 'Every frame of the animation', 'Whole bank')


class ClutWindow(QDialog):
    """`sprites`: the bank's SpriteView, which keeps the overrides;
    `player`: the AnimationView whose frame is recoloured."""

    def __init__(self, sprites, player):
        super().__init__(player)
        self.setWindowTitle('CLUTs')
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.sprites, self.player, self.frame = sprites, player, None
        layout = QVBoxLayout(self)
        self.title = QLabel()
        layout.addWidget(self.title)
        split = QSplitter(Qt.Orientation.Vertical)
        self.parts = QTableWidget(0, 5)
        self.parts.setHorizontalHeaderLabels(['Piece', 'U, V', 'Size', 'CLUT', 'Own CLUT'])
        self.parts.verticalHeader().hide()
        self.parts.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.parts.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.parts.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.parts.itemSelectionChanged.connect(self.show_palette)
        split.addWidget(self.parts)
        frames = sprites.frames
        self.vram = VramView(sprites.vram, {p[2] & 0x7FFF for frame in frames for p in frame}, 'VRAM', embedded=True)
        self.scope = QComboBox()
        self.scope.addItems(SCOPES)
        self.scope.setToolTip('What the palette the crosshair is put on goes to. With no piece selected, '
                              'the whole frame.')
        reset = QPushButton('Reset CLUTs')
        reset.setToolTip('Draw every piece of the bank through its own palette again.')
        reset.clicked.connect(self.reset)
        self.vram.add_controls(QLabel('Crosshair recolours:'), self.scope, reset)
        self.vram.clut_picked.connect(self.recolour)
        split.addWidget(self.vram)
        split.setSizes([160, 420])
        layout.addWidget(split, 1)
        self.resize(760, 640)

    def follow(self, frame):
        """Show the pieces of the frame the animation is on."""
        if frame == self.frame:
            return
        self.frame = frame
        self.fill()

    def fill(self):
        frames, frame = self.sprites.frames, self.frame
        parts = frames[frame] if frame is not None and 0 <= frame < len(frames) else []
        chosen = {item.row() for item in self.parts.selectedItems()}
        self.title.setText(f'Frame {frame:02X} | {len(parts)} pieces' if parts else 'No frame on screen')
        self.parts.blockSignals(True)
        self.parts.setRowCount(len(parts))
        for row, part in enumerate(parts):
            values = (str(row), f'{part[0]}, {part[1]}', f'{part[9]} x {part[10]}',
                      f'0x{self.sprites.part_clut(frame, row):04X}', f'0x{part[2] & 0x7FFF:04X}')
            for column, value in enumerate(values):
                self.parts.setItem(row, column, QTableWidgetItem(value))
        for row in chosen:
            if row < len(parts):
                self.parts.selectRow(row)
        self.parts.blockSignals(False)
        self.show_palette()

    def show_palette(self):
        if self.frame is None or not self.sprites.frames[self.frame]:
            return
        rows = sorted({item.row() for item in self.parts.selectedItems()})
        self.vram.show_clut(self.sprites.part_clut(self.frame, rows[0] if rows else 0), flash=False)

    def targets(self):
        """[(frame, piece)] the chosen scope covers."""
        frames, scope = self.sprites.frames, self.scope.currentIndex()
        rows = sorted({item.row() for item in self.parts.selectedItems()})
        if scope == 0 and rows:
            return [(self.frame, row) for row in rows]
        if scope <= 1:
            shown = [self.frame]
        elif scope == 2 and self.player.script is not None:
            shown = sorted(set(self.player.script.frames))
        else:
            shown = range(len(frames))
        return [(frame, part) for frame in shown if 0 <= frame < len(frames) for part in range(len(frames[frame]))]

    def recolour(self, word):
        if self.frame is None:
            return
        self.sprites.recolour(self.targets(), word)
        self.fill()

    def reset(self):
        self.sprites.reset_palettes()
        self.fill()
