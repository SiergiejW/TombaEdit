"""PrePre 8's object ABI, read from its embedded executable routines.

800834D0 copies APD fields; 800240BC installs resource pointers. This
predates the retail layer numbers, sprite slots and model-pointer offset.
"""
import struct
from formats.level.runtime import OBJECT, SPR_MEMORY, WMD_MEMORY, BANK_SPACING


def attempt(resolver, placement, stop_at_animation):
    r, raw, obj = resolver.reg, placement.raw, OBJECT
    resolver.stop_at_animation = stop_at_animation
    resolver.write(0x80000000, resolver.baseline)
    resolver.write(0x1F800000, resolver.scratch)
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
        except Exception:
            pass
        state = resolver.read(obj, 0x200)
        sprite, anim = struct.unpack_from('<I', state, 0x3C)[0], struct.unpack_from('<I', state, 0x24)[0]
        model = struct.unpack_from('<I', state, 0x9C)[0]
        if model in resolver.model_pointers:
            result = dict(model=resolver.model_pointers[model], lit=bool(state[0xA0]),
                          scale=struct.unpack_from('<3h', state, 0x70),
                          rotation=struct.unpack_from('<3i', state, 0x80))
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
        resolver.object_states[(raw, placement.position)] = state
        if placement.layer == 7 and 'sprite' in result:
            result.update(resolver.backdrop_motion(obj, pc, placement))
    return result
