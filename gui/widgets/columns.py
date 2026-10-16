"""Columns of a list that can be dragged wider or narrower."""
from PyQt6.QtWidgets import QHeaderView, QStyledItemDelegate, QStyleOptionViewItem
from PyQt6.QtCore import Qt, QTimer


class ViewportElideDelegate(QStyledItemDelegate):
    """Show an ellipsis when a wide cell reaches the visible pane edge."""
    def paint(self, painter, option, index):
        visible = QStyleOptionViewItem(option)
        visible.rect.setRight(min(visible.rect.right(), self.parent().viewport().rect().right()))
        visible.textElideMode = Qt.TextElideMode.ElideRight
        if visible.rect.width() > 0:
            super().paint(painter, visible, index)


def elide_at_view_edge(view):
    view.setTextElideMode(Qt.TextElideMode.ElideRight)
    view.setItemDelegate(ViewportElideDelegate(view))


def adjustable(table, fit=False, padding=14):
    """Let every column of `table` be resized by hand, the last one taking
    the room that is left. `fit` first sizes the columns to what they hold."""
    header = table.horizontalHeader()
    elide_at_view_edge(table)
    for column in range(table.columnCount()):
        item = table.horizontalHeaderItem(column)
        if item is not None and item.text().casefold() == 'label':
            header.moveSection(header.visualIndex(column), 1)
            break
    if fit:
        table.resizeColumnsToContents()
        for column in range(table.columnCount() - 1):
            table.setColumnWidth(column, table.columnWidth(column) + padding)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
    # Populate calls often follow this setup. Coalesce them into one fit,
    # including later label changes and animations loaded on first display.
    if not hasattr(table, '_text_column_fit'):
        timer = table._text_column_fit = QTimer(table)
        timer.setSingleShot(True)
        timer.setInterval(80)
        def fit_text():
            table.resizeColumnsToContents()
            for column in range(table.columnCount()):
                table.setColumnWidth(column, table.columnWidth(column) + padding)
        timer.timeout.connect(fit_text)
        for signal in (table.model().dataChanged, table.model().rowsInserted, table.model().modelReset):
            signal.connect(lambda *args: timer.start())
        timer.start()
