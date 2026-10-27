"""PrePre 8's object ABI, read from its embedded executable routines.

800834D0 copies APD fields; 800240BC installs resource pointers. This
predates the retail layer numbers, sprite slots and model-pointer offset.
"""
import struct
from unicorn import UcError
from formats.level.runtime import OBJECT, SPR_MEMORY, WMD_MEMORY, BANK_SPACING

# playerInit at 80043960 loads this embedded TIM's palette to (1008, 480)
# and writes 783F to the player's +08. His one-part frames do not use the
# two-row outfit rule introduced in later builds.
PLAYER_TIM, PLAYER_CLUT = 0x800A8194, 0x783F


def upload_player_palette(project, path, vram):
    from game.builds import executable
    found = executable(project, path)
    if found is None or not found.build.legacy8:
        return
    at = PLAYER_TIM - found.base + 0x800
    # This embedded TIM is used for its CLUT only; its dummy pixel block
    # is not a valid standalone image. Validate and read the palette block.
    magic, flags, size, _, _, width, height = struct.unpack_from('<III4H', found.data, at)
    if (magic, flags, size, width, height) == (16, 8, 44, 16, 1):
        vram[480, 1008:1024] = struct.unpack_from('<16H', found.data, at + 20)


def attempt(resolver, placement, stop_at_animation):
    raw, obj = placement.raw, OBJECT
    resolver.stop_at_animation = stop_at_animation
    resolver.queued.clear()
    parents, parent = [], placement.parent
    while parent is not None and len(parents) < 32:
        resolver.resolve(parent)
        state = resolver.object_states.get((parent.raw, parent.position))
        if state is None:
            break
        parents.append((parent, state))
        parent = parent.parent
    cached_pose = resolver.object_states.get((raw, placement.position)) if parents else None
    resolver.write(0x80000000, resolver.baseline)
    resolver.write(0x1F800000, resolver.scratch)
    prepare_pools(resolver)
    for address, data in placement.memory:
        resolver.write(address, data)
    resolver.spawn(obj, placement)
    resolver.write(obj + 0x1C, bytes((placement.native_layer or {3: 4, 4: 5, 5: 6, 7: 8}.get(placement.layer, placement.layer),)))
    if placement.model in resolver.model_spans:
        resolver.word(obj + 0x9C, resolver.model_spans[placement.model][0])
        resolver.write(obj + 0xA0, b'\x01')
    for offset, value in placement.extra:
        resolver.write(obj + offset, value)
    articulated = resolver.handler_address(placement) == 0x8003832C
    children = []
    if articulated and placement.parent is None:
        node, previous = placement.child, obj
        while node is not None and len(children) < 32:
            address = OBJECT + 0x8000 + len(children) * 0x400
            resolver.spawn(address, node)
            resolver.write(address + 0x1C, bytes((node.native_layer,)))
            if node.model in resolver.model_spans:
                resolver.word(address + 0x9C, resolver.model_spans[node.model][0])
                resolver.write(address + 0xA0, b'\x01')
            resolver.word(previous + 0x94, address)
            resolver.word(address + 0x90, previous)
            children.append((node, address))
            previous, node = address, node.child
    if articulated and cached_pose is not None:
        for offset, size in ((0x10, 12), (0x84, 12), (0xA0, 1)):
            resolver.write(obj + offset, cached_pose[offset:offset + size])
    # APD modes 2/3 use the same +90 parent pointer as the later engine.
    # Preserve the live parent and its coordinate pointers for attached props.
    for n, (parent, state) in enumerate(parents):
        address = OBJECT + 0x4000 + n * 0x400
        resolver.write(address, state)
        for offset in (0x40, 0x44):
            pointer = struct.unpack_from('<I', state, offset)[0]
            if OBJECT <= pointer < OBJECT + 0x200:
                resolver.word(address + offset, address + pointer - OBJECT)
        resolver.word(address + 0x90, address + 0x400 if n + 1 < len(parents) else 0)
    if parents:
        resolver.word(obj + 0x90, OBJECT + 0x4000)
        resolver.word(OBJECT + 0x4000 + 0x94, obj)
        for j, value in enumerate(struct.unpack_from('<3h', raw, 6)):
            resolver.word(obj + 0x30 + j * 4, value << 16)
    pc = resolver.handler_address(placement)
    result = {}
    for step in range(16):
        try:
            resolver.run_handler(pc, obj, 12000)
        except UcError:
            pass
        state = resolver.read(obj, 0x200)
        sprite, anim = struct.unpack_from('<I', state, 0x3C)[0], struct.unpack_from('<I', state, 0x24)[0]
        model = struct.unpack_from('<I', state, 0x9C)[0]
        if model in resolver.model_pointers:
            if articulated and step == 0:
                # Naming the model precedes the first articulated-pose update.
                # That update enables normal lighting before submitting it.
                continue
            result = dict(model=resolver.model_pointers[model], lit=bool(state[0xA0]),
                          # +6C..72 is the collision box, not model scale.
                          # Rotated-model draw routine 80063E28 reads three
                          # 32-bit angles from +84/+88/+8C. Its matrix is
                          # unit scale; the early ABI has no retail scale here.
                          scale=(4096, 4096, 4096),
                          rotation=struct.unpack_from('<3i', state, 0x84))
            break
        if SPR_MEMORY <= sprite < WMD_MEMORY and (sprite - SPR_MEMORY) % BANK_SPACING == 0 and resolver.base <= anim < resolver.limit:
            if parents and step == 0 and not stop_at_animation:
                continue
            if state[0xD] & 1 and not struct.unpack_from('<H', state, 8)[0] and step < 15:
                # The house's candle glows receive their first cycling CLUT
                # after ten updates (80034B78), not in the initializer.
                continue
            frames = resolver.animation(anim)
            if frames:
                result = dict(sprite=(sprite-SPR_MEMORY)//BANK_SPACING, frame=frames[0][0], frames=frames,
                    animation_address=anim, flip=not state[0x2E]&1, tpage=struct.unpack_from('<H',state,0x1E)[0],
                    clut=struct.unpack_from('<H',state,8)[0] if state[0xD]&1 else None,
                    blend=bool(state[0xD]&0x80), shade=state[0x6B], sort_bias=0, sort_fixed=False,
                    sort_depth=struct.unpack_from('<h',state,0x1A)[0], screen_bias=0)
                if state[0xA] == 6:
                    # Draw routine 80061D5C projects these four SVECTORs,
                    # using only the first SPR part's UVs. It does not use
                    # the ordinary sprite rectangle or its facing flag.
                    result['quad'] = tuple(struct.unpack_from('<3h', state, 0x98 + i * 8)
                                           for i in range(4))
                break
    if result:
        if parents:
            result['position'] = tuple(v / 65536 for v in struct.unpack_from('<3i', state, 0x10))
        for child, address in children:
            resolver.object_states[child.raw, child.position] = resolver.read(address, 0x200)
        made = spawned(resolver)
        if made:
            result['spawned'] = made
        resolver.object_states[(raw, placement.position)] = state
        if placement.layer == 7 and 'sprite' in result:
            result.update(resolver.backdrop_motion(obj, pc, placement))
    return result


def matrix_vector(resolver):
    """Psy-Q ApplyMatrixLV: signed long vector through a 12-bit matrix."""
    r, uc = resolver.reg, resolver.u
    matrix, vector, target = (uc.reg_read(getattr(r, 'UC_MIPS_REG_' + name)) for name in ('A0', 'A1', 'A2'))
    rows = struct.unpack('<9h', resolver.read(matrix, 18))
    values = struct.unpack('<3i', resolver.read(vector, 12))
    output = [sum(rows[j * 3 + k] * values[k] for k in range(3)) >> 12 for j in range(3)]
    resolver.write(target, struct.pack('<3I', *(value & 0xFFFFFFFF for value in output)))
    uc.reg_write(r.UC_MIPS_REG_V0, target)
    uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))


def light_mesh(resolver, mesh):
    """Native NCCS lighting of the early untextured F/G primitives."""
    import numpy as np
    from formats.models.four import rebuild_mesh
    if not any(p.get('normals') for p in mesh.polygons):
        return mesh
    if not hasattr(resolver, '_model_light'):
        from psx.mips.cpu import CPU
        cpu = CPU()
        cpu.write(resolver.base, resolver.exe[0x800:])
        cpu.write(0x1F800268, struct.pack('<9hh3i', 4096, 0, 0, 0, 4096, 0, 0, 0, 4096, 0, 0, 0, 0))
        # Default light setup: native direction, colour matrix and ambient.
        cpu.call(0x8001AD2C, 0x803E1000, max_instr=20000, sp=0x803F8000)
        for k, value in enumerate(struct.unpack('<5I', cpu.read(0x803E1000, 20))):
            cpu.gte.write_ctrl(8 + k, value)
        resolver._model_light = cpu.gte
    gte = resolver._model_light
    polygons = []
    for p in mesh.polygons:
        normals = p.get('normals')
        if not normals:
            polygons.append(p)
            continue
        colors = []
        for x, y, z in normals:
            gte.write_data(0, (x & 65535) | (y & 65535) << 16)
            gte.write_data(1, z & 65535)
            gte.write_data(6, p['material'])
            gte.command(0x108041B)  # NCCS, as 8002B1C0 / 8002C2xx.
            rgb = gte.read_data(22)
            colors.append([(rgb >> shift & 255) / 255 for shift in (0, 8, 16)])
        if len(colors) == 1:
            colors *= len(p['vertices'])
        polygons.append(dict(p, colors=np.asarray(colors, np.float32)))
    result = rebuild_mesh(polygons, mesh.offset, mesh.image)
    result.front_clockwise = getattr(mesh, 'front_clockwise', True)
    return result


# Free-list layout read from allocators 8001A36C through 8001A74C.
# The tracer gives each pool spare objects, preserving its native type.
POOLS = (
    ('objects', 2, 80, 240), ('player', 3, 4, 240),
    ('objects', 4, 96, 216), ('models', 5, 128, 240),
    ('models', 9, 50, 160), ('objects', 6, 16, 220),
    ('models', 7, 50, 160), ('backdrops', 8, 10, 108),
    ('controllers', 0, 10, 60))


def prepare_pools(resolver):
    from formats.level.runtime import SPAWN_AT
    for k, (_name, native, slots, size) in enumerate(POOLS):
        start, listed = SPAWN_AT + k * 0x8000, 0x80CF0000 + k * 0x400
        resolver.write(start, bytes(slots * size))
        for i in range(slots):
            resolver.write(start + i * size + 0x1C, bytes((native,)))
        resolver.write(listed, struct.pack(f'<{slots}I', *(start + i * size for i in range(slots))))
        resolver.word(0x1F8002E8 + k * 4, listed)
        resolver.write(0x1F8002C6 + k * 2, struct.pack('<h', slots))


def spawned(resolver):
    from formats.level.runtime import SPAWN_AT
    out = []
    for k, (name, _native, slots, size) in enumerate(POOLS):
        start = SPAWN_AT + k * 0x8000
        pool = resolver.read(start, slots * size)
        for i in range(slots):
            if pool[i * size]:
                out.append((name, start + i * size, pool[i * size:(i + 1) * size]))
    return out
