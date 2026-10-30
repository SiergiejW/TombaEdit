"""Viewers for a WFM bank: its entries, and the glyphs of its font."""
from pathlib import Path
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSplitter, QListWidget,
    QFileDialog, QMessageBox, QLineEdit, QTableWidget, QTableWidgetItem, QAbstractItemView, QInputDialog,
    QMenu, QComboBox, QCheckBox)
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
        if translation_session is not None and translation_session.project is not None:
            usage.attach(wfm, translation_session.project, source, offset)
        self.bank = export.Bank(name, source, offset, version=wfm.version.decode('ascii', 'replace'), wfm=wfm)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        tools = QHBoxLayout()       # the filter and the buttons: shown above the picture
        self.search = QLineEdit(); self.search.setPlaceholderText('Search dialogue...')
        self.search.textChanged.connect(self.filter)
        bar.addWidget(self.search)
        self.usage_filter = QComboBox()
        for label, status in [('All entries', ''), ('Possibly unused', 'not_found'),
                              ('Display references', 'referenced'), ('Dynamic selection', 'dynamic'),
                              ('Usage not checked', 'unknown')]:
            self.usage_filter.addItem(label, status)
        self.usage_filter.setToolTip('Filter by native text-display evidence. Possibly unused is not proof that an entry is unreachable.')
        self.usage_filter.currentIndexChanged.connect(lambda: self.filter(self.search.text()))
        tools.addWidget(self.usage_filter)
        save = QPushButton('Export text...')
        save.setToolTip('Write this bank\'s entries to a file: with their control codes, as plain text, '
                        'as JSON with the raw words, or as a table.')
        original_menu = QMenu(save)
        original_menu.addAction('This WFM bank...', lambda: self.export_text(False))
        self.export_all_originals = original_menu.addAction('All WFM banks...', lambda: self.export_text(True))
        save.setMenu(original_menu)
        tools.addWidget(save)
        search_all = QPushButton('Search for text...')
        search_all.setToolTip('Search phrases across every WFM bank on this disc.')
        search_all.clicked.connect(self.search_all_text)
        tools.addWidget(search_all)
        translated = QPushButton('Export translations...')
        translated_menu = QMenu(translated)
        translated_menu.addAction('This WFM bank...', lambda: self.export_translations(False))
        self.export_all_translations = translated_menu.addAction('All WFM banks...', lambda: self.export_translations(True))
        translated.setMenu(translated_menu)
        tools.addWidget(translated)
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
        # The message as the game draws it, in its own font, with the English under it in the fallback letters,
        # in one frame that grows taller for a longer text. The Display menu picks what is shown.
        self.rendered = ImageView()
        self._display_key = None
        self.script = text_view("")
        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(tools)
        top_layout.addWidget(self.rendered, 1)
        right.addWidget(top)
        right.addWidget(self.script)
        right.setSizes([400, 160])
        split.addWidget(right)
        from formats.text.translation_view import TranslationPane
        self.translation = TranslationPane(translation_session)
        self.translation.session.changed.connect(self.refresh_translations)
        self.make_display_menu(tools)
        split.addWidget(self.translation)
        split.setSizes([260, 550, 350])
        layout.addWidget(split, 1)
        layout.addWidget(QLabel("Glyph IDs are font-local, not ASCII. Control words are preserved below the preview."))
        self.entries.currentRowChanged.connect(self.select)
        self.relist()
        if wfm.dialogues:
            self.entries.setCurrentRow(0)
        self.translation.session.discover()

    def relist(self):
        """Fill the list of entries from the characters as they are known now."""
        wfm, row = self.wfm, self.entries.currentRow()
        self._display_key = None
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
        unchecked = sum((usage.entry(d) or {}).get('status', 'unknown') == 'unknown' for d in wfm.dialogues)
        recovered = len(getattr(wfm, 'recovered_glyphs', {}))
        self.summary.setText(f'{len(wfm.dialogues)} entries | {known}/{len(wfm.glyphs)} decoded glyphs'
                             + (f' ({recovered} reconstructed readings)' if recovered else '') + ' | '
                             + (f'{candidates} possibly unused'
                                + (f'; {unchecked} unchecked' if unchecked else '') if audited else 'In-game usage not checked'))
        if getattr(wfm, 'usage_checked', False):
            self.summary.setText(self.summary.text() + ' | Usage checked (static selectors)')
        self.summary.setToolTip(getattr(wfm, 'usage_summary', 'Native display analysis is not available for this build.'))
        if row >= 0:
            self.entries.setCurrentRow(row)
        self.filter(self.search.text())

    def make_display_menu(self, bar):
        """The Display menu: what is shown of a message, and where the English comes from."""
        from PyQt6.QtGui import QAction, QActionGroup
        session = self.translation.session
        button = QPushButton('Display')
        button.setToolTip('Show the message as the game draws it, in English, or both; and choose where the English comes from.')
        menu = QMenu(button)
        group = QActionGroup(menu)
        self.display_actions = {}
        for key, label in (('both', 'Original with the English under it'), ('original', 'Original only'),
                           ('translated', 'English only')):
            action = QAction(label, menu, checkable=True)
            action.setChecked(session.display == key)
            action.triggered.connect(lambda _checked=False, k=key: session.configure(display=k))
            group.addAction(action)
            menu.addAction(action)
            self.display_actions[key] = action
        menu.addSeparator()
        self.premade_action = QAction('Use the premade translations', menu, checkable=True)
        self.premade_action.setChecked(session.use_premade)
        self.premade_action.setToolTip('The English that comes with the program for known discs. Needs no model.')
        self.premade_action.toggled.connect(lambda value: session.configure(premade_on=value))
        menu.addAction(self.premade_action)
        self.premade_info = QAction('', menu)
        self.premade_info.setEnabled(False)
        menu.addAction(self.premade_info)
        menu.addSeparator()
        model = menu.addMenu('Translate with a model')
        self.model_off_action = QAction('Never load the translation model', model, checkable=True)
        self.model_off_action.setChecked(session.model_off)
        self.model_off_action.setToolTip('Keep the model out of memory, even if a model folder is remembered. '
                                         'A model that is loading is stopped. Only the premade translations are used.')
        self.model_off_action.toggled.connect(lambda value: session.configure(model_off=value))
        model.addAction(self.model_off_action)
        model.addSeparator()
        self.model_action = QAction('Translate every message in the background', model, checkable=True)
        self.model_action.setChecked(session.enabled)
        self.model_action.toggled.connect(lambda value: session.configure(enabled=value))
        model.addAction(self.model_action)
        self.model_choose = model.addAction('Choose a model...', self.translation.choose_model)
        button.setMenu(menu)
        bar.insertWidget(bar.count() - 1 if bar.count() else 0, button)
        self.display_button = button
        self.sync_display_menu()
        session.changed.connect(self.sync_display_menu)

    def sync_display_menu(self):
        session = self.translation.session
        for key, action in self.display_actions.items():
            action.blockSignals(True)
            action.setChecked(session.display == key)
            action.blockSignals(False)
        for action, value in ((self.premade_action, session.use_premade), (self.model_action, session.enabled),
                              (self.model_off_action, session.model_off)):
            action.blockSignals(True)
            action.setChecked(value)
            action.blockSignals(False)
        self.model_action.setEnabled(not session.model_off)
        premade = session.premade
        self.premade_info.setText(
            f'{len(premade):,} premade messages ({", ".join(premade.models) or "no model"})' if len(premade) else 'No premade translations')
        self.refresh_display()

    def select(self, index):
        if index < 0:
            return
        try:
            self.refresh_display()
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
        self.export_all_originals.setEnabled(session.project is None or session.discovered)
        for i, dialogue in enumerate(self.wfm.dialogues):
            original = export.plain(dialogue)
            preview = self.translation.session.lookup(original)
            preview = (preview if preview is not None else original).replace('\n', ' ')
            item = self.entries.item(i)
            if item is not None:
                flagged = usage.entry(dialogue) or {}
                marker = (('[Unused event] ' if flagged.get('event') is not None else '[Possibly unused] ')
                          if flagged.get('status') == 'not_found' else '')
                item.setData(UNUSED_ROLE, bool(marker))
                item.setData(Qt.ItemDataRole.ForegroundRole, QBrush(purple(self.entries.palette())) if marker else None)
                item.setText(f'{getattr(dialogue, "name", f"{i:03d}")} | {marker}{preview}')
                item.setToolTip(usage.explanation(dialogue) + '\n\n' + original)
        self.filter(self.search.text())
        self.refresh_display()

    def refresh_display(self):
        index = self.entries.currentRow()
        if not 0 <= index < len(self.wfm.dialogues):
            return
        original = export.plain(self.wfm.dialogues[index])
        session = self.translation.session
        translated = session.translations.get(original)
        key = index, translated, session.display
        if key == self._display_key:
            return
        show_original, show_english = session.display != 'translated', session.display != 'original'
        tips, pictures = [], []
        if show_original:
            tips.append('Original text, as the game draws it'
                        + ('\n' + self.wfm.palette_source if hasattr(self.wfm, 'palette_source') else ''))
            pictures.append(self.wfm.render(index))
        if show_english:
            if translated is not None and translated != original:
                from formats.text.english_preview import render
                try:
                    image, missing = render(self.wfm, index, translated)
                    tips.append('English translation, in the fallback letters'
                                + ('\nNo recognised glyph for: ' + ' '.join(sorted(missing)) + ' (shown as ?).' if missing else ''))
                except (OSError, ValueError, KeyError) as exc:
                    image = self.awaiting_image('English preview unavailable')
                    tips.append(str(exc))
            else:
                image = self.awaiting_image('No translation yet')
                tips.append('There is no premade translation of this message; choose a model in the Display menu to translate it.')
            pictures.append(image)
        self.rendered.setToolTip('\n\n'.join(tips))
        self.rendered.set_image(self.stacked(pictures), subject=(session.display, index))
        self._display_key = key

    @staticmethod
    def stacked(pictures, gap=10):
        """The pictures one under the other, left-aligned, in one picture: the frame grows with a longer text."""
        if len(pictures) == 1:
            return pictures[0]
        from PIL import Image
        image = Image.new('RGBA', (max(p.width for p in pictures),
                                   sum(p.height for p in pictures) + gap * (len(pictures) - 1)), (0, 0, 0, 0))
        top = 0
        for picture in pictures:
            image.alpha_composite(picture.convert('RGBA'), (0, top))
            top += picture.height + gap
        return image

    @staticmethod
    def awaiting_image(text):
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (256, 64), (60, 60, 60, 255))
        ImageDraw.Draw(image).text((10, 24), text, fill=(210, 210, 210, 255))
        return image

    def search_all_text(self):
        host = self.window()
        if hasattr(host, 'search_text'):
            host.search_text()
            return
        from gui.text_search import TextSearchDialog
        self.text_search = TextSearchDialog(self, self.translation.session)
        self.text_search.show()

    def export_translations(self, all_banks=False):
        session = self.translation.session
        banks = list(session.banks.values()) if all_banks else [self.bank]
        filters = {f'{label} (*{suffix})': kind for kind, (label, suffix) in export.FORMATS.items()}
        path, chosen = QFileDialog.getSaveFileName(self, 'Export English and original text',
            file_stem(self.bank.name, 'dialogue') + '-translated.json',
            ';;'.join(filters))
        if path:
            try:
                Path(path).write_text(export.render_translated(banks, session.translations,
                    session.folder, filters.get(chosen, 'json')), encoding='utf8')
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))

    def export_text(self, all_banks=False):
        filters = {f'{label} (*{suffix})': kind for kind, (label, suffix) in export.FORMATS.items()}
        path, chosen = QFileDialog.getSaveFileName(self, 'Export text', file_stem(self.bank.name, 'dialogue') + '.txt',
                                                   ';;'.join(filters), 'Script with control codes (*.txt)')
        if path:
            try:
                banks = list(self.translation.session.banks.values()) if all_banks else [self.bank]
                export.write(banks, path, filters.get(chosen, 'script'), raw=True)
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
