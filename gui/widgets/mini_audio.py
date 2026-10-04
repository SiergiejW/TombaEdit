"""Small waveform and note previews for audio list entries."""
import numpy as np
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def waveform_icon(samples, width=112, height=24):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor('#202020'))
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor('#a7c653')))
    values = np.asarray(samples, dtype=np.float32)
    if len(values):
        peak = max(1, float(np.max(np.abs(values))))
        for x in range(width):
            part = values[x * len(values) // width:max(x * len(values) // width + 1,
                (x + 1) * len(values) // width)]
            if len(part):
                mid = height // 2
                painter.drawLine(x, round(mid - float(part.max()) / peak * (mid - 2)),
                                 x, round(mid - float(part.min()) / peak * (mid - 2)))
    painter.end()
    return QIcon(pixmap)


def notes_icon(events, width=112, height=24):
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor('#202020'))
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor('#a7c653'), 2))
    ticks = sum(event[0] for event in events)
    at = 0
    notes = []
    for delta, status, key, velocity in events:
        at += delta
        if status & 0xF0 == 0x90 and velocity:
            notes.append((at, key))
    if ticks:
        for tick, key in notes:
            x = min(width - 2, int(tick / ticks * (width - 1)))
            y = height - 3 - int(max(0, min(127, key)) / 127 * (height - 6))
            painter.drawLine(x, y, min(width - 1, x + 3), y)
    painter.end()
    return QIcon(pixmap)
