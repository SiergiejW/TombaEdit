"""Zoom in, zoom out and reset buttons stacked at the top right of a 2D view.

    ZoomButtons(host, zoom_in, zoom_out, reset)

`host` is the widget the buttons float over; they stay at its top right corner
as it resizes. The three callables take no arguments. `reset` is what the view
calls "fit". The buttons never take keyboard focus, so a view's own keys keep
working after one is clicked, and they repeat while held.
"""
from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QToolButton, QVBoxLayout, QWidget

MARGIN = 6
SIZE = 26


class ZoomButtons(QWidget):
    def __init__(self, host, zoom_in, zoom_out, reset):
        super().__init__(host)
        self.host = host
        self.setObjectName('zoomButtons')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        for text, tip, action, repeat in (('+', 'Zoom in', zoom_in, True), ('−', 'Zoom out', zoom_out, True),
                                          ('Fit', 'Reset the zoom: fit the whole picture', reset, False)):
            button = QToolButton(self)
            button.setText(text)
            button.setToolTip(tip)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setAutoRepeat(repeat)
            button.setAutoRepeatInterval(60)
            button.setFixedSize(SIZE + (10 if text == 'Fit' else 0), SIZE)
            button.clicked.connect(lambda _checked=False, act=action: act())
            layout.addWidget(button)
        self.adjustSize()
        host.installEventFilter(self)
        self.place()
        self.raise_()

    def place(self):
        self.move(max(0, self.host.width() - self.width() - MARGIN), MARGIN)
        self.raise_()

    def eventFilter(self, watched: QObject, event):
        if watched is self.host and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.place()
        return False
