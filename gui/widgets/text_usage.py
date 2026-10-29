"""Purple unused-text entries and a separately coloured tree count."""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QPalette, QTextLayout, QTextCharFormat
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QApplication
from gui.widgets.columns import ViewportElideDelegate

COUNT_ROLE = Qt.ItemDataRole.UserRole + 50
UNUSED_ROLE = Qt.ItemDataRole.UserRole + 51
UNCHECKED_ROLE = Qt.ItemDataRole.UserRole + 52
USAGE_TOOLTIP_ROLE = Qt.ItemDataRole.UserRole + 53


def purple(palette, selected=False):
    background = QPalette.ColorRole.Highlight if selected else QPalette.ColorRole.Base
    return QColor('#bc80ed' if palette.color(background).lightness() < 128 else '#8535b1')


def blue(palette):
    """The colour of a section that has cut content, readable on a dark or a light tree."""
    return QColor('#5aa2ff' if palette.color(QPalette.ColorRole.Base).lightness() < 128 else '#1c5fcf')


class TextEntryDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.data(UNUSED_ROLE):
            color = purple(option.palette, bool(option.state & QStyle.StateFlag.State_Selected))
            option.palette.setColor(QPalette.ColorRole.Text, color)
            option.palette.setColor(QPalette.ColorRole.HighlightedText, color)


class UsageTreeDelegate(ViewportElideDelegate):
    def paint(self, painter, option, index):
        count = index.data(COUNT_ROLE) if index.column() == 0 else 0
        unchecked = index.data(UNCHECKED_ROLE) if index.column() == 0 else False
        if not count and not unchecked:
            return super().paint(painter, option, index)
        visible = QStyleOptionViewItem(option)
        self.initStyleOption(visible, index)
        visible.rect.setRight(min(visible.rect.right(), self.parent().viewport().rect().right()))
        if visible.rect.width() <= 0:
            return
        suffix = f' ({count} possibly unused)' if count else ' (usage not checked)'
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
        accent.setForeground(purple(visible.palette, bool(visible.state & QStyle.StateFlag.State_Selected))
                             if count else visible.palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text))
        span = QTextLayout.FormatRange()
        span.start, span.length, span.format = len(base.encode('utf-16-le')) // 2, len(suffix), accent
        layout.setFormats([span])
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(max(rect.width(), visible.fontMetrics.horizontalAdvance(text)))
        layout.endLayout()
        layout.draw(painter, QPointF(rect.x(), rect.y() + (rect.height() - line.height()) / 2))
        painter.restore()
