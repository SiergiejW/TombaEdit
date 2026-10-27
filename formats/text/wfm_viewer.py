"""Viewers for a WFM bank: its entries, and the glyphs of its font."""
from pathlib import Path
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QListWidget,
    QFileDialog, QMessageBox, QLineEdit, QTableWidget, QTableWidgetItem, QAbstractItemView, QInputDialog,
    QMenu, QComboBox)
from gui.widgets.image_view import ImageView, text_view, qimage, file_stem
from gui.widgets.columns import adjustable
from formats.text import wfm as wfm_module
from formats.text import export
from formats.text import usage
from gui.widgets.text_usage import TextEntryDelegate, UNUSED_ROLE, purple
from PyQt6.QtGui import QBrush


class DialogueView(QWidget):
    def __init__(self, wfm, name='dialogue', source='', offset=0, translation_session=None):
        super().__init__()
        self.wfm = wfm
        self.bank = export.Bank(name, source, offset, version=wfm.version.decode('ascii', 'replace'), wfm=wfm)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText('Search dialogue...')
        self.search.textChanged.connect(self.filter)
        bar.addWidget(self.search)
        self.usage_filter = QComboBox()
        for label, status in [('All entries', ''), ('No in-game use found', 'not_found'),
                              ('Display references', 'referenced'), ('Dynamic selection', 'dynamic'),
                              ('Usage not checked', 'unknown')]:
            self.usage_filter.addItem(label, status)
        self.usage_filter.setToolTip('Filter by native text-display evidence. No use found means an unused candidate.')
        self.usage_filter.currentIndexChanged.connect(lambda: self.filter(self.search.text()))
        bar.addWidget(self.usage_filter)
        save = QPushButton('Export text...')
        save.setToolTip('Write this bank\'s entries to a file: with their control codes, as plain text, '
                        'as JSON with the raw words, or as a table.')
        save.clicked.connect(self.export_text)
        bar.addWidget(save)
        translated = QPushButton('Export translations...')
        translated_menu = QMenu(translated)
        translated_menu.addAction('This WFM bank...', lambda: self.export_translations(False))
        self.export_all_translations = translated_menu.addAction('All WFM banks...', lambda: self.export_translations(True))
        translated.setMenu(translated_menu)
        bar.addWidget(translated)
        layout.addLayout(bar)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        split = QSplitter()
        self.entries = QListWidget()
        self.entries.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.entries.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.entries.setItemDelegate(TextEntryDelegate(self.entries))
        split.addWidget(self.entries)
        right = QSplitter(Qt.Orientation.Vertical)
        self.rendered = ImageView()
        self.script = text_view("")
        right.addWidget(self.rendered)
        right.addWidget(self.script)
        right.setSizes([400, 160])
        split.addWidget(right)
        from formats.text.translation_view import TranslationPane
        self.translation = TranslationPane(translation_session)
        self.translation.session.changed.connect(self.refresh_translations)
        split.addWidget(self.translation)
        split.setSizes([260, 550, 350])
        layout.addWidget(split, 1)
        layout.addWidget(QLabel("Glyph IDs are font-local, not ASCII. Control words are preserved below the preview."))
        self.entries.currentRowChanged.connect(self.select)
        self.relist()
        if wfm.dialogues:
            self.entries.setCurrentRow(0)

    def relist(self):
        """Fill the list of entries from the characters as they are known now."""
        wfm, row = self.wfm, self.entries.currentRow()
        self.entries.blockSignals(True)
        self.entries.clear()
        for i, d in enumerate(wfm.dialogues):
            preview = export.plain(d).replace('\n', ' ')
            self.entries.addItem(f'{getattr(d, "name", f"{i:03d}")} | {preview}')
        self.entries.blockSignals(False)
        self.translation.session.register(self.bank)
        self.refresh_translations()
        known = sum(c is not None for c in wfm.characters)
        candidates = sum((usage.entry(d) or {}).get('status') == 'not_found' for d in wfm.dialogues)
        audited = any(usage.entry(d) for d in wfm.dialogues)
        recovered = len(getattr(wfm, 'recovered_glyphs', {}))
        self.summary.setText(f'{len(wfm.dialogues)} entries | {known}/{len(wfm.glyphs)} decoded glyphs'
                             + (f' ({recovered} reconstructed readings)' if recovered else '') + ' | '
                             + (f'{candidates} with no in-game use found' if audited else 'In-game usage not checked'))
        self.summary.setToolTip(getattr(wfm, 'usage_summary', 'Native display analysis is not available for this build.'))
        if row >= 0:
            self.entries.setCurrentRow(row)
        self.filter(self.search.text())

    def select(self, index):
        if index < 0:
            return
        try:
            self.rendered.set_image(self.wfm.render(index))
            self.script.setPlainText(self.wfm.dialogues[index].script())
            dialogue = self.wfm.dialogues[index]
            self.translation.set_text(export.plain(dialogue), dialogue.warning)
        except ValueError as exc:
            self.script.setPlainText(str(exc))
            self.translation.set_text('')

    def filter(self, text):
        for i, dialogue in enumerate(self.wfm.dialogues):
            translated = self.translation.session.lookup(export.plain(dialogue)) or ''
            wanted = self.usage_filter.currentData()
            status = (usage.entry(dialogue) or {}).get('status', 'unknown')
            self.entries.item(i).setHidden((bool(wanted) and status != wanted)
                or text.casefold() not in (dialogue.script() + '\n' + translated).casefold())

    def refresh_translations(self):
        session = self.translation.session
        self.export_all_translations.setEnabled(session.project is None or session.discovered)
        for i, dialogue in enumerate(self.wfm.dialogues):
            original = export.plain(dialogue)
            preview = self.translation.session.lookup(original)
            preview = (preview if preview is not None else original).replace('\n', ' ')
            item = self.entries.item(i)
            if item is not None:
                marker = '[No in-game use found] ' if (usage.entry(dialogue) or {}).get('status') == 'not_found' else ''
                item.setData(UNUSED_ROLE, bool(marker))
                item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(purple(self.entries.palette())) if marker else None)
                item.setText(f'{getattr(dialogue, "name", f"{i:03d}")} | {marker}{preview}')
                item.setToolTip(usage.explanation(dialogue) + '\n\n' + original)
        self.filter(self.search.text())

    def export_translations(self, all_banks=False):
        session = self.translation.session
        banks = list(session.banks.values()) if all_banks else [self.bank]
        path, chosen = QFileDialog.getSaveFileName(self, 'Export English and original text',
            file_stem(self.bank.name, 'dialogue') + '-translated.json',
            'JSON with English and originals (*.json);;English and original text (*.txt)')
        if path:
            try:
                Path(path).write_text(export.render_translated(banks, session.translations,
                    session.folder, 'json' if 'JSON' in chosen else 'plain'), encoding='utf8')
            except OSError as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))

    def export_text(self):
        filters = {f'{label} (*{suffix})': kind for kind, (label, suffix) in export.FORMATS.items()}
        path, chosen = QFileDialog.getSaveFileName(self, 'Export text', file_stem(self.bank.name, 'dialogue') + '.txt',
                                                   ';;'.join(filters), 'Script with control codes (*.txt)')
        if path:
            try:
                export.write([self.bank], path, filters.get(chosen, 'script'), raw=True)
            except OSError as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))


class GlyphView(QWidget):
    """The font of a bank, glyph by glyph, with the character each is read
    as. A character can be typed for one glyph or for several at once."""
    changed = pyqtSignal()

    def __init__(self, wfm):
        super().__init__()
        self.wfm = wfm
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.only_unknown = QPushButton('Unknown only')
        self.only_unknown.setCheckable(True)
        self.only_unknown.toggled.connect(self.refill)
        bar.addWidget(self.only_unknown)
        name = QPushButton('Set character...')
        name.setToolTip('Type the character the selected glyphs stand for. It is remembered for every '
                        'glyph of the same shape, in this bank and in the others.')
        name.clicked.connect(self.rename)
        bar.addWidget(name)
        sheet = QPushButton('Save glyph sheet...')
        sheet.clicked.connect(self.save_sheet)
        bar.addWidget(sheet)
        self.summary = QLabel()
        bar.addWidget(self.summary, 1)
        layout.addLayout(bar)
        split = QSplitter()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Glyph', 'ID', 'Size', 'Used', 'Character'])
        self.table.verticalHeader().hide()
        self.table.setIconSize(QSize(48, 48))
        self.table.verticalHeader().setDefaultSectionSize(54)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for column, width in enumerate((70, 60, 76, 64, 120)):
            self.table.setColumnWidth(column, width)
        adjustable(self.table)
        self.table.cellDoubleClicked.connect(lambda row, column: self.rename())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.menu)
        split.addWidget(self.table)
        self.atlas = ImageView()
        split.addWidget(self.atlas)
        split.setSizes([430, 560])
        layout.addWidget(split, 1)
        self.used = {}
        for dialogue in wfm.dialogues:
            for word, _ in dialogue.tokens:
                if word < 0xFF00 and not word & 0x4000:
                    self.used[word & 0xFFF] = self.used.get(word & 0xFFF, 0) + 1
        self.rows = []
        self.refill()
        self.atlas.set_image(wfm.atlas())

    def refill(self, *_):
        wfm = self.wfm
        self.rows = [i for i, c in enumerate(wfm.characters) if c is None or not self.only_unknown.isChecked()]
        self.table.setRowCount(len(self.rows))
        for row, number in enumerate(self.rows):
            image = wfm.glyphs[number]
            icon = QTableWidgetItem()
            scale = max(1, 48 // max(image.size))
            icon.setIcon(QIcon(QPixmap.fromImage(qimage(image)).scaled(
                image.width * scale, image.height * scale, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation)))
            values = [icon, f'{number:03X}', f'{image.width} x {image.height}', str(self.used.get(number, 0)),
                      wfm.characters[number] or '']
            for column, value in enumerate(values):
                self.table.setItem(row, column, value if column == 0 else QTableWidgetItem(value))
            recovered = getattr(wfm, 'recovered_glyphs', {}).get(number)
            if recovered:
                self.table.item(row, 4).setToolTip(recovered['evidence'])
        known = sum(c is not None for c in wfm.characters)
        self.summary.setText(f'{known} of {len(wfm.glyphs)} glyphs have a character')
        recovered = len(getattr(wfm, 'recovered_glyphs', {}))
        if recovered:
            self.summary.setText(self.summary.text() + f' | {recovered} reconstructed readings; artwork absent')

    def selected(self):
        return [self.rows[row] for row in sorted({item.row() for item in self.table.selectedItems()})]

    def menu(self, point):
        numbers = self.selected()
        if not numbers:
            return
        menu = QMenu(self)
        name = menu.addAction('Set character...' if len(numbers) == 1 else f'Set character of {len(numbers)} glyphs...')
        clear = menu.addAction('Forget character')
        chosen = menu.exec(self.table.viewport().mapToGlobal(point))
        if chosen is name:
            self.rename()
        elif chosen is clear:
            self.assign(numbers, None)

    def rename(self):
        numbers = self.selected()
        if not numbers:
            return
        old = {self.wfm.characters[n] or '' for n in numbers}
        text, accepted = QInputDialog.getText(
            self, 'Glyph character', 'Character or characters this glyph stands for (empty: none):',
            text=old.pop() if len(old) == 1 else '')
        if accepted:
            self.assign(numbers, text)

    def assign(self, numbers, text):
        """Give the glyphs a character; None goes back to the built-in one."""
        for number in numbers:
            key = self.wfm.keys[number]
            if not key:
                continue
            if text is None:
                wfm_module.USER_GLYPHS.pop(key, None)
            else:
                wfm_module.USER_GLYPHS[key] = text
        self.wfm.recognise()
        self.refill()
        self.changed.emit()

    def save_sheet(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save glyph sheet', 'glyphs.png', 'PNG (*.png)')
        if path:
            try:
                self.wfm.atlas().save(path)
            except OSError as exc:
                QMessageBox.warning(self, 'Not saved', str(exc))
