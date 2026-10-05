"""Preview model deformation banks with compatible WMD source geometry."""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QComboBox, QSlider, QPushButton
from formats.models.four import deform, topology
from formats.models.wmd_viewer import ModelView


class FourView(ModelView):
    def __init__(self):
        super().__init__()
        self.morphs = []
        self.candidates = []
        self.source = QComboBox()
        self.pose = QComboBox()
        self.weight = QSlider(Qt.Orientation.Horizontal)
        self.weight.setRange(0, 4096)
        self.weight_label = QLabel('0%')
        self.play = QPushButton('Play')
        bar = QHBoxLayout()
        for widget in (QLabel('Deformation:'), self.pose, QLabel('Source WMD:'), self.source,
                       self.play, self.weight, self.weight_label):
            bar.addWidget(widget)
        self.layout().insertLayout(0, bar)
        self.notice = QLabel('FOUR stores vertex deltas. A matching polygon count alone does not prove a source model link.')
        self.notice.setWordWrap(True)
        self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.layout().insertWidget(1, self.notice)
        self.timer = QTimer(self)
        self.timer.setInterval(33)
        self.timer.timeout.connect(self.advance)
        self.play.clicked.connect(self.toggle_play)
        self.pose.currentIndexChanged.connect(self.populate_sources)
        self.source.currentIndexChanged.connect(self.change_source)
        self.weight.valueChanged.connect(self.update_pose)
        self.direction = 1

    def set_four(self, morphs, candidates, vram, preferred=None):
        self.timer.stop()
        self.play.setText('Play')
        self.morphs, self.candidates, self.vram = morphs, candidates, vram
        self.preferred = preferred
        self.pose.blockSignals(True)
        self.pose.clear()
        for i, morph in enumerate(morphs):
            self.pose.addItem(f'{i:03d} | {sum(morph.counts)} polygons')
        self.pose.blockSignals(False)
        self.weight.setValue(0)
        self.populate_sources()

    def populate_sources(self):
        index = self.pose.currentIndex()
        self.source.blockSignals(True)
        self.source.clear()
        if index >= 0:
            for i, (label, mesh, key) in enumerate(self.candidates):
                if topology(mesh) == self.morphs[index].counts:
                    self.source.addItem(label, i)
                    if key == self.preferred:
                        self.source.setCurrentIndex(self.source.count() - 1)
        self.source.blockSignals(False)
        self.change_source()

    def change_source(self):
        self.update_pose(reset=True)

    def update_pose(self, value=None, reset=False):
        self.weight_label.setText(f'{self.weight.value() / 4096:.0%}')
        i = self.source.currentData()
        enabled = i is not None
        self.weight.setEnabled(enabled)
        self.play.setEnabled(enabled)
        if not enabled:
            self.set_data([], self.vram, 0x5080)
            self.notice.setText('No WMD with matching polygon batches is loaded in this area and section.')
            return
        label, mesh, key = self.candidates[i]
        changed = deform(mesh, self.morphs[self.pose.currentIndex()], self.weight.value())
        if reset:
            self.set_data([changed], self.vram, 0x5080, {0: label})
        else:
            self.canvas.meshes = [changed]
            self.canvas.selected = None
            self.canvas.update()
        self.notice.setText('Source link verified in AREA00 code.' if key == self.preferred else
                            'Compatible polygon batches. Choose the source model; this link is not verified by game code.')

    def toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play.setText('Play')
        else:
            self.timer.start()
            self.play.setText('Stop')

    def advance(self):
        value = self.weight.value() + self.direction * 96
        if value >= 4096 or value <= 0:
            self.direction *= -1
        self.weight.setValue(max(0, min(4096, value)))

    def hideEvent(self, event):
        self.timer.stop()
        self.play.setText('Play')
        super().hideEvent(event)
