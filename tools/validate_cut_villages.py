"""Regression checks against a user-supplied JP retail CUE; no ROM is bundled.

Run: python tools/validate_cut_villages.py "rom/Ore! Tomba (Japan).cue" [--ui]
"""
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formats.archive.ldar import Project
from formats.level.cut_towns import dialogue_routines, WINDOWS
from formats.level.cut_village_view import _overlay, preview, mechanisms, draw_plan, hit_test, describe
from formats.level.cut_research import animations, supported, REPORT, reference_manifest, STOPS
from game.builds import executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cue')
    parser.add_argument('--ui', action='store_true')
    args = parser.parse_args()
    project = Project(args.cue)
    assert supported(project), 'Supply the audited SLPS_011.44 retail build'
    exe = executable(project)
    overlay = bytes(_overlay(project))
    import struct
    points = [struct.unpack_from('<hh',overlay,0x801018CC-exe.build.overlay+i*4) for i in range(7)]
    assert tuple(p for p in points if p != (-999,-999)) == STOPS
    reference = reference_manifest()
    assert len(reference['files']) == 9 and any(f['path']=='LICENSE' for f in reference['files'])
    readers = dialogue_routines(overlay, exe.build.overlay, exe.word, WINDOWS[exe.build.name])
    assert {n: (address, len(cases)) for n, (address, cases) in readers.items()} == {
        13: (0x800F3000, 11), 14: (0x800F41FC, 16), 15: (0x800F5488, 16)}
    assert readers[13][1][3] == [(4, 0)]  # fortune-teller hut, not Baccus dialogue
    assert readers[15][1][3] == [(3, 0), (3, 2), (3, 3), (3, 5), (3, 8), (3, 11)]
    changed = bytearray(overlay)
    changed[-1] ^= 1
    assert dialogue_routines(changed, exe.build.overlay, exe.word, WINDOWS[exe.build.name]) == {}
    previews = {area: preview(project, f'SYS/LDAR{area:02d}.BIN', 1) for area in (11, 16, 17, 18)}
    stone = previews[16]
    assert [len(r.messages) for r in stone.rows] == [1, 1, 1, 4, 4, 3, 2, 3, 2, 0, 0, 0, 1]
    # The house-1 strongman has exactly his four phase lines.
    assert [entry for entry, _ in stone.rows[3].messages] == [210, 214, 217, 221]
    assert not previews[11].rows[-1].messages  # dlg11 is outside Wood's actual switch
    from formats.text import premade
    translations = premade.load()
    iron = previews[17]
    messages = [text for row in iron.rows for _, text in row.messages]
    assert len(messages) == 32 and all(translations.get(text, 'Japanese retail') for text in messages)
    assert any('\n' in text for text in messages), 'Translation keys must retain original line breaks'
    assert len(mechanisms(iron.village)) == 10
    hits = []
    draw_plan(iron.village, hits=hits)
    markers = [h for h in hits if h[0] in ('lift', 'passage')]
    assert len(markers) == 10
    for kind, index, (x0, y0, x1, y1) in markers:
        assert hit_test(hits, (x0+x1)/2, (y0+y1)/2) == (kind, index)
        assert 'World trigger' in describe(iron, [(kind, index)])
    scripts = animations(project)
    assert len(scripts) == 24
    assert sorted({s[0] for _, _, steps in scripts for s in steps}) == list(range(148, 203))
    assert scripts[0] == (0, 0x80014B6C, [(169, 14, 0, 0, 14), (170, 14, 0, 0, 0x800E)])
    report = REPORT.read_text(encoding='utf8')
    assert '73 bounded blocks' in report and '0x801047F4' in report
    if args.ui:
        from PyQt6.QtWidgets import QApplication, QLineEdit, QListWidget, QTextBrowser, QPushButton, QTabWidget, QComboBox
        from formats.level.cut_research import view
        from formats.level.cut_village_view import view as village_view
        app = QApplication.instance() or QApplication([])
        jumps = []
        widget = view(project, lambda *v: jumps.append(v))
        widget.resize(1200, 800)
        widget.show()
        app.processEvents()
        assert widget.findChild(QTabWidget).count() == 3
        search = widget.findChild(QLineEdit)
        search.setText('0x801047F4')
        search.returnPressed.emit()
        assert widget.findChild(QTextBrowser).textCursor().selectedText() == '0x801047F4'
        documents = widget.findChild(QComboBox)
        assert documents.count() == 10
        documents.setCurrentIndex(1)
        assert "SiergiejW" in widget.findChild(QTextBrowser).toPlainText()
        outline = widget.findChild(QListWidget)
        port = next(i for i in range(outline.count()) if outline.item(i).text().startswith('Port test'))
        outline.setCurrentRow(port)
        assert widget.findChild(QTextBrowser).textCursor().selectedText() == outline.item(port).text()
        documents.setCurrentIndex(0)
        for button in widget.findChildren(QPushButton):
            if button.text() == 'Open Iron Town plan':
                button.click()
        assert jumps == [('village', ('SYS/LDAR17.BIN', 1))]
        for p in previews.values():
            plan = village_view(p)
            assert any('Research' in b.text() for b in plan.findChildren(QPushButton))
            plan.close()
        from PyQt6.QtWidgets import QTableWidget, QLabel
        plan = village_view(iron, lambda text: translations.get(text, 'Japanese retail'))
        mechanism_table = next(t for t in plan.findChildren(QTableWidget) if t.columnCount() == 4)
        mechanism_table.selectRow(0)
        assert any('L1 — Lower lift' in label.text() for label in plan.findChildren(QLabel))
        mechanism_table.selectRow(6)
        assert any('P8 — Internal passage' in label.text() for label in plan.findChildren(QLabel))
        from formats.level.cut_graphics import chooser, Assignments, render
        from PyQt6.QtCore import QSettings
        from tempfile import TemporaryDirectory
        picker = chooser(iron, kind='prop')
        graphic = picker.selection['choice']
        assert graphic is not None and graphic.spec['group'] == 80 and graphic.spec['mode'] == 'building'
        with TemporaryDirectory() as folder:
            store = Assignments(iron, QSettings(str(Path(folder)/'graphics.ini'), QSettings.Format.IniFormat))
            store.save({('prop', 0):graphic, ('resident', 0):graphic})
            saved = store.load()
            assert set(saved) == {('prop',0),('resident',0)}
            assert saved['prop',0].image.tobytes() == graphic.image.tobytes()
            before = draw_plan(iron.village,iron.art)
            after = draw_plan(iron.village,iron.art,graphics=saved)
            assert before.size != after.size or before.tobytes() != after.tobytes()
            altered = dict(graphic.spec, sheet_hash='changed')
            try:
                render(altered,iron.sheets,project)
                raise AssertionError('Changed sheet must not reuse a saved crop')
            except ValueError:
                pass
            store.save({})
            assert store.load() == {}
        from unittest.mock import patch
        props = next(t for t in plan.findChildren(QTableWidget) if t.horizontalHeaderItem(0).text() == 'Prop')
        props.selectRow(0)
        class Accepted:
            selection = {'choice':graphic}
            def exec(self):return 1
        with patch('formats.level.cut_graphics.chooser',return_value=Accepted()), patch.object(Assignments,'save') as save:
            next(b for b in plan.findChildren(QPushButton) if b.text()=='Assign graphics…').click()
            assert ('prop',0) in iron.graphics and save.called
            assert 'Group 80' in props.item(0,5).text()
            next(b for b in plan.findChildren(QPushButton) if b.text()=='Reset manual graphics').click()
            assert ('prop',0) not in iron.graphics
        picker.close()
        plan.close()
        widget.close()
    print('Passed: native dialogue bindings, phase-specific Stone text, modified-overlay rejection, '
          'all 24 animations, hashed upstream snapshot, native lift table, report availability' +
          (', UI document navigation, manual graphics persistence/apply/reset and four previews.' if args.ui else '.'))


if __name__ == '__main__':
    main()
