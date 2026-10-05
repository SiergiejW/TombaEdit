"""Scene transforms, panorama continuity and outward model export."""
import json
import struct
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
from formats.level.presentation import model_vertices, panorama_layers, panorama_position
from formats.level.scene import Backdrop
from formats.models.winding import closed_winding
from formats.models.glb import export_glb


class PresentationTests(unittest.TestCase):
    def test_psx_scale_and_quarter_turn_before_translation(self):
        # A point on raw +X becomes raw +Z after a 3072-unit Y rotation.
        result = model_vertices([[48, 0, 0]], (2625, -286, 221),
                                (3072, 3072, 3072), (0, 3072, 0))
        np.testing.assert_allclose(result, [[2625, 286, -257]], atol=1e-4)
        np.testing.assert_allclose(model_vertices([[1, 2, 3]], (10, 20, 30)),
                                   [[11, -18, -27]])

    def test_strips_stitch_and_wrapped_edge_is_preserved(self):
        strips = [(0, Backdrop(Image.new('RGBA', (4, 6), 'red'), 0, 0,
                              (0, 0, 0), (0, 0), (.25, .25), 8)),
                  (1, Backdrop(Image.new('RGBA', (4, 6), 'blue'), 0, 0,
                              (0, 0, 0), (6, 0), (.25, .25), 8))]
        layer, = panorama_layers(strips, {0, 1})
        self.assertEqual(layer.image.size, (8, 6))
        self.assertEqual(layer.image.getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(layer.image.getpixel((2, 0)), (255, 0, 0, 255))
        hidden, = panorama_layers(strips, {0})
        self.assertEqual([p[0] for p in hidden.parts], [0])

    def test_panorama_horizon_height_pitch_stops_and_full_turn(self):
        strip = Backdrop(Image.new('RGBA', (512, 240), 'blue'), 0, 0,
                         (0, 0, 0), (0, 0), (.25, .25), 512)
        layer, = panorama_layers([(0, strip)], {0})
        original = panorama_position(layer, (30, -500, 900), 0, 0)
        self.assertEqual(original, panorama_position(layer, (30, 7000, -900), 360, 0))
        self.assertEqual(original[1], 0)
        self.assertEqual(panorama_position(layer, (0, 0, 0), 0, 60),
                         panorama_position(layer, (0, 0, 0), 0, 90))
        self.assertEqual(panorama_position(layer, (0, 0, 0), 0, -60),
                         panorama_position(layer, (0, 0, 0), 0, -90))


class WindingTests(unittest.TestCase):
    def tetrahedron(self, clockwise=False):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], np.float32)
        faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])
        if clockwise:
            faces = faces[:, [0, 2, 1]]
        points = vertices[faces].reshape(-1, 3)
        return SimpleNamespace(batches={(-1, 0, False): (points, None, None)})

    def test_closed_orientation_is_translation_independent(self):
        for clockwise in (False, True):
            mesh = self.tetrahedron(clockwise)
            self.assertEqual(closed_winding([mesh]), clockwise)
            mesh.batches[(-1, 0, False)][0][:] += [2630, -301, 732]
            self.assertEqual(closed_winding([mesh]), clockwise)

    def test_open_mesh_does_not_claim_an_outside(self):
        mesh = self.tetrahedron()
        mesh.batches[(-1, 0, False)] = (mesh.batches[(-1, 0, False)][0][:-3], None, None)
        self.assertIsNone(closed_winding([mesh]))

    def test_duplicate_inward_panels_do_not_break_closed_shell(self):
        mesh = self.tetrahedron()
        triangles = mesh.batches[(-1, 0, False)][0].reshape(-1, 3, 3)
        mesh.polygons = [dict(vertices=points) for points in triangles]
        mesh.polygons += [dict(vertices=points[[0, 2, 1]]) for points in triangles]
        self.assertFalse(closed_winding([mesh]))

    def test_lit_export_reorders_uv_colours_with_vertices_and_normals(self):
        vertices = np.array([[0, 0, 0], [0, 1, 0], [1, 0, 0]], np.float32)
        uv = np.array([[0, 0], [0, 1], [1, 0]], np.float32)
        colors = np.eye(3, dtype=np.float32)
        mesh = SimpleNamespace(batches={(-2, 0, False): (vertices, uv, colors)},
                               image=Image.new('RGBA', (1, 1), 'white'), offset=0,
                               front_clockwise=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'model.glb'
            export_glb(path, [mesh], None, unlit=False)
            data = path.read_bytes()
        size = struct.unpack_from('<I', data, 12)[0]
        doc = json.loads(data[20:20 + size])
        blob = data[28 + size:]
        attrs = doc['meshes'][0]['primitives'][0]['attributes']
        def read(name, dimensions):
            accessor = doc['accessors'][attrs[name]]
            view = doc['bufferViews'][accessor['bufferView']]
            return np.frombuffer(blob, '<f4', accessor['count'] * dimensions,
                                 view['byteOffset']).reshape(-1, dimensions)
        np.testing.assert_array_equal(read('POSITION', 3), vertices[[0, 2, 1]])
        np.testing.assert_array_equal(read('TEXCOORD_0', 2), uv[[0, 2, 1]])
        np.testing.assert_array_equal(read('COLOR_0', 3), colors[[0, 2, 1]])
        np.testing.assert_array_equal(read('NORMAL', 3), [[0, 0, 1]] * 3)


if __name__ == '__main__':
    unittest.main()
