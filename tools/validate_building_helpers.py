"""Check helper coverage, defaults, stale-source rejection and manual grey choices."""
import argparse
from pathlib import Path
import sys
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from formats.archive.ldar import Project
from formats.level.building_helpers import entries,palette_for
from formats.level.cut_village_view import preview,byte_indices,building_image,_sheets_panel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cue')
    parser.add_argument('--ui',action='store_true')
    args=parser.parse_args()
    project=Project(args.cue)
    data=entries()
    assert set(data)=={61,76,80}
    previews={}
    for area,group in ((11,61),(16,76),(17,80)):
        p=preview(project,f'SYS/LDAR{area:02d}.BIN',1);previews[area]=p
        sheet=next(s for s in p.sheets if s.group==group)
        indices=byte_indices(sheet.building_words)
        entry=data[group]
        used=set(np.unique(indices).tolist())-{0}
        assert used <= set(entry['observed_indices'])
        assert not used & set(entry['filled_indices'])
        assert entry['observed_pixel_coverage']==1 and entry['heldout_color_agreement']>.999
        assert sheet.building_palettes[0][0].startswith('HELPER CLUT:')
        assert any(label.startswith('texel value as grey') for label,_ in sheet.building_palettes)
        image=np.array(building_image(sheet,0))
        assert np.all(image[indices==0,3]==0) and np.all(image[indices!=0,3]==255)
        assert np.count_nonzero(image[:,:,0]!=image[:,:,1])>10000
        changed=indices.copy();changed[0,0]^=1
        assert palette_for(group,changed) is None
    if args.ui:
        from PyQt6.QtWidgets import QApplication,QComboBox
        from formats.level.cut_graphics import chooser,render
        app=QApplication.instance() or QApplication([])
        p=previews[17]
        panel=_sheets_panel(p.sheets,80)
        combos=panel.findChildren(QComboBox)
        assert 'group 80' in combos[0].currentText()
        assert any(c.currentText().find('HELPER CLUT:')>=0 for c in combos)
        picker=chooser(p,kind='prop')
        assert picker.selection['choice'].spec['palette_label'].startswith('HELPER CLUT:')
        palettes=picker.findChildren(QComboBox)[3]
        grey=next(i for i in range(palettes.count()) if palettes.itemText(i).startswith('texel value as grey'))
        palettes.setCurrentIndex(grey)
        old_choice=picker.selection['choice']
        assert old_choice is not None
        restored=render(old_choice.spec,p.sheets,project)
        assert restored.image.tobytes()==old_choice.image.tobytes()
        reopened=chooser(p,current=restored,kind='prop')
        assert reopened.selection['choice'].spec['palette_hash']==restored.spec['palette_hash']
        reopened.close();picker.close();panel.close()
    print('Passed: all used building indices reference-matched, coloured/opaque output, helper defaults, '
          'grey fallback availability, pixel-hash scoping'+(', UI defaults and preserved explicit grey assignment.' if args.ui else '.'))


if __name__=='__main__':main()
