"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QFontDatabase, QSurfaceFormat, QMatrix4x4, QAction
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QSpinBox, QSplitter, QListWidget, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QToolBar, QStyle, QInputDialog)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from psx.graphics import texture_page, render_sprite



from gui.widgets.image_view import ImageView, text_view, qimage

from gui.widgets.camera_controls import CameraControls, CameraEventMixin, CONTROLS_HINT, LEVEL_HEADING, LEVEL_PITCH
from gui.widgets.polygon_pick import ray_through, nearest_polygon
from gui.theme import view_background
from PIL import ImageDraw

class MeshCanvas(CameraEventMixin, QOpenGLWidget):
    picked = pyqtSignal(object)
    def __init__(self, meshes, vram):
        super().__init__()
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile)
        fmt.setDepthBufferSize(24)
        self.setFormat(fmt)
        self.meshes, self.vram = meshes, vram
        self.index = -1
        self.textured = True
        self.colored = True
        self.wireframe = False
        self.backface_culling = False
        self.show_origin = False
        self.spread = True
        self.spread_offsets = {}
        self.visible = set()
        self.textures = {}
        self.last = QPoint()
        self.camera_controls = CameraControls(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.selected = None
        self.pan = [0., 0.]
        self.fit()
        self.setMinimumSize(200, 200)

    def active(self):
        return [mesh for i, mesh in enumerate(self.meshes) if i in self.visible]

    def compute_spread_offsets(self):
        if not self.meshes:
            self.spread_offsets = {}
            return
        bounds = []
        spans = []
        for mesh in self.meshes:
            arrays = [batch[0] for batch in mesh.batches.values() if len(batch[0])]
            if arrays:
                lo = np.min([array.min(axis=0) for array in arrays], axis=0)
                hi = np.max([array.max(axis=0) for array in arrays], axis=0)
                center = (lo + hi) / 2
                spans.append(float(np.max(hi-lo)))
            else:
                center = np.zeros(3)
            bounds.append(center)
        step = max(1., float(np.percentile(spans, 90)) * 1.35) if spans else 1.
        columns = max(1, math.ceil(math.sqrt(len(self.meshes))))
        rows = math.ceil(len(self.meshes) / columns)
        self.spread_offsets = {
            i: np.array(((i % columns - (columns-1)/2) * step,
                         ((rows-1)/2 - i//columns) * step, 0.)) - center
            for i, center in enumerate(bounds)
        }

    def offset_for(self, index):
        return self.spread_offsets.get(index, np.zeros(3)) if self.spread else np.zeros(3)

    def fit(self):
        arrays = [batch[0] + self.offset_for(i)
                  for i, mesh in enumerate(self.meshes) if i in self.visible
                  for batch in mesh.batches.values() if len(batch[0])]
        if arrays:
            lo = np.min([a.min(axis=0) for a in arrays], axis=0)
            hi = np.max([a.max(axis=0) for a in arrays], axis=0)
            self.center = (lo + hi) / 2
            self.radius = max(1., float(np.linalg.norm(hi - lo)) / 2)
        else:
            self.center, self.radius = np.zeros(3), 1.
        self.camera_controls.frame(self.center, self.radius, heading=LEVEL_HEADING, pitch=LEVEL_PITCH)
        self.update()

    def initializeGL(self):
        from OpenGL import GL as gl
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDisable(gl.GL_CULL_FACE)
        gl.glEnable(gl.GL_ALPHA_TEST)
        gl.glAlphaFunc(gl.GL_GREATER, 0.05)
        self.context().aboutToBeDestroyed.connect(self.cleanup)

    def cleanup(self):
        if self.textures and self.context() and self.context().isValid():
            from OpenGL import GL as gl
            self.makeCurrent()
            gl.glDeleteTextures(list(self.textures.values()))
            self.textures.clear()
            self.doneCurrent()

    def paintGL(self):
        from OpenGL import GL as gl
        from OpenGL.GLU import gluPerspective
        gl.glClearColor(*view_background(), 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        if self.backface_culling:
            gl.glEnable(gl.GL_CULL_FACE)
        else:
            gl.glDisable(gl.GL_CULL_FACE)
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        gluPerspective(45, self.width() / max(1, self.height()), max(0.01, self.radius / 1000), self.radius * 200)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadIdentity()
        c = self.camera_controls
        gl.glRotatef(c.camera_angle_v, 1, 0, 0)
        gl.glRotatef(c.camera_angle_h, 0, 1, 0)
        gl.glTranslatef(c.camera_x, c.camera_y, c.camera_z)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_LINE if self.wireframe else gl.GL_FILL)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        for i, mesh in enumerate(self.meshes):
            if i not in self.visible:
                continue
            gl.glPushMatrix()
            gl.glTranslatef(*self.offset_for(i))
            for (page, clut, semi), (vertices, uv, colors) in mesh.batches.items():
                use_texture = self.textured and page >= 0
                if use_texture:
                    key = (page, clut)
                    if key not in self.textures:
                        im = texture_page(self.vram, page, clut)
                        tex = int(gl.glGenTextures(1))
                        self.textures[key] = tex
                        gl.glBindTexture(gl.GL_TEXTURE_2D, tex)
                        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
                        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
                        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT)
                        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT)
                        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, im.width, im.height, 0,
                                        gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, im.tobytes())
                    gl.glEnable(gl.GL_TEXTURE_2D)
                    gl.glBindTexture(gl.GL_TEXTURE_2D, self.textures[key])
                    gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
                    gl.glTexCoordPointer(2, gl.GL_FLOAT, 0, uv)
                    gl.glTexEnvi(gl.GL_TEXTURE_ENV, gl.GL_TEXTURE_ENV_MODE, gl.GL_COMBINE)
                    gl.glTexEnvi(gl.GL_TEXTURE_ENV, gl.GL_COMBINE_RGB, gl.GL_MODULATE)
                    gl.glTexEnvf(gl.GL_TEXTURE_ENV, gl.GL_RGB_SCALE, 2)
                else:
                    gl.glDisable(gl.GL_TEXTURE_2D)
                    gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
                draw_colors = colors if self.colored else np.ones_like(colors)
                if use_texture:
                    draw_colors = np.ascontiguousarray(draw_colors * 0.5)
                gl.glColorPointer(3, gl.GL_FLOAT, 0, draw_colors)
                gl.glVertexPointer(3, gl.GL_FLOAT, 0, vertices)
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, len(vertices))
            gl.glPopMatrix()
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable(gl.GL_TEXTURE_2D)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
        if self.show_origin:
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glLineWidth(2)
            gl.glBegin(gl.GL_LINES)
            for color, end in [((1, .25, .25), (self.radius, 0, 0)),
                               ((.25, 1, .25), (0, self.radius, 0)),
                               ((.25, .5, 1), (0, 0, self.radius))]:
                gl.glColor3f(*color)
                gl.glVertex3f(0, 0, 0)
                gl.glVertex3f(*end)
            gl.glEnd()
            gl.glEnable(gl.GL_DEPTH_TEST)
        if self.selected is not None:
            model_index, p = self.selected
            order = [0, 1, 3, 2] if len(p['vertices']) == 4 else [0, 1, 2]
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glColor3f(1, 1, 0)
            gl.glLineWidth(2)
            gl.glBegin(gl.GL_LINE_LOOP)
            for i in order:
                gl.glVertex3f(*(np.asarray(p['vertices'][i]) + self.offset_for(model_index)))
            gl.glEnd()
            gl.glEnable(gl.GL_DEPTH_TEST)

    def _model_view_projection(self):
        m = QMatrix4x4()
        m.perspective(45, self.width() / max(1, self.height()), max(.01, self.radius / 1000), self.radius * 200)
        c = self.camera_controls
        m.rotate(c.camera_angle_v, 1, 0, 0)
        m.rotate(c.camera_angle_h, 0, 1, 0)
        m.translate(c.camera_x, c.camera_y, c.camera_z)
        return m

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        ray = ray_through(self._model_view_projection(), event.position().x(), event.position().y(), self.width(), self.height())
        if ray is None:
            return
        polygons = [(i, p) for i, mesh in enumerate(self.meshes) if i in self.visible for p in mesh.polygons]
        vertices, faces, lookup = [], [], []
        for pi, (model_index, p) in enumerate(polygons):
            base = len(vertices)
            vertices.extend(np.asarray(p['vertices']) + self.offset_for(model_index))
            faces.append((base, base + 1, base + 2)); lookup.append(pi)
            if len(p['vertices']) == 4:
                faces.append((base + 3, base + 2, base + 1)); lookup.append(pi)
        hit = nearest_polygon(*ray, np.asarray(vertices), np.asarray(faces), np.asarray(lookup))
        self.selected = polygons[hit] if hit is not None else None
        self.picked.emit(self.selected)
        self.update()


class ModelView(QWidget):
    def __init__(self, meshes=None, vram=None, code=0):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName('viewerToolbar')
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.toolbar.setMovable(False)
        self.canvas = MeshCanvas([], np.zeros((512, 1024), np.uint16))
        def add_action(icon_kind, title, callback, checked=None):
            action = QAction(self.style().standardIcon(icon_kind), title, self)
            if checked is not None:
                action.setCheckable(True)
                action.setChecked(checked)
                action.toggled.connect(callback)
            else:
                action.triggered.connect(callback)
            self.toolbar.addAction(action)
            return action
        self.texture_action = add_action(QStyle.StandardPixmap.SP_DialogYesButton,
            'Texture Mode', lambda value: self.toggle('textured', value), True)
        self.texture_action.setToolTip('Show CLUT textures. Turn off to inspect WMD vertex colours.')
        self.culling_action = add_action(QStyle.StandardPixmap.SP_BrowserReload,
            'Backface Culling', lambda value: self.toggle('backface_culling', value), False)
        self.spread_action = add_action(QStyle.StandardPixmap.SP_FileDialogDetailedView,
            'Spread Parts', self.toggle_spread, True)
        self.spread_action.setToolTip('Lay every model on a numbered grid, as in the Tomba2Edit SMST viewer.')
        add_action(QStyle.StandardPixmap.SP_FileDialogContentsView,
            'Frame Model', self.canvas.fit)
        self.origin_action = add_action(QStyle.StandardPixmap.SP_ArrowUp,
            'Origin', lambda value: self.toggle('show_origin', value), False)
        add_action(QStyle.StandardPixmap.SP_DialogOpenButton,
            'Export glTF', self.export)
        layout.addWidget(self.toolbar)
        split = QSplitter()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel('Models'))
        self.objects = QTableWidget(0, 5)
        self.objects.setHorizontalHeaderLabels(['Show', 'Model', 'Tris', 'Quads', 'Offset'])
        self.objects.verticalHeader().hide()
        self.objects.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.objects.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.objects.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.objects.setColumnWidth(0, 48)
        self.objects.setColumnWidth(2, 52)
        self.objects.setColumnWidth(3, 52)
        self.objects.setColumnWidth(4, 90)
        self.objects.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.objects.itemChanged.connect(self.visibility_changed)
        self.objects.currentCellChanged.connect(self.model_selected)
        ll.addWidget(self.objects)
        row = QHBoxLayout()
        show_all = QPushButton('Show all')
        show_all.clicked.connect(self.show_all)
        isolate = QPushButton('Isolate selected')
        isolate.clicked.connect(self.isolate)
        rename = QPushButton('Name model...')
        rename.clicked.connect(self.rename_model)
        row.addWidget(show_all); row.addWidget(isolate); row.addWidget(rename)
        ll.addLayout(row)
        split.addWidget(left)
        split.addWidget(self.canvas)
        side = QWidget()
        sl = QVBoxLayout(side)
        self.details = text_view('Click a triangle or quad to inspect its original WMD record and UVs.')
        sl.addWidget(self.details)
        self.uv = ImageView()
        sl.addWidget(self.uv)
        split.addWidget(side)
        split.setSizes([280, 680, 300])
        layout.addWidget(split, 1)
        self.stats = QLabel()
        self.stats.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.stats)
        hint = QLabel(CONTROLS_HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.canvas.picked.connect(self.show_polygon)
        if meshes is not None:
            self.set_data(meshes, vram, code)

    def set_data(self, meshes, vram, code=0, names=None, rename_callback=None):
        self.rename_callback = rename_callback
        self.model_names = names or {}
        self.canvas.cleanup()
        self.canvas.meshes, self.canvas.vram = meshes, vram
        self.canvas.compute_spread_offsets()
        self.canvas.selected = None
        self.objects.blockSignals(True)
        self.objects.setRowCount(len(meshes))
        for i, mesh in enumerate(meshes):
            triangles = sum(1 for p in mesh.polygons if len(p['vertices']) == 3)
            quads = sum(1 for p in mesh.polygons if len(p['vertices']) == 4)
            entries = ['', self.model_names.get(i) or f'Model {i:03d}', str(triangles), str(quads), f'0x{mesh.offset:06X}']
            for column, value in enumerate(entries):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked)
                self.objects.setItem(i, column, item)
        self.canvas.visible = set(range(len(meshes)))
        self.spread_action.setChecked(code not in (0x5080, 0x50FF))
        self.canvas.spread = self.spread_action.isChecked()
        if meshes:
            self.objects.setCurrentCell(0, 0)
        self.objects.blockSignals(False)
        self.canvas.fit()
        triangles = sum(len(a[0]) // 3 for m in meshes for a in m.batches.values())
        self.stats.setText(f'{triangles:,} triangles | {sum(len(m.polygons) for m in meshes):,} original polygons')
        self.show_polygon(None)

    def rename_model(self):
        row = self.objects.currentRow()
        if row < 0 or self.rename_callback is None:
            return
        name, accepted = QInputDialog.getText(self, 'Name model',
            'Label (empty restores the original name):', text=self.model_names.get(row, ''))
        if accepted:
            self.rename_callback(row, name.strip())
            self.model_names[row] = name.strip()
            self.objects.item(row, 1).setText(name.strip() or f'Model {row:03d}')

    def model_selected(self, row, column, old_row, old_column):
        self.canvas.selected = None
        self.show_polygon(None)
        self.canvas.update()

    def visibility_changed(self, item):
        if item.column() != 0:
            return
        self.canvas.visible = {row for row in range(self.objects.rowCount())
                               if self.objects.item(row, 0).checkState() == Qt.CheckState.Checked}
        self.canvas.selected = None
        self.canvas.update()

    def show_all(self):
        self.objects.blockSignals(True)
        for row in range(self.objects.rowCount()):
            self.objects.item(row, 0).setCheckState(Qt.CheckState.Checked)
        self.objects.blockSignals(False)
        self.canvas.visible = set(range(self.objects.rowCount()))
        self.canvas.fit()

    def isolate(self):
        selected = self.objects.currentRow()
        if selected < 0:
            return
        self.objects.blockSignals(True)
        for row in range(self.objects.rowCount()):
            self.objects.item(row, 0).setCheckState(Qt.CheckState.Checked if row == selected else Qt.CheckState.Unchecked)
        self.objects.blockSignals(False)
        self.canvas.visible = {selected}
        self.canvas.fit()

    def toggle(self, name, value):
        setattr(self.canvas, name, value)
        self.canvas.update()

    def toggle_spread(self, value):
        self.canvas.spread = value
        self.canvas.selected = None
        self.show_polygon(None)
        self.canvas.fit()

    def show_polygon(self, selected):
        if selected is None:
            self.details.setPlainText('Click a triangle or quad to inspect its UVs.\n\nGLB exports visible models with embedded textures and vertex colours.\nPSX blend equations and overbright colours are approximated in glTF.')
            self.uv.set_image(Image.new('RGBA', (1, 1)))
            return
        index, p = selected
        texels = [(round(u * 256 - .5), round(v * 256 - .5)) for u, v in p['uv']]
        self.details.setPlainText(f"Object {index:03d} | {p['kind']}\nRecord @ 0x{p['offset']:X}\nPage: 0x{p['page']:04X}\nCLUT: 0x{p['clut']:04X}\nGPU command: 0x{p['command']:02X}\n\nUV: {texels}\n\nVertices: {p['vertices']}")
        image = texture_page(self.canvas.vram, p['page'], p['clut']).copy() if p['page'] >= 0 else Image.new('RGBA', (256, 256), (32, 32, 32, 255))
        order = [0, 1, 3, 2, 0] if len(texels) == 4 else [0, 1, 2, 0]
        ImageDraw.Draw(image).line([texels[i] for i in order], fill='yellow', width=1)
        self.uv.set_image(image)

    def export(self):
        path, mode = QFileDialog.getSaveFileName(self, 'Export geometry', 'model.glb',
            'GLB (unlit, game colours) (*.glb);;GLB (lit, external lighting) (*.glb)')
        if path:
            try:
                from formats.models.glb import export_glb
                export_glb(path, self.canvas.active(), self.canvas.vram, unlit='unlit' in mode)
            except Exception as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))
