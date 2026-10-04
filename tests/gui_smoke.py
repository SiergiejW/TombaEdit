"""Visible, real-OpenGL integration smoke test; writes screenshots under work/."""
import sys,time,traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from tombaedit.window import MainWindow
QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app=QApplication([])
app.setOrganizationName('TombaEditTests');app.setApplicationName('Smoke')
output=Path('work/gui-smoke');output.mkdir(parents=True, exist_ok=True)
w=MainWindow();w.show();w.set_theme('dark');w.open_path(sys.argv[1] if len(sys.argv)>1 else 'rom/Tomba! (USA).cue')
state={'step':0,'waiting':False,'start':time.monotonic()}
def tick():
 try:
  if time.monotonic()-state['start']>60:raise RuntimeError('UI smoke timeout')
  if not w.project or w.pool.activeThreadCount():return
  s=state['step']
  if s==0:
   w.grab().save('work/gui-smoke/01-disc.png');print('loaded',w.count_label.text(),flush=True)
   a=next(a for a in w.project.ldars['SYS/LDAR00.BIN'][1].assets if a.kind=='WMD')
   w.jump_asset(a);state['step']=1
  elif s==1:
   if w.tabs.tabText(0)=='Loading':return
   assert w.tabs.tabText(0)=='Geometry'
   print('model tabs',[w.tabs.tabText(i) for i in range(w.tabs.count())],flush=True)
   widget=w.tabs.widget(0)
   if hasattr(widget,'canvas'):
    assert widget.canvas.isValid()
    image=widget.canvas.grabFramebuffer();print('GL',widget.canvas.isValid(),image.size(),flush=True);image.save('work/gui-smoke/02-geometry.png')
   w.grab().save('work/gui-smoke/02-window.png')
   a=next(a for a in w.project.ldars['SYS/LDAR00.BIN'][1].assets if a.kind=='WFM')
   w.jump_asset(a);state['step']=2
  elif s==2:
   if w.tabs.tabText(0)=='Loading':return
   assert w.tabs.tabText(0)=='Dialogue'
   assert w.tabs.widget(0).wfm.dialogues
   print('text tabs',[w.tabs.tabText(i) for i in range(w.tabs.count())],flush=True)
   w.grab().save('work/gui-smoke/03-dialogue.png')
   a=next(a for a in w.project.ldars['SYS/LDAR00.BIN'][0].assets if a.code==0x32ff)
   w.jump_asset(a);state['step']=3
  elif s==3:
   if w.tabs.tabText(0)=='Loading':return
   assert w.tabs.tabText(0)=='Sprites'
   assert w.tabs.widget(0).image.image.getbbox() is not None
   print('sprite tabs',[w.tabs.tabText(i) for i in range(w.tabs.count())],flush=True)
   w.grab().save('work/gui-smoke/04-sprite.png');w.set_theme('bright');state['step']=4
  elif s==4:
   w.grab().save('work/gui-smoke/05-bright.png')
   w.destination=lambda name: str(output / name)
   payload=w.current_data
   entry=w.source_entry()
   w.export_payload();w.export_raw()
   assert (output / Path(entry.path).name).read_bytes()==w.project.disc.read(entry)
   assert any(f.read_bytes()==payload for f in output.glob('*.SPR'))
   print('PASS: navigation, viewers, themes, payload/source export',flush=True)
   timer.stop();w.close();app.quit()
 except Exception:
  traceback.print_exc();timer.stop();app.exit(1)
timer=QTimer();timer.timeout.connect(tick);timer.start(500)
sys.exit(app.exec())

