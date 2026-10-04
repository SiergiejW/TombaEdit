"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QFontDatabase, QSurfaceFormat, QMatrix4x4
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QSpinBox, QSplitter, QListWidget, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QFileDialog, QMessageBox)
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
        self.textures = {}
        self.last = QPoint()
        self.camera_controls = CameraControls(self)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.selected = None
        self.pan = [0., 0.]
        self.fit()
        self.setMinimumSize(200, 200)

    def active(self):
        return self.meshes if self.index < 0 else [self.meshes[self.index]]

    def fit(self):
        arrays = [a[0] for m in self.active() for a in m.batches.values() if len(a[0])]
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
        for mesh in self.active():
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
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable(gl.GL_TEXTURE_2D)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
        if self.selected is not None:
            p = self.selected[1]
            order = [0, 1, 3, 2] if len(p['vertices']) == 4 else [0, 1, 2]
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glColor3f(1, 1, 0)
            gl.glLineWidth(2)
            gl.glBegin(gl.GL_LINE_LOOP)
            for i in order:
                gl.glVertex3f(*p['vertices'][i])
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
        polygons = [(i, p) for i, mesh in enumerate(self.meshes) if self.index < 0 or i == self.index for p in mesh.polygons]
        vertices, faces, lookup = [], [], []
        for pi, (_, p) in enumerate(polygons):
            base = len(vertices)
            vertices.extend(p['vertices'])
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
        bar = QHBoxLayout()
        self.canvas = MeshCanvas([], np.zeros((512, 1024), np.uint16))
        self.objects = QComboBox()
        self.objects.currentIndexChanged.connect(self.select)
        bar.addWidget(self.objects)
        for text, attr, state in [('Textures', 'textured', True), ('Vertex colours', 'colored', True), ('Wireframe', 'wireframe', False)]:
            box = QCheckBox(text)
            box.setChecked(state)
            box.toggled.connect(lambda value, name=attr: self.toggle(name, value))
            bar.addWidget(box)
        fit = QPushButton('Fit')
        fit.clicked.connect(self.canvas.fit)
        bar.addWidget(fit)
        export = QPushButton('Export GLB...')
        export.clicked.connect(self.export)
        bar.addWidget(export)
        layout.addLayout(bar)
        split = QSplitter()
        split.addWidget(self.canvas)
        side = QWidget()
        sl = QVBoxLayout(side)
        self.details = text_view('Click a triangle or quad to inspect its original WMD record and UVs.')
        sl.addWidget(self.details)
        self.uv = ImageView()
        sl.addWidget(self.uv)
        split.addWidget(side)
        split.setSizes([700, 280])
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

    def set_data(self, meshes, vram, code=0):
        self.canvas.cleanup()
        self.canvas.meshes, self.canvas.vram = meshes, vram
        self.canvas.selected = None
        self.objects.blockSignals(True)
        self.objects.clear()
        self.objects.addItem(f'All {len(meshes)} objects')
        for i, mesh in enumerate(meshes):
            self.objects.addItem(f'Object {i:03d} | @{mesh.offset:06X}')
        index = 1 if meshes and code not in (0x5080, 0x50FF) else 0
        self.objects.setCurrentIndex(index)
        self.objects.blockSignals(False)
        self.select(index)
        triangles = sum(len(a[0]) // 3 for m in meshes for a in m.batches.values())
        self.stats.setText(f'{triangles:,} triangles | {sum(len(m.polygons) for m in meshes):,} original polygons')
        self.show_polygon(None)

    def select(self, index):
        self.canvas.index = index - 1
        self.canvas.selected = None
        self.canvas.fit()

    def toggle(self, name, value):
        setattr(self.canvas, name, value)
        self.canvas.update()

    def show_polygon(self, selected):
        if selected is None:
            self.details.setPlainText('Click a triangle or quad to inspect its UVs.\n\nGLB exports the selected object or all objects, with embedded textures and vertex colours.\nPSX blend equations and overbright colours are approximated in glTF.')
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
        path, _ = QFileDialog.getSaveFileName(self, 'Export geometry', 'model.glb', 'glTF binary (*.glb)')
        if path:
            try:
                from formats.models.glb import export_glb
                export_glb(path, self.canvas.active(), self.canvas.vram)
            except Exception as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))
