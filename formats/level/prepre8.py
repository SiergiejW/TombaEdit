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
    parents, parent = [], placement.parent
    while parent is not None and len(parents) < 32:
        resolver.resolve(parent)
        state = resolver.object_states.get((parent.raw, parent.position))
        if state is None:
            break
        parents.append((parent, state))
        parent = parent.parent
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
        children = spawned(resolver)
        if children:
            result['spawned'] = children
        resolver.object_states[(raw, placement.position)] = state
        if placement.layer == 7 and 'sprite' in result:
            result.update(resolver.backdrop_motion(obj, pc, placement))
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
