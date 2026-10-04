"""Clickable PCM waveform used by sound previews."""
import io
import wave
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget


class WavePreview(QWidget):
    scrubbed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(48)
        self.setMaximumHeight(72)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.envelope = None
        self.position = 0.

    def set_wav(self, data):
        try:
            with wave.open(io.BytesIO(data), 'rb') as source:
                channels = source.getnchannels()
                pcm = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
            if channels > 1:
                pcm = pcm[:len(pcm)//channels*channels].reshape(-1, channels)
                low, high = pcm.min(axis=1), pcm.max(axis=1)
            else:
                low = high = pcm
            count = min(1024, len(low))
            if count:
                end = len(low)//count*count
                self.envelope = np.stack((low[:end].reshape(count, -1).min(axis=1),
                                          high[:end].reshape(count, -1).max(axis=1)), axis=1) / 32768.
            else:
                self.envelope = None
        except (EOFError, wave.Error, ValueError):
            self.envelope = None
        self.position = 0.
        self.update()

    def set_position(self, fraction):
        self.position = max(0., min(1., float(fraction)))
        self.update()

    def mousePressEvent(self, event):
        if self.envelope is not None:
            self.position = max(0., min(1., event.position().x()/max(1, self.width())))
            self.scrubbed.emit(self.position)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        dark = QApplication.palette().window().color().lightness() < 128
        painter.fillRect(self.rect(), QColor('#181818' if dark else '#eeeeee'))
        if self.envelope is None:
            painter.setPen(QColor('#888888'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Select a sample')
            return
        mid = self.height()/2
        half = max(1, mid-3)
        cursor = int(self.width()*self.position)
        for x in range(self.width()):
            first = x*len(self.envelope)//max(1,self.width())
            last = max(first+1, (x+1)*len(self.envelope)//max(1,self.width()))
            block = self.envelope[first:last]
            if not len(block):
                continue
            painter.setPen(QPen(QColor('#72b3d5' if x < cursor else '#777777')))
            painter.drawLine(x, int(mid-block[:,1].max()*half),
                             x, int(mid-block[:,0].min()*half))
        painter.setPen(QPen(QColor('#f0c04a')))
        painter.drawLine(cursor, 0, cursor, self.height())
