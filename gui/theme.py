"""Classic themes ported from Tomba2Edit. Native dark, explicit bright."""
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication
_native_palette = None
_current_theme = "dark"
_BASE_QSS = """
QMenuBar::item {
    background-color: transparent;
    padding: 4px 6px;
    margin: 0px;
}
QMenuBar::item:selected, QMenuBar::item:pressed {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
QToolBar#viewerToolbar QToolButton {
    background-color: rgba(255, 255, 255, 128);
    color: black;
    border: none;
    padding: 5px;
    margin: 2px;
    border-radius: 4px;
}
QToolBar#viewerToolbar QToolButton:hover {
    background-color: rgba(255, 255, 255, 180);
}
QLabel#viewerOverlay {
    background-color: rgba(0, 0, 0, 128);
    color: white;
    padding: 4px 6px;
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 11px;
}
QLabel#panelTitle {
    color: #b8b8b8;
    font-size: 11px;
    padding: 2px 4px;
}
"""

_BRIGHT_MENU_QSS = _BASE_QSS + """
QMenu {
    background-color: #ffffff;
    color: #202020;
}
QMenu::item:selected {
    background-color: #3399ff;
    color: #ffffff;
}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {
    background-color: #3399ff;
    color: #ffffff;
}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {
    background-color: #f0f0f2;
}
"""

def _bright_palette():
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#f0f0f0"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#202020"))
    p.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f0f0"))
    p.setColor(QPalette.ColorRole.Text, QColor("#202020"))
    p.setColor(QPalette.ColorRole.Button, QColor("#f0f0f0"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#202020"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#202020"))
    p.setColor(QPalette.ColorRole.Highlight, QColor("#3399ff"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return p

def apply_theme(dark=True):
    global _native_palette, _current_theme
    app = QApplication.instance()
    if _native_palette is None:
        _native_palette = QPalette(app.palette())
    _current_theme = "dark" if dark else "bright"
    app.setPalette(_native_palette if dark else _bright_palette())
    app.setStyleSheet(_BASE_QSS if dark else _BRIGHT_MENU_QSS)
    for widget in app.allWidgets():
        widget.update()

def view_background(dark=(0.1, 0.1, 0.1)):
    return (0.82, 0.83, 0.85) if _current_theme == "bright" else dark
