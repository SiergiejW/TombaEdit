"""Classic Qt image, dialogue, sprite and interactive OpenGL mesh viewers."""
import math
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QFontDatabase, QSurfaceFormat, QMatrix4x4, QAction, QShortcut, QKeySequence
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QPushButton, QSpinBox, QSplitter, QListWidget, QPlainTextEdit,
    QGraphicsView, QGraphicsScene, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QToolBar, QStyle, QInputDialog)
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from psx.graphics import texture_page, render_sprite



from gui.widgets.image_view import ImageView, text_view, qimage

from gui.widgets.camera_controls import (CameraControls, CameraEventMixin, CONTROLS_HINT,
    MODEL_HEADING, MODEL_PITCH, FIELD_OF_VIEW)
from gui.widgets.polygon_pick import ray_through, nearest_polygon
from gui.theme import view_background

# Downward tilt a level opens with, close to the game's own camera.
LEVEL_TILT = 10.0
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
        self.selected_model = None
        self.pan = [0., 0.]
        # Opening pose. The game looks along +Z with Y down, which after the
        # (x, -y, -z) conversion is the camera's own forward direction.
        self.view_angles = (MODEL_HEADING, MODEL_PITCH)
        self.view_margin = 1.25
        self.orbit_selection = True
        self.camera_controls.orbit_target = self.orbit_target
        # Optional GL_LINES overlay: (vertices, colours).
        self.lines = None
        self.show_lines = False
        self.selection_lines = None
        self.line_picker = None
        # Dim everything but the selected model. The level editor turns this
        # off: a scene is read as a whole.
        self.highlight = True
        # Screen-space sprites behind the scene: [(index, Backdrop)].
        self.backdrop = []
        self.sky = None
        self.show_backdrop = True
        self.stats_label = QLabel(self)
        self.stats_label.setObjectName('viewerOverlay')
        self.stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.controls_label = QLabel(CONTROLS_HINT + '\nF: frame selected | Double-click a row: frame it', self)
        self.controls_label.setObjectName('viewerOverlay')
        self.controls_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.stats_label.raise_(); self.controls_label.raise_()
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

    def box(self, indices=None):
        """(low, high) corners of the visible meshes, or of `indices` among them."""
        arrays = [batch[0] + self.offset_for(i)
                  for i, mesh in enumerate(self.meshes) if i in self.visible
                  and (indices is None or i in indices)
                  for batch in mesh.batches.values() if len(batch[0])]
        if not arrays:
            return None
        return (np.min([a.min(axis=0) for a in arrays], axis=0),
                np.max([a.max(axis=0) for a in arrays], axis=0))

    def bounds(self, indices=None):
        """(centre, radius) of the same."""
        found = self.box(indices)
        if found is None:
            return None
        lo, hi = found
        return (lo + hi) / 2, max(1., float(np.linalg.norm(hi - lo)) / 2)

    def fit(self, indices=None, animate=True):
        # Qt hands a button's "checked" flag to whatever slot it is wired to.
        if not isinstance(indices, (set, frozenset, list, tuple)):
            indices = None
        self.center, self.radius = self.bounds(indices) or (np.zeros(3), 1.)
        camera = self.camera_controls
        heading, pitch = self.view_angles
        margin = self.view_margin
        found = self.box(indices)
        if found is not None:
            # The opening pose looks along Z, so X and Y are what has to fit
            # the viewport; a wide level in a narrow pane needs more distance
            # than its radius suggests, and a flat one less.
            width, height, depth = (float(v) for v in found[1] - found[0])
            half = math.tan(math.radians(FIELD_OF_VIEW) / 2)
            aspect = self.width() / max(1, self.height())
            distance = max(height / 2 / half, width / 2 / (half * aspect)) * 1.08 + depth / 2
            margin = max(distance, self.radius * 0.2) / (self.radius * 1.2)
        frame = camera.glide_frame if animate else camera.frame
        frame(self.center, self.radius, heading=heading, pitch=pitch, margin=margin)
        # Until the camera is moved by hand, a resize keeps everything framed.
        self.auto_fit = indices is None
        if indices is not None:
            # Framing one object must not pull the clip planes in around it.
            whole = self.bounds()
            if whole:
                self.radius = max(self.radius, whole[1])
        self.update()

    def orbit_target(self):
        """Centre of the selected model while Orbit selection is on."""
        if not self.orbit_selection or self.selected_model is None:
            return None
        found = self.bounds({self.selected_model})
        return tuple(float(v) for v in found[0]) if found else None

    def set_mesh(self, index, mesh):
        """Swap one mesh in place, as an animation step does."""
        if 0 <= index < len(self.meshes) and self.meshes[index] is not mesh:
            if self.selected is not None and self.selected[0] == index:
                # Carry the selection over to the same polygon of the new mesh.
                old = self.meshes[index].polygons
                at = next((n for n, polygon in enumerate(old) if polygon is self.selected[1]), 0)
                self.selected = (index, mesh.polygons[min(at, len(mesh.polygons) - 1)]) if mesh.polygons else None
            self.meshes[index] = mesh
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, 'auto_fit', False):
            self.fit(animate=False)
        self.stats_label.adjustSize()
        self.stats_label.move(6, 6)
        self.controls_label.adjustSize()
        self.controls_label.move(self.width() - self.controls_label.width() - 6,
                                 self.height() - self.controls_label.height() - 6)

    def wheelEvent(self, event):
        self.auto_fit = False
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F:
            self.fit({self.selected_model} if self.selected_model is not None else None)
            event.accept()
            return
        super().keyPressEvent(event)

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
        gl.glClearColor(*(self.sky if self.sky and self.show_backdrop else view_background()), 1)
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
        if self.backdrop and self.show_backdrop:
            self.paint_backdrop(gl)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_LINE if self.wireframe else gl.GL_FILL)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        for i, mesh in enumerate(self.meshes):
            if i not in self.visible:
                continue
            gl.glPushMatrix()
            gl.glTranslatef(*self.offset_for(i))
            for (page, clut, semi), (vertices, uv, colors) in mesh.batches.items():
                use_texture = self.textured and (page >= 0 or mesh.image is not None)
                if use_texture:
                    key = ('image', id(mesh.image)) if mesh.image is not None else (page, clut)
                    if key not in self.textures:
                        im = mesh.image if mesh.image is not None else texture_page(self.vram, page, clut)
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
                if self.highlight and self.selected_model is not None and i != self.selected_model:
                    draw_colors = np.ascontiguousarray(draw_colors * 0.24)
                gl.glColorPointer(3, gl.GL_FLOAT, 0, draw_colors)
                gl.glVertexPointer(3, gl.GL_FLOAT, 0, vertices)
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, len(vertices))
            gl.glPopMatrix()
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable(gl.GL_TEXTURE_2D)
        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
        if self.show_lines and self.lines is not None:
            vertices, colors = self.lines
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glEnable(gl.GL_BLEND)
            gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
            gl.glEnable(gl.GL_LINE_SMOOTH)
            gl.glLineWidth(1.5)
            gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
            gl.glEnableClientState(gl.GL_COLOR_ARRAY)
            gl.glVertexPointer(3, gl.GL_FLOAT, 0, vertices)
            gl.glColorPointer(3, gl.GL_FLOAT, 0, colors)
            gl.glDrawArrays(gl.GL_LINES, 0, len(vertices))
            if self.selection_lines is not None:
                gl.glDisableClientState(gl.GL_COLOR_ARRAY)
                gl.glColor3f(1., 1., .1)
                gl.glLineWidth(3)
                selected = np.asarray(self.selection_lines, np.float32)
                gl.glVertexPointer(3, gl.GL_FLOAT, 0, selected)
                gl.glDrawArrays(gl.GL_LINES, 0, len(selected))
            gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
            gl.glDisableClientState(gl.GL_COLOR_ARRAY)
            gl.glDisable(gl.GL_LINE_SMOOTH)
            gl.glDisable(gl.GL_BLEND)
            gl.glEnable(gl.GL_DEPTH_TEST)
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

    def image_texture(self, gl, image):
        key = ('image', id(image))
        if key not in self.textures:
            texture = int(gl.glGenTextures(1))
            self.textures[key] = texture
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, image.width, image.height, 0,
                            gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, image.tobytes())
        return self.textures[key]

    def paint_backdrop(self, gl):
        """Layer 7 sprites on a 320 x 240 screen that fills the view's height.

        The game places each from the camera position scaled by the sprite's
        own factor, so distant scenery drifts slowly. Here the backdrop is
        treated as scenery a long way off: sliding the camera sideways
        scrolls each sprite by its factor, turning the camera carries the
        whole backdrop across the view, and looking up or down moves it down
        or up, at the rate the view itself turns. Moving towards or away from
        the level leaves it alone."""
        aspect = self.width() / max(1, self.height())
        width = 240 * aspect
        c = self.camera_controls
        heading = math.radians(c.camera_angle_h)
        # How far the camera stands along its own right-hand axis.
        sideways = -c.camera_x * math.cos(heading) - c.camera_z * math.sin(heading)
        per_degree = 240 / FIELD_OF_VIEW
        turned = (c.camera_angle_h * per_degree, c.camera_angle_v * per_degree)
        camera = (sideways - 160, 0)
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glPushMatrix()
        gl.glLoadIdentity()
        gl.glOrtho((320 - width) / 2, (320 + width) / 2, 240, 0, -1, 1)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPushMatrix()
        gl.glLoadIdentity()
        gl.glDisable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glTexEnvi(gl.GL_TEXTURE_ENV, gl.GL_TEXTURE_ENV_MODE, gl.GL_REPLACE)
        for index, sprite in self.backdrop:
            if index not in self.visible:
                continue
            # Whole pixels, so neighbouring strips meet without seams.
            x = math.floor(sprite.screen[0] - camera[0] * sprite.follow[0] - turned[0]) + sprite.left
            y = math.floor(sprite.screen[1] - camera[1] * sprite.follow[1] - turned[1]) + sprite.top
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.image_texture(gl, sprite.image))
            gl.glColor3f(1, 1, 1)
            low = (320 - width) / 2
            if sprite.period:
                # Looping scenery: every copy that reaches into the view.
                first = x - math.ceil((x + sprite.image.width - low) / sprite.period) * sprite.period + sprite.period
                copies = [first + n * sprite.period for n in range(int(width // sprite.period) + 2)]
            else:
                copies = [x]
            gl.glBegin(gl.GL_QUADS)
            for at in copies:
                for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    gl.glTexCoord2f(u, v)
                    gl.glVertex2f(at + u * sprite.image.width, y + v * sprite.image.height)
            gl.glEnd()
        gl.glTexEnvi(gl.GL_TEXTURE_ENV, gl.GL_TEXTURE_ENV_MODE, gl.GL_MODULATE)
        gl.glDisable(gl.GL_TEXTURE_2D)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glPopMatrix()
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glPopMatrix()
        gl.glMatrixMode(gl.GL_MODELVIEW)

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
            self.auto_fit = False
            return super().mousePressEvent(event)
        if self.show_lines and self.line_picker is not None and self.line_picker(event.position()):
            return
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
        self.export_name = ''       # default file name for exports, set by the window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar = QToolBar(self)
        self.toolbar.setObjectName('viewerToolbar')
        self.toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.toolbar.setMovable(False)
        self.canvas = MeshCanvas([], np.zeros((512, 1024), np.uint16))
        shortcut = QShortcut(QKeySequence('F'), self)
        shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.frame_current)
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
        self.culling_action = add_action(QStyle.StandardPixmap.SP_DialogNoButton,
            'Backface Culling', lambda value: self.toggle('backface_culling', value), False)
        self.spread_action = add_action(QStyle.StandardPixmap.SP_FileDialogDetailedView,
            'Spread Parts', self.toggle_spread, True)
        self.spread_action.setToolTip('Lay every model on a numbered grid, as in the Tomba2Edit SMST viewer.')
        add_action(QStyle.StandardPixmap.SP_FileDialogContentsView,
            'Frame Model', lambda: self.canvas.fit())
        self.orbit_action = add_action(QStyle.StandardPixmap.SP_BrowserReload,
            'Orbit Selection', lambda value: setattr(self.canvas, 'orbit_selection', value), True)
        self.orbit_action.setToolTip('Middle-drag circles the selected model. Turn off to orbit '
                                     'whatever is in the middle of the view.')
        self.origin_action = add_action(QStyle.StandardPixmap.SP_ArrowUp,
            'Origin', lambda value: self.toggle('show_origin', value), False)
        add_action(QStyle.StandardPixmap.SP_DialogOpenButton,
            'Export glTF', self.export)
        layout.addWidget(self.toolbar)
        split = QSplitter()
        left = QWidget()
        left.setMinimumWidth(320)
        ll = QVBoxLayout(left)
        ll.addWidget(QLabel('Models'))
        self.objects = QTableWidget(0, 5)
        self.objects.setHorizontalHeaderLabels(['Show', 'Model', 'Tris', 'Quads', 'Offset'])
        self.objects.verticalHeader().hide()
        self.objects.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.objects.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.objects.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.objects.setColumnWidth(0, 40)
        self.objects.setColumnWidth(2, 43)
        self.objects.setColumnWidth(3, 49)
        self.objects.setColumnWidth(4, 78)
        self.objects.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.objects.itemChanged.connect(self.visibility_changed)
        self.objects.currentCellChanged.connect(self.model_selected)
        self.objects.cellDoubleClicked.connect(self.frame_selected)
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
        side.setMinimumWidth(210)
        sl = QVBoxLayout(side)
        self.details = text_view('Click a triangle or quad to inspect its original WMD record and UVs.')
        sl.addWidget(self.details)
        self.uv = ImageView()
        sl.addWidget(self.uv)
        split.addWidget(side)
        split.setSizes([280, 680, 300])
        layout.addWidget(split, 1)
        self.canvas.picked.connect(self.show_polygon)
        if meshes is not None:
            self.set_data(meshes, vram, code)

    def set_data(self, meshes, vram, code=0, names=None, rename_callback=None, level=None):
        self.rename_callback = rename_callback
        self.model_names = names or {}
        had_meshes = bool(self.canvas.meshes)
        self.canvas.cleanup()
        self.canvas.meshes, self.canvas.vram = list(meshes), vram
        self.canvas.lines = None
        self.canvas.selection_lines = None
        self.canvas.backdrop = []
        self.canvas.sky = None
        # Level geometry opens from slightly above; single models square on.
        level = code in (0x5080, 0x50FF) if level is None else level
        self.canvas.view_angles = (MODEL_HEADING, LEVEL_TILT if level else MODEL_PITCH)
        self.canvas.view_margin = 1.0 if level else 1.25
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
        self.canvas.selected_model = None
        self.spread_action.blockSignals(True)
        self.spread_action.setChecked(code not in (0x5080, 0x50FF))
        self.spread_action.blockSignals(False)
        self.canvas.spread = self.spread_action.isChecked()
        if meshes:
            self.objects.setCurrentCell(0, 0)
        self.objects.blockSignals(False)
        self.canvas.fit(animate=False)
        triangles = sum(len(a[0]) // 3 for m in meshes for a in m.batches.values())
        self.canvas.stats_label.setText(f'{triangles:,} triangles | {len(meshes):,} models\n'
                                        'F: frame selected')
        self.canvas.stats_label.adjustSize()
        self.canvas.stats_label.move(6, 6)
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
        self.canvas.selected_model = row if row >= 0 else None
        self.show_polygon(None)
        self.canvas.update()
        if 0 <= row < len(self.canvas.meshes) and self.objects.item(row, 4):
            print('selected: ' + self.describe(row))

    def describe(self, row):
        return (f'{self.objects.item(row, 1).text()} | '
                f'{self.objects.item(row, 2).text()} triangles, {self.objects.item(row, 3).text()} quads '
                f'@ {self.objects.item(row, 4).text()}')

    def frame_selected(self, row, column):
        if row < 0:
            return
        self.canvas.selected_model = row
        self.canvas.fit({row})

    def frame_current(self):
        self.canvas.fit({self.canvas.selected_model} if self.canvas.selected_model is not None else None)

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
        # Nothing stays dimmed: showing everything also lets go of the selection.
        self.objects.blockSignals(True)
        self.objects.clearSelection()
        self.objects.setCurrentCell(-1, -1)
        self.objects.blockSignals(False)
        self.canvas.selected = self.canvas.selected_model = None
        self.show_polygon(None)
        self.canvas.update()

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

    def show_polygon(self, selected, announce=True):
        if selected is None:
            self.details.setPlainText('Click a triangle or quad to inspect its UVs.\n\nGLB exports visible models with embedded textures and vertex colours.\nPSX blend equations and overbright colours are approximated in glTF.')
            self.uv.set_image(Image.new('RGBA', (1, 1)))
            return
        index, p = selected
        texels = [(round(u * 256 - .5), round(v * 256 - .5)) for u, v in p['uv']]
        if announce:
            print(f"selected: model {index:03d} {p['kind']} @ 0x{p['offset']:X} | page 0x{p['page'] & 0xFFFF:04X} "
                  f"CLUT 0x{p['clut']:04X} | UV {texels}")
        self.details.setPlainText(f"Object {index:03d} | {p['kind']}\nRecord @ 0x{p['offset']:X}\nPage: 0x{p['page']:04X}\nCLUT: 0x{p['clut']:04X}\nGPU command: 0x{p['command']:02X}\n\nUV: {texels}\n\nVertices: {p['vertices']}")
        image = texture_page(self.canvas.vram, p['page'], p['clut']).copy() if p['page'] >= 0 else Image.new('RGBA', (256, 256), (32, 32, 32, 255))
        order = [0, 1, 3, 2, 0] if len(texels) == 4 else [0, 1, 2, 0]
        ImageDraw.Draw(image).line([texels[i] for i in order], fill='yellow', width=1)
        self.uv.set_image(image)
        # Bring the outlined texels into view.
        xs, ys = [t[0] for t in texels], [t[1] for t in texels]
        self.uv.show_area(min(xs), min(ys), max(xs), max(ys))

    def export(self):
        from gui.widgets.image_view import file_stem
        shown = sorted(self.canvas.visible)
        names = [self.objects.item(row, 1).text() for row in shown if self.objects.item(row, 1)]
        # Named after the open resource, and after the model when one is exported alone.
        stem = self.export_name + (f' - {names[0]}' if len(names) == 1 and self.objects.rowCount() > 1 else '')
        path, mode = QFileDialog.getSaveFileName(self, 'Export geometry', file_stem(stem, 'model') + '.glb',
            'GLB (unlit, game colours) (*.glb);;GLB (lit, external lighting) (*.glb)')
        if path:
            try:
                from formats.models.glb import export_glb
                export_glb(path, self.canvas.active(), self.canvas.vram, unlit='unlit' in mode, names=names)
                print(f'wrote {path}: {len(names)} models')
            except Exception as exc:
                QMessageBox.warning(self, 'Export failed', str(exc))
