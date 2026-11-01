"""User reconstruction graphics: ROM-backed crops, stored separately from game data."""
import hashlib
import json
from dataclasses import dataclass

import numpy as np
from PIL import Image


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parts(texels):
    """Connected nonzero pieces; coordinates are suggestions, not original SPR parts."""
    mask = texels != 0
    seen = np.zeros(mask.shape, dtype=bool)
    h, w = mask.shape
    result = []
    for y, x in zip(*np.nonzero(mask)):
        if seen[y, x]:
            continue
        pending = [(int(x), int(y))]
        seen[y, x] = True
        left = right = int(x)
        top = bottom = int(y)
        count = 0
        while pending:
            a, b = pending.pop()
            count += 1
            left, right, top, bottom = min(left, a), max(right, a), min(top, b), max(bottom, b)
            for c, d in ((a-1,b), (a+1,b), (a,b-1), (a,b+1)):
                if 0 <= c < w and 0 <= d < h and mask[d,c] and not seen[d,c]:
                    seen[d,c] = True
                    pending.append((c,d))
        if count >= 8 and right > left and bottom > top:
            result.append((left, top, right-left+1, bottom-top+1))
    return sorted(result, key=lambda r: (r[1]//16, r[0], r[1]))


def texels(sheet, mode):
    from formats.level.cut_village_view import indices, byte_indices
    return indices(sheet.words) if mode == 'npc' else byte_indices(sheet.building_words)


def palettes(sheet, mode):
    return sheet.palettes if mode == 'npc' else sheet.building_palettes


@dataclass
class Graphic:
    spec: dict
    image: object

    @property
    def label(self):
        return f"Group {self.spec['group']} · {self.spec['mode']} · {self.spec['rect']} · {self.spec['palette_label']}"


def render(spec, sheets, project=None):
    from formats.level.cut_village_view import colours
    sheet = next(s for s in sheets if s.group == spec['group'])
    data = texels(sheet, spec['mode'])
    if digest(data.tobytes()) != spec['sheet_hash']:
        raise ValueError('Sprite group pixels changed')
    if spec.get('clut_file'):
        if project is None:
            raise ValueError('CLUT source unavailable')
        words = np.frombuffer(project.payload(project.disc.entries[spec['clut_file']]), '<u2')
        start = spec['clut_word']
        palette = words[start:start+(16 if spec['mode']=='npc' else 256)]
        if len(palette) != (16 if spec['mode']=='npc' else 256):
            raise ValueError('CLUT range outside file')
    else:
        palette = next(row for _, row in palettes(sheet, spec['mode'])
                       if digest(row.tobytes()) == spec['palette_hash'])
    if digest(palette.tobytes()) != spec['palette_hash']:
        raise ValueError('Palette changed')
    x,y,w,h = spec['rect']
    if not (0 <= x < x+w <= data.shape[1] and 0 <= y < y+h <= data.shape[0]):
        raise ValueError('Crop outside sprite sheet')
    crop = data[y:y+h,x:x+w]
    rgba = colours(palette)[crop].copy()
    if spec.get('transparent', True):
        rgba[crop == 0,3] = 0
    image = Image.fromarray(rgba)
    if spec.get('mirror'):
        image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    scale = float(spec.get('scale', 100)) / 100
    if not 0.1 <= scale <= 4:
        raise ValueError('Scale outside 10–400%')
    image = image.resize((max(1,round(w*scale)),max(1,round(h*scale))), Image.Resampling.NEAREST)
    return Graphic(spec, image)


class Assignments:
    def __init__(self, preview, settings=None):
        from PyQt6.QtCore import QSettings
        self.preview = preview
        self.settings = settings if settings is not None else QSettings()
        self.key = 'cutVillage/graphics/v1/' + preview.places['graphics_key']

    def load(self):
        result = {}
        try:
            records = json.loads(str(self.settings.value(self.key, '{}')))
            if not isinstance(records, dict):
                return result
        except (TypeError, ValueError):
            return result
        failed = 0
        for name, spec in records.items():
            try:
                kind, index = name.split(':')
                index = int(index)
                limit = len(self.preview.village.residents if kind == 'resident' else self.preview.village.props)
                if kind not in ('resident','prop') or not 0 <= index < limit:
                    raise ValueError('Unknown entry')
                result[kind,index] = render(spec, self.preview.sheets, self.preview.places.get('graphics_project'))
            except (ValueError, TypeError, KeyError, StopIteration, IndexError, OSError):
                failed += 1
        if failed:
            self.preview.notes.append(f'{failed} saved manual graphics assignments could not be loaded; source pixels or CLUT may have changed.')
        return result

    def save(self, entries):
        self.settings.setValue(self.key, json.dumps({f'{kind}:{index}':g.spec for (kind,index),g in entries.items()}))
        self.settings.sync()


def chooser(preview, current=None, parent=None):
    """A modal crop picker. Only Apply persists anything; Cancel is a preview."""
    from PyQt6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QSpinBox,
                                QCheckBox,QDialogButtonBox,QSplitter,QWidget)
    from gui.widgets.image_view import ImageView
    dialog = QDialog(parent)
    dialog.setWindowTitle('Assign manual graphics — reconstruction choice')
    dialog.resize(1100,800)
    layout = QVBoxLayout(dialog)
    note = QLabel('Choose a detected part or set a custom crop. Click two corners on the sheet to crop manually. '
                  'The crop is placed bottom-centred on this entry; offsets and scale adjust it. '
                  'Detected pieces are not recovered SPR definitions. Changes are saved only with Apply.')
    note.setWordWrap(True)
    layout.addWidget(note)
    group, mode, palette, part, clut = (QComboBox() for _ in range(5))
    group.addItems([f'Group {s.group}' for s in preview.sheets])
    mode.addItem('NPC figures · 4-bit', 'npc')
    mode.addItem('Building parts · 8-bit', 'building')
    clut.addItem('Suggested palettes', '')
    project = preview.places.get('graphics_project')
    if project:
        for entry in project.disc.files:
            if '/CLUT' in entry.path.upper() and entry.path.upper().endswith('.GAM'):
                clut.addItem(entry.path, entry.path)
    controls = {}
    for label, widgets in (('Sprite group / sheet', (group,mode)), ('CLUT source / palette', (clut,palette)),
                           ('Detected part', (part,))):
        bar=QHBoxLayout();bar.addWidget(QLabel(label))
        for item in widgets:bar.addWidget(item,1)
        layout.addLayout(bar)
    bar=QHBoxLayout()
    for name, low, high, value in (('X',0,767,0),('Y',0,255,0),('Width',1,768,32),('Height',1,256,32),
                                  ('Offset X',-2000,2000,0),('Offset Y',-2000,2000,0),('Scale %',10,400,100),
                                  ('CLUT word',0,8191,0)):
        control=QSpinBox();control.setRange(low,high);control.setValue(value)
        controls[name]=control;bar.addWidget(QLabel(name));bar.addWidget(control)
    controls['CLUT word'].setSingleStep(16)
    layout.addLayout(bar)
    transparent, mirror = QCheckBox('Index 0 transparent'), QCheckBox('Mirror')
    transparent.setChecked(True)
    bar=QHBoxLayout();bar.addWidget(transparent);bar.addWidget(mirror);layout.addLayout(bar)
    split=QSplitter();sheet_view=ImageView();crop_view=ImageView()
    for picture in (sheet_view,crop_view):picture.zoom.setCurrentIndex(0);split.addWidget(picture)
    layout.addWidget(split,1)
    status=QLabel();status.setWordWrap(True);layout.addWidget(status)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel)
    layout.addWidget(buttons)
    state={'busy':False,'first':None,'parts':[],'choice':None}
    cache={}

    def update():
        if state['busy']:return
        try:
            sheet=preview.sheets[group.currentIndex()];kind=mode.currentData();data=texels(sheet,kind)
            path=clut.currentData()
            if path:
                words=np.frombuffer(project.payload(project.disc.entries[path]),'<u2')
                start=controls['CLUT word'].value();row=words[start:start+(16 if kind=='npc' else 256)]
                label=f'{path} word {start}'
            else:
                label,row=palettes(sheet,kind)[palette.currentIndex()]
            spec=dict(group=sheet.group,mode=kind,rect=[controls[n].value() for n in ('X','Y','Width','Height')],
                      dx=controls['Offset X'].value(),dy=controls['Offset Y'].value(),scale=controls['Scale %'].value(),
                      transparent=transparent.isChecked(),mirror=mirror.isChecked(),sheet_hash=digest(data.tobytes()),
                      palette_hash=digest(row.tobytes()),palette_label=label,
                      clut_file=path,clut_word=controls['CLUT word'].value())
            graphic=render(spec,preview.sheets,project)
            from formats.level.cut_village_view import colours
            rgba=colours(row)[data].copy()
            if transparent.isChecked():rgba[data==0,3]=0
            picture=Image.fromarray(rgba)
            from PIL import ImageDraw
            x,y,w,h=spec['rect'];ImageDraw.Draw(picture).rectangle((x,y,x+w-1,y+h-1),outline=(0,255,255,255))
            sheet_view.set_image(picture,preserve_view=True)
            crop_view.set_image(graphic.image,preserve_view=True)
            state['choice']=graphic
            status.setText(graphic.label+' — manual assignment; not an original binding')
            buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(True)
        except (ValueError,IndexError,KeyError,StopIteration,AttributeError) as exc:
            state['choice']=None;status.setText(f'Choose a valid sheet, CLUT and crop: {exc}')
            buttons.button(QDialogButtonBox.StandardButton.Apply).setEnabled(False)

    def fill():
        state['busy']=True
        sheet=preview.sheets[group.currentIndex()];kind=mode.currentData()
        if kind=='building' and sheet.building_words is None:
            mode.setCurrentIndex(0);kind='npc'
        data=texels(sheet,kind)
        palette.clear();palette.addItems([label for label,_ in palettes(sheet,kind)])
        key=(sheet.group,kind)
        if key not in cache:cache[key]=parts(data)
        state['parts']=cache[key];part.clear();part.addItem('Custom crop')
        for n,(x,y,w,h) in enumerate(state['parts'],1):part.addItem(f'Part {n}: x{x}, y{y}, {w} × {h}')
        state['first']=None
        controls['X'].setMaximum(data.shape[1]-1);controls['Width'].setMaximum(data.shape[1])
        controls['Width'].setValue(min(controls['Width'].value(),data.shape[1]-controls['X'].value()))
        state['busy']=False;update()

    def use_part(index):
        if state['busy'] or index<=0:return
        state['busy']=True
        for name,value in zip(('X','Y','Width','Height'),state['parts'][index-1]):controls[name].setValue(value)
        state['busy']=False;update()

    def clicked(x,y):
        if state['first'] is None:
            state['first']=(int(x),int(y));status.setText('First corner chosen. Click the opposite corner.');return
        a,b=state.pop('first');state['first']=None
        x,y=int(x),int(y);state['busy']=True;part.setCurrentIndex(0)
        for name,value in zip(('X','Y','Width','Height'),(min(a,x),min(b,y),abs(a-x)+1,abs(b-y)+1)):controls[name].setValue(value)
        state['busy']=False;update()

    group.currentIndexChanged.connect(fill);mode.currentIndexChanged.connect(fill)
    palette.currentIndexChanged.connect(update);clut.currentIndexChanged.connect(update)
    part.currentIndexChanged.connect(use_part)
    for control in controls.values():control.valueChanged.connect(update)
    transparent.toggled.connect(update);mirror.toggled.connect(update)
    sheet_view.canvas.clicked.connect(clicked)
    buttons.rejected.connect(dialog.reject)
    buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(dialog.accept)
    fill()
    if current:
        spec=current.spec;state['busy']=True
        group.setCurrentIndex(next(i for i,s in enumerate(preview.sheets) if s.group==spec['group']))
        mode.setCurrentIndex(0 if spec['mode']=='npc' else 1);state['busy']=False;fill();state['busy']=True
        clut.setCurrentIndex(max(0,clut.findData(spec.get('clut_file',''))))
        if not spec.get('clut_file'):
            palette.setCurrentIndex(next((i for i,(_,row) in enumerate(palettes(preview.sheets[group.currentIndex()],spec['mode']))
                                          if digest(row.tobytes())==spec['palette_hash']),0))
        for name,value in zip(('X','Y','Width','Height'),spec['rect']):controls[name].setValue(value)
        for name,value in (('Offset X',spec.get('dx',0)),('Offset Y',spec.get('dy',0)),('Scale %',spec.get('scale',100)),
                           ('CLUT word',spec.get('clut_word',0))):controls[name].setValue(value)
        mirror.setChecked(spec.get('mirror',False));transparent.setChecked(spec.get('transparent',True))
        state['busy']=False;update()
    dialog.selection=state
    return dialog
