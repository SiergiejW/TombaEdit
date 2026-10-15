"""Busy overlay that leaves the current viewer in place."""
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import QWidget, QFrame, QVBoxLayout, QLabel, QProgressBar


class LoadingOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        parent.installEventFilter(self)
        layout = QVBoxLayout(self)
        panel = QFrame()
        panel.setFixedWidth(440)
        panel.setStyleSheet('QFrame { background: transparent; border: none; }'
                            'QProgressBar { background: #292329; border: none; height: 22px; }'
                            'QProgressBar::chunk { background: #ef63a6; }')
        body = QVBoxLayout(panel)
        body.setContentsMargins(24, 20, 24, 24)
        self.message = QLabel('LOADING...')
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.message.font()
        font.setBold(True)
        font.setPointSize(12)
        self.message.setFont(font)
        self.message.setWordWrap(True)
        body.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        body.addWidget(self.progress)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def begin(self, message):
        self.message.setStyleSheet('color: ' + self.parentWidget().palette().color(QPalette.ColorRole.Text).name())
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
        return False

