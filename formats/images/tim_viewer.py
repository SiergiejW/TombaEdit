"""TIM pictures with their palettes."""
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QCheckBox
from PIL import Image
from gui.widgets.image_view import ImageView


class TimView(QWidget):
    """One TIM. An indexed picture can be shown through any palette its
    file holds; the transparent colour can be filled in to see the whole
    rectangle."""

    def __init__(self, tim=None):
        super().__init__()
        self.tim = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.setContentsMargins(8, 6, 8, 0)
        self.palette_label = QLabel('Palette')
        self.palette = QSpinBox()
        self.palette.valueChanged.connect(self.refresh)
        self.opaque = QCheckBox('Show transparent colour')
        self.opaque.setToolTip('Colour word 0 is not drawn by the console. Tick to see it as black.')
        self.opaque.toggled.connect(self.refresh)
        self.info = QLabel()
        for widget in (self.palette_label, self.palette, self.opaque):
            bar.addWidget(widget)
        bar.addSpacing(12)
        bar.addWidget(self.info, 1)
        layout.addLayout(bar)
        self.image = ImageView()
        layout.addWidget(self.image, 1)
        if tim is not None:
            self.set_tim(tim)

    @property
    def export_name(self):
        return self.image.export_name

    @export_name.setter
    def export_name(self, value):
        self.image.export_name = value

    def set_tim(self, tim, keep_view=False):
        self.tim = tim
        count = len(tim.palettes)
        self.palette.blockSignals(True)
        self.palette.setRange(0, max(0, count - 1))
        self.palette.setValue(0)
        self.palette.blockSignals(False)
        self.palette.setVisible(count > 1)
        self.palette_label.setVisible(count > 1)
        self.palette.setSuffix(f' of {count}')
        self.info.setText(tim.describe())
        if self.image.zoom.currentIndex() and max(tim.width, tim.height) > 400:
            self.image.zoom.setCurrentIndex(0 if max(tim.width, tim.height) > 640 else 1)
        self.refresh(keep_view=keep_view)

    def refresh(self, *_, keep_view=False):
        if self.tim is None:
            return
        picture = self.tim.image(self.palette.value())
        if self.opaque.isChecked():
            filled = Image.new('RGBA', picture.size, (0, 0, 0, 255))
            filled.alpha_composite(picture)
            picture = filled
        self.image.set_image(picture, preserve_view=keep_view)
