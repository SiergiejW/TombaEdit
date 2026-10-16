"""PrePre 8's object ABI, read from its embedded executable routines.

800834D0 copies APD fields; 800240BC installs resource pointers. This
predates the retail layer numbers, sprite slots and model-pointer offset.
"""
import struct
from unicorn import UcError
from formats.level.runtime import OBJECT, SPR_MEMORY, WMD_MEMORY, BANK_SPACING


def attempt(resolver, placement, stop_at_animation):
    raw, obj = placement.raw, OBJECT
    resolver.stop_at_animation = stop_at_animation
    resolver.write(0x80000000, resolver.baseline)
    resolver.write(0x1F800000, resolver.scratch)
    prepare_pools(resolver)
    resolver.spawn(obj, placement)
    resolver.write(obj + 0x1C, bytes((placement.native_layer or {3: 4, 4: 5, 5: 6, 7: 8}.get(placement.layer, placement.layer),)))
    resolver.write(obj + 0x70, struct.pack('<3h', 4096, 4096, 4096))
    if placement.model in resolver.model_spans:
        resolver.word(obj + 0x9C, resolver.model_spans[placement.model][0])
        resolver.write(obj + 0xA0, b'\x01')
    for offset, value in placement.extra:
        resolver.write(obj + offset, value)
    pc = resolver.handler_address(placement)
    result = {}
    for _ in range(4):
        try:
            resolver.run_handler(pc, obj, 12000)
        except UcError:
            pass
        state = resolver.read(obj, 0x200)
        sprite, anim = struct.unpack_from('<I', state, 0x3C)[0], struct.unpack_from('<I', state, 0x24)[0]
        model = struct.unpack_from('<I', state, 0x9C)[0]
        if model in resolver.model_pointers:
            result = dict(model=resolver.model_pointers[model], lit=bool(state[0xA0]),
                          scale=struct.unpack_from('<3h', state, 0x70),
                          rotation=struct.unpack_from('<3h', state, 0x7C))
            break
        if SPR_MEMORY <= sprite < WMD_MEMORY and (sprite - SPR_MEMORY) % BANK_SPACING == 0 and resolver.base <= anim < resolver.limit:
            frames = resolver.animation(anim)
            if frames:
                result = dict(sprite=(sprite-SPR_MEMORY)//BANK_SPACING, frame=frames[0][0], frames=frames,
                    animation_address=anim, flip=not state[0x2E]&1, tpage=struct.unpack_from('<H',state,0x1E)[0],
                    clut=struct.unpack_from('<H',state,8)[0] if state[0xD]&1 else None,
                    blend=bool(state[0xD]&0x80), shade=state[0x6B], sort_bias=0, sort_fixed=False,
                    sort_depth=struct.unpack_from('<h',state,0x1A)[0], screen_bias=0)
                break
    if result:
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
