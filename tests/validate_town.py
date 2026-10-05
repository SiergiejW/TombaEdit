"""Compare town sprite settings with the actual US overlay initializer.

Usage: python -m tests.validate_town path/to/disc.cue
The disc is supplied locally and is not part of the repository.
"""
import struct
import sys
from formats.archive.ldar import Project
from formats.level.scene import loaded_resources, build_scene
from formats.level.runtime import InitialPoseResolver
from formats.level.town import dwarf_graphics, town_graphics
from psx.graphics import sprite_frames, render_sprite


def main(path):
    project = Project(path)
    resources = loaded_resources(project, 'SYS/LDAR02.BIN', 1)
    profile = dwarf_graphics(project, resources, 2, 0)
    resolver = InitialPoseResolver(project, 2, 0, resources)
    assert profile is not None and resolver.available, 'Verified US retail is required'
    obj, r = 0x80300000, resolver.reg
    comparisons = 0
    for variant in range(24):
        # The scripts select one of three styles. Run the initializer with
        # that style and compare its resulting frame/page/palette to the
        # decoder, rather than repeating the decoder's table reads.
        style = 0 if variant < 17 else 1 if variant == 17 else 2
        resolver.write(0x80000000, resolver.baseline)
        resolver.write(0x1F800000, resolver.scratch)
        resolver.write(obj, bytes(0x200))
        resolver.write(obj + 3, bytes([style]))
        resolver.write(obj + 0x74, struct.pack('<h', variant))
        resolver.write(obj + 0x2E, b'\x01\x00')
        resolver.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
        resolver.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
        resolver.u.reg_write(r.UC_MIPS_REG_A0, obj)
        resolver.u.emu_start(0x800E7780, 0x80001000, count=4000)
        state = resolver.read(obj, 0x40)
        script = resolver.read_word(obj + 0x24)
        frame = struct.unpack('<H', resolver.read(script, 2))[0]
        page = struct.unpack_from('<H', state, 0x1E)[0]
        clut = struct.unpack_from('<H', state, 8)[0]
        assert profile.pages[frame] == page, (variant, frame, page)
        assert profile.cluts[frame] == clut, (variant, frame, hex(clut))
        assert resolver.read_word(obj + 0x3C) == 0x80400000 + 11 * 0x40000
        comparisons += 1
    assert all(profile.pages[frame] == 16 and frame not in profile.cluts for frame in range(425, 431))
    assert dwarf_graphics(project, resources, 2, 1) is None
    frames = sprite_frames(project.asset_data(resources['SPR', 11]))
    vram = project.vram('SYS/LDAR02.BIN', 1)
    scene = build_scene(project, 'SYS/LDAR02.BIN', 1)
    assert len(scene.town_views) == 3
    for (_, preview), (_, frame) in zip(scene.town_views, profile.houses):
        expected = render_sprite(frames[frame], vram, tpage=profile.pages[frame], clut=profile.cluts[frame])
        assert expected.getbbox() and expected.tobytes() == preview.entries[0].mesh.image.tobytes()
        assert preview.entries[0].source is resources['SPR', 11]
    views = 3
    # INFO2 has a different object layout, bank and palette selection from
    # Dwarf Village. Trace both Baccus variants and Hidden independently.
    for area, group in ((5, 1), (5, 3), (19, 3)):
        path = f'SYS/LDAR{area:02}.BIN'
        resources = loaded_resources(project, path, group)
        profile = town_graphics(project, resources, area, group - 1)
        assert profile is not None and profile.bank == 13
        resolver = InitialPoseResolver(project, area, group - 1, resources)
        r = resolver.reg
        for frame in profile.pages:
            resolver.write(0x80000000, resolver.baseline)
            resolver.write(0x1F800000, resolver.scratch)
            resolver.write(obj, bytes(0x200))
            resolver.write(obj + 0xB4, struct.pack('<H', frame))
            resolver.write(obj + 0xB6, struct.pack('<H', int(area == 5 and frame >= 9)))
            resolver.write(obj + 0x2E, b'\x01\x00')
            resolver.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
            resolver.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
            resolver.u.reg_write(r.UC_MIPS_REG_A0, obj)
            resolver.u.emu_start(0x800EF658 if area == 5 else 0x800F03E0,
                                 0x80001000, count=4000)
            script = resolver.read_word(obj + 0x24)
            assert struct.unpack('<H', resolver.read(script, 2))[0] == frame
            assert struct.unpack('<H', resolver.read(obj + 0x1E, 2))[0] == profile.pages[frame]
            assert struct.unpack('<H', resolver.read(obj + 8, 2))[0] == profile.cluts[frame]
            assert resolver.read_word(obj + 0x3C) == 0x80400000 + 13 * 0x40000
            comparisons += 1
        scene = build_scene(project, path, group)
        assert len(scene.town_views) == (2 if area == 5 else 3)
        frames = sprite_frames(project.asset_data(resources['SPR', profile.bank]))
        vram = project.vram(path, group)
        for (_, preview), (_, frame) in zip(scene.town_views, profile.houses):
            expected = render_sprite(frames[frame], vram,
                                     tpage=profile.pages[frame], clut=profile.cluts[frame])
            assert expected.getbbox() and expected.tobytes() == preview.entries[0].mesh.image.tobytes()
            assert preview.entries[0].source is resources['SPR', 13]
        views += len(scene.town_views)
    variant = build_scene(project, 'SYS/LDAR19.BIN', 1)
    assert len(variant.town_views) == 3
    views += 3
    # Pier uses the same overlay and loads Dwarf's NPC bank, but its scenery
    # is fences. Central Park and the Elder's Hut have their own sections.
    for area, group in ((8, 1), (8, 3), (5, 2), (19, 2), (2, 2)):
        path = f'SYS/LDAR{area:02}.BIN'
        assert town_graphics(project, loaded_resources(project, path, group), area, group - 1) is None
        assert not build_scene(project, path, group).town_views
    print(f'PASS: {comparisons} overlay initializer comparisons, {views} room views across five town contexts; '
          'Pier and adjacent sections excluded')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'rom/Tomba! (USA).cue')
