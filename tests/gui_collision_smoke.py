"""Visible OpenGL regression for collision selection, F and section switching."""
import sys
import time
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt, QPointF
from PyQt6.QtGui import QVector4D
from PyQt6.QtTest import QTest
from gui.main_window.window import MainWindow

QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
app = QApplication([])
app.setOrganizationName('TombaEditTests'); app.setApplicationName('CollisionSmoke')
w = MainWindow(); w.resize(1650, 950); w.set_theme('dark'); w.show()
w.open_path(sys.argv[1] if len(sys.argv) > 1 else 'rom/Tomba! (USA).cue')
out = Path('work/gui-smoke'); out.mkdir(parents=True, exist_ok=True)
state = dict(step=0, start=time.monotonic(), ready=0)


def open_section(area, index):
    w.current_node = ('group', f'SYS/LDAR{area:02d}.BIN', index)
    w.load_selection(f'AREA{area:02d} section {index - 1:02d}')


def tick():
    try:
        if time.monotonic() - state['start'] > 100:
            raise RuntimeError('Collision GUI smoke timed out')
        if not w.project or w.pool.activeThreadCount() or time.monotonic() < state['ready']:
            return
        v = w.level_view
        step = state['step']
        expected_area = {1: 0, 3: 4, 5: 3}.get(step)
        if expected_area is not None and (not v.scene or
                v.scene.resources[0].ldar != f'SYS/LDAR{expected_area:02d}.BIN'):
            return  # the worker can finish before its queued GUI update
        if step == 7 and w.tabs.tabText(0) != 'Collision planes':
            return
        if step == 0:
            open_section(0, 1)
        elif step == 1:
            assert w.tabs.tabText(0) == 'Level editor'
            assert v.canvas.isValid()
            v.animate_action.setChecked(False)
            v.collision_action.setChecked(True)
            inspector = v.collision_inspector
            assert len(inspector.rows) > 2000
            # Show a single plane, then frame a non-flat floor.
            inspector.plane.setCurrentIndex(1)
            row = next(i for i, r in enumerate(inspector.visible_rows)
                       if not r.span.wall and r.span.attribute & 1 and r.span.y1 and r.span.length)
            inspector.table.setCurrentCell(row, 1)
            QTest.keyClick(inspector.table, Qt.Key.Key_F)
            assert v.canvas.camera_controls.scene_radius == 20
            assert v.canvas.selection_lines is not None
            assert 'signed delta' in v.details.toPlainText()
            state['ready'] = time.monotonic() + .5
        elif step == 2:
            inspector = v.collision_inspector
            matrix = v.canvas._model_view_projection()
            a, b = inspector.selected.points[:2]
            mid = [(x + y) / 2 for x, y in zip(a, b)]
            p = matrix.map(QVector4D(*mid, 1))
            pos = QPointF((p.x() / p.w() + 1) * v.canvas.width() / 2,
                          (1 - p.y() / p.w()) * v.canvas.height() / 2)
            assert inspector.pick(pos)
            w.grab().save(str(out / 'collision-village.png'))
            original = v.canvas
            state['canvas'] = original
            open_section(4, 2)
        elif step == 3:
            assert v.canvas is state['canvas'] and v.canvas.isValid()
            assert all(r.turned and r.source.code >> 8 & 15 == 1 for r in v.scene.collision_records)
            inspector = v.collision_inspector
            inspector.plane.setCurrentIndex(1)
            inspector.table.setCurrentCell(0, 1)
            QTest.mouseClick(inspector.table.viewport(), Qt.MouseButton.LeftButton,
                             pos=inspector.table.visualItemRect(inspector.table.item(0, 1)).center())
            QTest.mouseDClick(inspector.table.viewport(), Qt.MouseButton.LeftButton,
                             pos=inspector.table.visualItemRect(inspector.table.item(0, 1)).center())
            assert v.canvas.camera_controls.scene_radius == 20
            state['ready'] = time.monotonic() + .5
        elif step == 4:
            w.grab().save(str(out / 'collision-mansion.png'))
            open_section(3, 2)
        elif step == 5:
            assert v.canvas.isValid()
            inspector = v.collision_inspector
            assert inspector.route.count() == 3
            inspector.plane.setCurrentIndex(0)
            inspector.route.setCurrentIndex(1)
            assert inspector.visible_rows and all(r.route == 'Alternate mountain route' for r in inspector.visible_rows)
            inspector.table.setCurrentCell(0, 1)
            inspector.frame()
            state['ready'] = time.monotonic() + .5
        elif step == 6:
            w.grab().save(str(out / 'collision-mountain.png'))
            w.set_theme('bright')
            # Opening the standalone WHM view uses the same decoded records.
            w.jump_asset(next(a for a in v.scene.resources if a.kind == 'WHM'))
        elif step == 7:
            assert w.tabs.tabText(0) == 'Collision planes'
            w.grab().save(str(out / 'collision-whm-bright.png'))
            print('PASS: real OpenGL, collision filters, line picking, F, double-click, '
                  'turned mansion, alternate mountain route and standalone WHM', flush=True)
            timer.stop(); w.close(); app.quit()
        state['step'] += 1
    except Exception:
        traceback.print_exc(); timer.stop(); app.exit(1)


timer = QTimer(); timer.timeout.connect(tick); timer.start(400)
sys.exit(app.exec())
