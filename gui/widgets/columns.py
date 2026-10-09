"""Columns of a list that can be dragged wider or narrower."""
from PyQt6.QtWidgets import QHeaderView


def adjustable(table, fit=False, padding=14):
    """Let every column of `table` be resized by hand, the last one taking
    the room that is left. `fit` first sizes the columns to what they hold."""
    header = table.horizontalHeader()
    if fit:
        table.resizeColumnsToContents()
        for column in range(table.columnCount() - 1):
            table.setColumnWidth(column, table.columnWidth(column) + padding)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    header.setStretchLastSection(True)
