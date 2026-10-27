"""Purple unused-text entries and a separately coloured tree count."""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPalette, QTextLayout, QTextCharFormat
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
from gui.widgets.columns import ViewportElideDelegate

COUNT_ROLE = Qt.ItemDataRole.UserRole + 50
UNUSED_ROLE = Qt.ItemDataRole.UserRole + 51


def purple(palette):
    return QColor('#bc80ed' if palette.color(QPalette.ColorRole.Base).lightness() < 128 else '#8535b1')


class TextEntryDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(UNUSED_ROLE):
            color = purple(option.palette)
            option.palette.setColor(QPalette.ColorRole.Text, color)
            option.palette.setColor(QPalette.ColorRole.HighlightedText, color)


class UsageTreeDelegate(ViewportElideDelegate):
    def paint(self, painter, option, index):
        count = index.data(COUNT_ROLE) if index.column() == 0 else 0
        if not count:
            return super().paint(painter, option, index)
        visible = QStyleOptionViewItem(option)
        self.initStyleOption(visible, index)
        visible.rect.setRight(min(visible.rect.right(), self.parent().viewport().rect().right()))
        if visible.rect.width() <= 0:
            return
        suffix = f' ({count} unused)'
        base = visible.text.removesuffix(suffix)
        style = visible.widget.style() if visible.widget else QApplication.style()
        rect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, visible, visible.widget)
        # Keep the count visible when a long file name reaches the pane edge.
        base = visible.fontMetrics.elidedText(base, Qt.TextElideMode.ElideRight,
                    max(0, rect.width() - visible.fontMetrics.horizontalAdvance(suffix)))
        text = base + suffix
        visible.text = ''
        painter.save()
        painter.setClipRect(visible.rect)
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, visible, painter, visible.widget)
        color = visible.palette.color(QPalette.ColorRole.HighlightedText
            if visible.state & QStyle.StateFlag.State_Selected else QPalette.ColorRole.Text)
        painter.setPen(color)
        layout = QTextLayout(text, visible.font)
        accent = QTextCharFormat()
        accent.setForeground(purple(visible.palette))
        span = QTextLayout.FormatRange()
        span.start, span.length, span.format = len(base), len(suffix), accent
        layout.setFormats([span])
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(max(rect.width(), visible.fontMetrics.horizontalAdvance(text)))
        layout.endLayout()
        layout.draw(painter, QPointF(rect.x(), rect.y() + (rect.height() - line.height()) / 2))
        painter.restore()
