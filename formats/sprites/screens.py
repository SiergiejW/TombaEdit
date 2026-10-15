"""Sprite setup performed by system screen code, separate from area objects."""
import struct
import numpy as np
from formats.archive.ldar import system_table
from formats.level.runtime import InitialPoseResolver, SPR_MEMORY, BANK_SPACING, OBJECT
from formats.level.palettes import constant_uploads


def screen_bank(project, path, index, slot, frames):
    cache = project.__dict__.setdefault('screen_sprite_cache', {})
    key = (path, index, slot)
    if key in cache:
        return cache[key]
    from formats.level.scene import loaded_resources, area_of
    resources = loaded_resources(project, path, 0).copy()
    group = project.ldars[system_table(path)][index]
    for asset in group.assets:
        resources[asset.kind, asset.slot] = asset
    resolver = InitialPoseResolver(project, area_of(path), 0, resources)
    vram = project.vram(path, 0, index)
    pages, cluts = {}, {}
    if resolver.available:
        code, build = resolver.overlay_code, resolver.build
        load_image = build.get_clut + 0xFA0
        if resolver.read(load_image, 4) == bytes.fromhex('e0ffbd27'):
            for x, y, w, h, pixels in constant_uploads(code, build.overlay, load_image, screen=True):
                vram[y:y + h, x:x + w] = np.frombuffer(pixels, '<u2').reshape(h, w)
        words = np.frombuffer(code[:len(code) // 4 * 4], '<u4')
        # Start at a function boundary, never at the bank load itself. Leaf
        # initializers can have no stack frame, so include the preceding return.
        starts = set()
        offset = 0x2C8 + slot * 4
        for i in np.flatnonzero((words >> 26 == 35) & (words & 0xFFFF == offset)):
            for j in range(int(i), max(-1, int(i) - 150), -1):
                if int(words[j]) >> 16 == 0x27BD and int(words[j]) & 0x8000:
                    starts.add(j)
                    break
            for j in range(int(i) - 2, max(-1, int(i) - 150), -1):
                if int(words[j]) == 0x03E00008:
                    starts.add(j + 2)
                    break
        pointer = SPR_MEMORY + slot * BANK_SPACING
        from unicorn import UcError
        for start in sorted(starts):
            resolver.write(0x80000000, resolver.baseline)
            resolver.write(0x1F800000, resolver.scratch)
            resolver.write(OBJECT, bytes(0x200))
            try:
                resolver.run_handler(build.overlay + start * 4, OBJECT, 4000)
            except UcError:
                continue
            ram = np.frombuffer(resolver.read(0x80000000, 0x200000), '<u4')
            for word in np.flatnonzero(ram == pointer):
                address = 0x80000000 + int(word) * 4 - 0x3C
                if not build.overlay <= address < build.overlay + len(code) - 0x40:
                    continue
                state = resolver.read(address, 0x40)
                animation = struct.unpack_from('<I', state, 0x24)[0]
                if not resolver.base <= animation < resolver.limit:
                    continue
                page = struct.unpack_from('<H', state, 0x1E)[0]
                if page >= 512:
                    continue
                steps = resolver.animation(animation)
                if not steps or any(frame >= len(frames) for frame, _ in steps):
                    continue
                clut = struct.unpack_from('<H', state, 8)[0] & 0x7FFF if state[13] & 1 else None
                for frame, _ in steps:
                    pages.setdefault(frame, page)
                    if clut is not None:
                        cluts.setdefault(frame, clut)
    result = (vram, pages, cluts)
    cache[key] = result
    return result
