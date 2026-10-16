"""A status list that immediately updates the whole-SPR JSON entry."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QMessageBox, QSizePolicy
from game.sprite_checks import default_store, review_statuses


class SpriteCheckBar(QWidget):
    review_changed = pyqtSignal()

    def __init__(self, target, preview, parent=None, store=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.target, self.preview = target, preview
        self.status_names = review_statuses(target.get('review_kind', 'spr'))
        self.store = store or default_store()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        animation = target.get('review_kind') == 'anim'
        layout.addWidget(QLabel('Check animations:' if animation else 'Check whole SPR:'))
        self.status = QComboBox()
        self.status.addItem('Not checked', None)
        for value, title in self.status_names.items():
            self.status.addItem(title, value)
        self.status.setToolTip('Choosing a status replaces this SPR entry in the JSON.\n'
                               'JSON file: ' + str(self.store.path))
        layout.addWidget(self.status)
        layout.addStretch()
        self.refresh()
        self.status.activated.connect(self.mark)

    def error(self, exc):
        QMessageBox.warning(self, 'Sprite checks', str(exc))

    def refresh(self):
        try:
            entry = self.store.get(self.target['id']) or {}
            index = self.status.findData(entry.get('status'))
            self.status.setCurrentIndex(max(0, index))
        except (OSError, ValueError, TypeError) as exc:
            self.error(exc)

    def mark(self, index):
        try:
            status = self.status.itemData(index)
            self.store.set(self.target, status, preview=self.preview())
            target = self.target
            kind = 'ANIM' if target.get('review_kind') == 'anim' else 'SPR'
            print(f"{kind} review {'saved' if status else 'cleared'}: "
                  f"{self.status_names.get(status, 'Not checked')} | "
                  f"{target.get('type', 'SPR')} | {target.get('source', '')} "
                  f"+0x{target.get('offset', 0):06X} | {target.get('ldar', '')} "
                  f"group {target.get('group', '')} | VRAM context {target.get('vram_context')} | "
                  f"ROM {target.get('rom', '')} | JSON: {self.store.path}", flush=True)
            self.review_changed.emit()
        except (OSError, ValueError, TypeError) as exc:
            self.error(exc)
        self.refresh()
