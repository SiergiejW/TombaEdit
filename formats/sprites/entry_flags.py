"""Per-entry checkboxes saved independently of the bank review."""
from PyQt6.QtCore import QObject, Qt, QSignalBlocker, QEvent
from PyQt6.QtWidgets import QTableWidgetItem, QStyleOptionViewItem, QStyle
from game.sprite_checks import entry_target


class EntryFlags(QObject):
    def __init__(self, table, column, review_bar, kind):
        super().__init__(table)
        self.table, self.column, self.bar, self.kind = table, column, review_bar, kind
        self.checked = set()
        self.consume_release = False
        table.itemChanged.connect(self.changed)
        table.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonRelease and self.consume_release:
            self.consume_release = False
            return True
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            point = event.position().toPoint()
            index = self.table.indexAt(point)
            selected = {row.row() for row in self.table.selectionModel().selectedRows()}
            if index.isValid() and index.column() == self.column and index.row() in selected:
                option = QStyleOptionViewItem()
                option.initFrom(self.table)
                self.table.itemDelegate().initStyleOption(option, index)
                option.rect = self.table.visualRect(index)
                indicator = self.table.style().subElementRect(
                    QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, self.table)
                if indicator.contains(point):
                    # Handle the checkbox before Qt collapses a multi-row selection.
                    item = self.table.item(index.row(), self.column)
                    self.consume_release = True
                    item.setCheckState(Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked
                                       else Qt.CheckState.Checked)
                    return True
        return super().eventFilter(watched, event)

    def fill(self, entries):
        """Read once per list rebuild, never once per sprite."""
        try:
            self.checked = {e['id'] for e in self.bar.store.document()['entries'] if e.get('status') == 'looks_off'}
        except (OSError, ValueError, TypeError) as exc:
            self.bar.error(exc)
            return
        with QSignalBlocker(self.table):
            for row, identity in enumerate(entries):
                target = entry_target(self.bar.target, self.kind, identity)
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, identity)
                item.setToolTip('Looks off. Checking or unchecking applies to all selected rows and saves immediately.')
                item.setCheckState(Qt.CheckState.Checked if target['id'] in self.checked else Qt.CheckState.Unchecked)
                self.table.setItem(row, self.column, item)

    def changed(self, item):
        if item.column() != self.column:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        if item.row() not in rows:
            rows = {item.row()}
        changes = []
        for row in sorted(rows):
            checkbox = self.table.item(row, self.column)
            if checkbox is None:
                continue
            identity = checkbox.data(Qt.ItemDataRole.UserRole)
            target = entry_target(self.bar.target, self.kind, identity)
            if checked != (target['id'] in self.checked):
                changes.append((checkbox, target, identity))
        if not changes:
            return
        try:
            self.bar.store.set_many([target for _, target, _ in changes], 'looks_off' if checked else None,
                                    preview=dict(self.bar.preview(), looks_off=checked))
        except (OSError, ValueError, TypeError) as exc:
            with QSignalBlocker(self.table):
                for checkbox, target, _ in changes:
                    checkbox.setCheckState(Qt.CheckState.Checked if target['id'] in self.checked
                                           else Qt.CheckState.Unchecked)
            self.bar.error(exc)
            return
        with QSignalBlocker(self.table):
            for checkbox, target, _ in changes:
                checkbox.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                if checked:
                    self.checked.add(target['id'])
                else:
                    self.checked.discard(target['id'])
        bank = self.bar.target
        identities = ', '.join(f'{identity:02X}' if isinstance(identity, int) else str(identity)
                               for _, _, identity in changes)
        print(f"{'ANIM' if self.kind == 'animation' else 'SPR'} entries {identities} | Looks off: "
              f"{'checked' if checked else 'cleared'} | {bank.get('type', 'SPR')} | "
              f"{bank.get('source', '')} +0x{bank.get('offset', 0):06X} | "
              f"{bank.get('ldar', '')} group {bank.get('group', '')} | "
              f"VRAM context {bank.get('vram_context')} | ROM {bank.get('rom', '')} | "
              f"JSON: {self.bar.store.path}", flush=True)
        self.bar.review_changed.emit()
