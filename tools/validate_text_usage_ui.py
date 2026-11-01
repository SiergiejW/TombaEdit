"""JP cut/shared usage evidence and English-only/Fit WFM viewer smoke checks."""
import argparse
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from formats.archive.ldar import Project, table_name
from formats.level.cut_village_view import _bank
from formats.text import usage, export
from formats.text.wfm import Wfm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jp_cue')
    parser.add_argument('--english-cue', required=True)
    args = parser.parse_args()
    project = Project(args.jp_cue)
    banks = {}
    for area, count in ((11, 12), (16, 21), (17, 31)):
        wfm, asset = _bank(project, f'SYS/LDAR{area:02d}.BIN')
        usage.attach(wfm, project, asset.source.path, asset.offset)
        assert sum(usage.confirmed_cut_village(d) for d in wfm.dialogues) == count
        assert not usage.confirmed_cut_village(wfm.dialogues[154])  # common item-use text
        for dialogue in wfm.dialogues:
            if usage.confirmed_cut_village(dialogue):
                assert dialogue.usage['status'] == 'referenced'
                assert f'AREA{area:02d}' in usage.explanation(dialogue)
                assert 'Confirmed unused' in usage.label(dialogue)
        banks[area] = wfm, asset
    wood, asset = banks[11]
    assert usage.confirmed_cut_village(wood.dialogues[210])
    assert not usage.confirmed_cut_village(wood.dialogues[220])  # old wrong routine's binding
    emitted = list(export.entries(export.Bank('Wood', asset.source.path, asset.offset, wfm=wood)))
    assert emitted[210]['usage']['availability'] == 'confirmed_unused_cut_village'
    profile = usage._study_for(project)
    shared = [(key, int(i), item) for key, bank in profile['banks'].items() for i, item in bank['text'].items()
              if item['status'] == 'referenced_elsewhere']
    assert len(shared) == 146
    assert all(item['local_status'] == 'not_found' and item['equivalent_references'] for _, _, item in shared)

    # A changed code input must lose the retail-only classification.
    read_asset = project.asset_data
    def changed_code(item):
        raw = bytes(read_asset(item))
        return bytes([raw[0] ^ 1])+raw[1:] if item.kind == 'INS' else raw
    project.__dict__.pop('_text_usage_code_sha1', None)
    with patch.object(project, 'asset_data', side_effect=changed_code):
        changed = Wfm(read_asset(asset))
        usage.attach(changed, project, asset.source.path, asset.offset)
        assert not any(usage.confirmed_cut_village(d) for d in changed.dialogues)
    project.__dict__.pop('_text_usage_code_sha1', None)

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from formats.text.translation_session import TranslationSession
    from formats.text.wfm_viewer import DialogueView
    from gui.widgets.text_usage import CUT_DIALOGUE_ROLE, UNUSED_ROLE, blue
    app = QApplication.instance() or QApplication([])
    session = TranslationSession(project)
    session.enabled = False
    session.model_off = True
    session.discovered = True
    viewer = DialogueView(wood, 'Wood', asset.source.path, asset.offset, session)
    viewer.resize(1400, 900)
    viewer.show()
    app.processEvents()
    marker = viewer.entries.item(210)
    assert marker.data(CUT_DIALOGUE_ROLE) and not marker.data(UNUSED_ROLE)
    assert marker.foreground().color() == blue(viewer.entries.palette())
    viewer.usage_filter.setCurrentIndex(viewer.usage_filter.findData('confirmed_unused_cut_village'))
    assert sum(not viewer.entries.item(i).isHidden() for i in range(viewer.entries.count())) == 12
    viewer.entries.setCurrentRow(210)
    assert 'AREA11' in viewer.script.toPlainText()
    assert viewer.rendered.zoom.currentIndex() == 0
    viewer.rendered.zoom.setCurrentIndex(3)
    viewer.entries.setCurrentRow(232)
    assert viewer.rendered.zoom.currentIndex() == 3
    assert not viewer.translation.isHidden() and not viewer.panes.widget(1).isHidden()
    viewer.close()
    session.closed = True

    english = Project(args.english_cue)
    groups = next(groups for path, groups in english.ldars.items() if table_name(path) == (0, 11))
    asset = next(a for a in groups[0].assets if a.kind == 'WFM' and a.slot == 0)
    session = TranslationSession(english)
    session.enabled = False
    session.model_off = True
    # Deliberately prefer translation globally: an English bank must still show its original.
    session.display = 'translated'
    with patch.object(session, 'discover') as discover:
        english_view = DialogueView(Wfm(english.asset_data(asset)), 'English', asset.source.path, asset.offset, session)
        english_view.resize(1400, 900)
        english_view.show()
        app.processEvents()
        assert english_view.is_english
        assert english_view.translation.isHidden() and english_view.panes.widget(1).isHidden()
        assert not english_view.panes.widget(0).isHidden() and english_view.display_button.isHidden()
        assert english_view.rendered.zoom.currentIndex() == 0
        english_view.entries.setCurrentRow(190)
        assert english_view.rendered.image is not None
        session.changed.emit()
        assert english_view.translation.isHidden() and english_view.panes.widget(1).isHidden()
        assert not discover.called
        english_view.close()
    session.closed = True
    print('Passed: 64 blue confirmed cut-village entries, 146 shared native streams, export evidence, '
          'changed-code rejection, filtering, default Fit/preserved zoom, and English-only original preview.')


if __name__ == '__main__':
    main()
