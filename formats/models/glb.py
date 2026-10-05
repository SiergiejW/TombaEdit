"""Self-contained glTF 2.0 export with embedded PSX textures."""
import io
import json
import struct
from pathlib import Path
import numpy as np
from psx.graphics import texture_page


def export_glb(path, meshes, vram, unlit=True):
    doc = dict(asset=dict(version="2.0", generator="TombaEdit"), scene=0,
               scenes=[dict(nodes=[])], nodes=[], meshes=[], materials=[],
               buffers=[], bufferViews=[], accessors=[], images=[], textures=[],
               samplers=[dict(magFilter=9728, minFilter=9728, wrapS=10497, wrapT=10497)],
               extensionsUsed=["KHR_materials_unlit"] if unlit else [])
    binary = bytearray()
    def view(data):
        binary.extend(b'\0' * (-len(binary) % 4))
        index = len(doc['bufferViews'])
        doc['bufferViews'].append(dict(buffer=0, byteOffset=len(binary), byteLength=len(data)))
        binary.extend(data)
        return index
    def accessor(array, typ, bounds=False):
        array = np.asarray(array, dtype='<f4')
        a = dict(bufferView=view(array.tobytes()), componentType=5126, count=len(array), type=typ)
        if bounds:
            a.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        index = len(doc['accessors'])
        doc['accessors'].append(a)
        return index
    materials = {}
    for mi, mesh in enumerate(meshes):
        primitives = []
        for key, (vertices, uv, colors) in mesh.batches.items():
            if not len(vertices):
                continue
            page, clut, semi = key
            key = ('image', id(mesh.image)) if mesh.image is not None else key
            if key not in materials:
                material = dict(name=f'Page {page:04X} CLUT {clut:04X}', doubleSided=True,
                                alphaMode='BLEND' if semi else 'MASK',
                                pbrMetallicRoughness=dict(metallicFactor=0, roughnessFactor=1))
                if unlit:
                    material['extensions'] = {'KHR_materials_unlit': {}}
                if page >= 0 or mesh.image is not None:
                    stream = io.BytesIO()
                    (mesh.image if mesh.image is not None else texture_page(vram, page, clut)).save(stream, format='PNG')
                    idx = len(doc['images'])
                    doc['images'].append(dict(bufferView=view(stream.getvalue()), mimeType='image/png'))
                    doc['textures'].append(dict(source=idx, sampler=0))
                    material['pbrMetallicRoughness']['baseColorTexture'] = dict(index=idx)
                materials[key] = len(doc['materials'])
                doc['materials'].append(material)
            attrs = dict(POSITION=accessor(vertices, 'VEC3', True),
                         COLOR_0=accessor(np.clip(colors, 0, 1), 'VEC3'))
            if page >= 0 or mesh.image is not None:
                attrs['TEXCOORD_0'] = accessor(uv, 'VEC2')
            primitives.append(dict(attributes=attrs, material=materials[key], mode=4))
        if primitives:
            index = len(doc['meshes'])
            doc['meshes'].append(dict(name=f'Object {mi:03d}', primitives=primitives))
            doc['scenes'][0]['nodes'].append(len(doc['nodes']))
            doc['nodes'].append(dict(mesh=index, name=f'Object {mi:03d} @ {mesh.offset:06X}'))
    doc['buffers'] = [dict(byteLength=len(binary))]
    blob = json.dumps(doc, separators=(',', ':')).encode('utf-8')
    blob += b' ' * (-len(blob) % 4)
    binary.extend(b'\0' * (-len(binary) % 4))
    output = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(blob) + 8 + len(binary))
    output += struct.pack('<II', len(blob), 0x4E4F534A) + blob
    output += struct.pack('<II', len(binary), 0x004E4942) + binary
    Path(path).write_bytes(output)
