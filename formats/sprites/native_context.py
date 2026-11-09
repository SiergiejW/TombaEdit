"""SPR inspection with original initialization and drawing code.

These are bounded traces with the initial-pose resolver's documented service
stubs, not a complete game/emulator state.  No inferred bank links, palette
substitutions or frames from another load context enter this result.  Each
assigned animation step is drawn with the object's initialization fields;
later AI updates and runtime VRAM changes are not simulated.
"""
from dataclasses import asdict, replace
import hashlib
import struct

from disc.reader import FormatError
from formats.level.apd import parse_apd
from formats.level.draw import DrawCapture
from formats.level.runtime import InitialPoseResolver, OBJECT
from formats.sprites.animations import Memory, read_script

TRACE_RAM_SIZE = 0x1000000
TRACE_PAGE_SIZE = 0x1000


DECOMP_REFERENCE = dict(repository='https://github.com/afsenovilla/Tombi-Decomp',
                        revision='51e0f8a3d5d3b79eb42fea1d074a43ac3798db31',
                        files=['src/drawObjectSprite.c', 'src/AnimAdvance.c', 'include/tomba/anim.h'])


class IncompleteTrace(RuntimeError):
    """An initializer stopped before returning to its real caller."""


class BankTraceResolver(InitialPoseResolver):
    """Do not seed event flags, stop at animation setters, or select motions."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.native_states, self.native_failures = {}, {}
        self.native_gpu_upload = False
        self.native_upload_tracking = False
        if self.available:
            self.native_baseline = self.read(0x80000000, TRACE_RAM_SIZE)
            load_image = self.build.get_clut + 0xFA0
            if self.read(load_image, 4) == bytes.fromhex('e0ffbd27'):
                from unicorn import UC_HOOK_CODE
                self.u.hook_add(UC_HOOK_CODE, self.reject_upload, begin=load_image, end=load_image)
                self.native_upload_tracking = True

    def write(self, address, data):
        # InitialPoseResolver resets only the console's first 2 MB. Our
        # synthetic SPR/WMD banks are above that range and must reset too,
        # including when a parent initializer ran immediately before this.
        if (address == 0x80000000 and hasattr(self, 'native_baseline')
                and data is self.baseline):
            data = self.native_baseline
        super().write(address, data)

    def reject_upload(self, uc, address, size, user):
        self.native_gpu_upload = True
        uc.emu_stop()

    def run_handler(self, pc, obj, count):
        super().run_handler(pc, obj, count)
        if self.native_gpu_upload:
            raise IncompleteTrace('Initializer requests a runtime VRAM upload; its resulting VRAM is unresolved.')
        if self.u.reg_read(self.reg.UC_MIPS_REG_PC) != 0x80001000:
            raise IncompleteTrace('Initializer did not return within the trace bound.')

    def resolve(self, placement):
        if not self.available or placement.layer not in (2, 3, 4, 5, 7):
            return {}
        key = (placement.raw, placement.position, placement.extra, placement.memory)
        if key not in self.cache:
            self.native_gpu_upload = False
            try:
                self.cache[key] = self.attempt(placement, False)
            except (IncompleteTrace, IndexError, struct.error) as error:
                self.cache[key] = {}
                if hasattr(self, 'native_failures'):
                    self.native_failures[key] = str(error)
            if self.cache[key].get('sprite') is not None and key not in self.draw_states:
                # The general level resolver does not retain layer-7 draw
                # states. Keep the actual initialized bytes here as well.
                self.draw_states[key] = (self.read(OBJECT, 0x200), self.read(OBJECT + 0x4000, 0x400),
                                         self.read(0x1F800000, 0x400))
            if self.cache[key].get('sprite') is not None:
                # Store sparse changed pages, rather than 16 MB per object.
                # The complete image is reconstructed transiently for draw.
                current = self.read(0x80000000, TRACE_RAM_SIZE)
                delta = tuple((at, current[at:at + TRACE_PAGE_SIZE])
                              for at in range(0, TRACE_RAM_SIZE, TRACE_PAGE_SIZE)
                              if current[at:at + TRACE_PAGE_SIZE] != self.native_baseline[at:at + TRACE_PAGE_SIZE])
                self.native_states[key] = (delta, self.read(0x1F800000, 0x1000))
        return self.cache[key]


class CompleteDrawCapture(DrawCapture):
    """Discard partial packets if any of the camera capture calls fail."""

    def capture(self, *args, **kwargs):
        original = self.cpu.call
        incomplete = False

        def checked(*call_args, **call_kwargs):
            nonlocal incomplete
            try:
                return original(*call_args, **call_kwargs)
            except Exception:
                incomplete = True
                raise

        self.cpu.call = checked
        try:
            result = super().capture(*args, **kwargs)
        finally:
            self.cpu.call = original
        return None if incomplete else result


class RestoreDrawMemory:
    """Restore post-init memory before *each* alternative camera draw.

    DrawCapture iterates its memory argument once per camera, before it
    writes the object/list/camera harness. That is the reset boundary.
    """

    def __init__(self, cpu, ram, scratch):
        self.cpu, self.ram, self.scratch = cpu, ram, scratch

    def __iter__(self):
        from psx.mips.gte import GTE
        cpu = self.cpu
        cpu.write(0x80000000, self.ram)
        cpu.write(0x1F800000, self.scratch)
        cpu.R[:] = [0] * 32
        cpu.hi = cpu.lo = cpu.pc = cpu.icount = 0
        cpu.cop0[:] = [0] * 32
        cpu.gte = GTE()
        cpu.pc_override = None
        def unsupported_io(*args):
            raise IncompleteTrace('The draw routine requests an uncaptured hardware operation.')
        cpu.io_read = cpu.io_write = unsupported_io
        return iter(())


def _snapshot_ram(resolver, key):
    ram = bytearray(resolver.native_baseline)
    for at, data in resolver.native_states[key][0]:
        ram[at:at + len(data)] = data
    return ram


def _matches_loaded_script(resolver, script, count):
    original = read_script(resolver.animation_memory(), script.address, count)
    return original is not None and original.steps == script.steps and original.loop == script.loop


def _draw_steps(resolver, placement, script, ram=None):
    """(step, primitive dictionaries) using real script entries, never scans."""
    from formats.level.draw import town_of
    key = (placement.raw, placement.position, placement.extra, placement.memory)
    saved = resolver.draw_states.get(key)
    # Legacy8 has a different object layout and is intentionally not guessed.
    if saved is None or resolver.build.legacy8:
        return []
    native_state = resolver.native_states.get(key)
    if native_state is None:
        return []
    state = saved[0]
    scratch = native_state[1]
    ram = _snapshot_ram(resolver, key) if ram is None else ram
    if resolver.drawer is None:
        resolver.drawer = CompleteDrawCapture(resolver.exe, resolver.base, resolver.read, town_of(resolver.town))
    if not resolver.drawer.available:
        return []
    out = []
    for step in script.steps:
        current = bytearray(state)
        struct.pack_into('<I', current, 0x24, step.address)
        try:
            primitives = resolver.drawer.capture(OBJECT, bytes(current), scratch,
                category=placement.layer, memory=RestoreDrawMemory(resolver.drawer.cpu, ram, scratch))
        except (ValueError, IndexError, struct.error, RuntimeError):
            primitives = None
        if primitives:
            out.append((step, [asdict(p) for p in primitives]))
    return out


def _freeze(value):
    if isinstance(value, dict):
        return tuple((k, _freeze(v)) for k, v in sorted(value.items()))
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    return value


def _collect(result, observations):
    """Keep all observed variants and render only an unambiguous context."""
    variants = {}
    for frame, context, primitives in observations:
        context = dict(context, draw_commands=primitives)
        signature = _freeze((context['page'], context['clut'], context['style'], primitives))
        record = variants.setdefault(frame, {}).setdefault(signature, (context, primitives, []))
        if context not in record[2]:
            record[2].append(context)
    for frame, choices in variants.items():
        evidence = result['sprite_evidence'][frame]
        evidence['contexts'] = [context for _, _, contexts in choices.values() for context in contexts]
        if len(choices) != 1:
            evidence.update(status='ambiguous', reason='Objects in this load context draw this frame differently.')
            continue
        context, primitives, contexts = next(iter(choices.values()))
        result['sprite_pages'][frame] = context['page']
        if context['clut'] is not None:
            result['sprite_cluts'][frame] = context['clut']
        result['sprite_styles'][frame] = context['style']
        result['sprite_primitives'][frame] = primitives
        result['sprite_names'][frame] = list(dict.fromkeys(c['source'] for c in contexts))
        result['sprite_origins'][frame] = 'initialization and draw trace'
        result['sprite_unavailable'].discard(frame)
        evidence.update(status='traced', reason='Original draw packets with the traced initialization fields and real script entry.')


def _block_frames(result, blocked):
    """A known but uncaptured variant prevents a unique frame result."""
    for frame, contexts in blocked.items():
        evidence = result['sprite_evidence'][frame]
        evidence['contexts'].extend(contexts)
        evidence.update(status='unresolved', reason=contexts[0]['unresolved_reason'])
        result['sprite_unavailable'].add(frame)
        for key in ('sprite_pages', 'sprite_cluts', 'sprite_styles', 'sprite_primitives', 'sprite_names', 'sprite_origins'):
            result[key].pop(frame, None)


def prepare_native_bank(project, node, index, frames, screen=None):
    """Return a preview payload using only this bank's selected load context.

    ``sprite_evidence`` is JSON-compatible provenance per frame. Conflicting
    object variants remain unavailable, with every observed context retained.
    ``sprite_primitives`` contains plain dictionaries accepted by Primitive().
    """
    from formats.level.scene import loaded_resources, area_of
    from game.builds import executable
    from formats.sprites.native_render import load_vram, packets_loaded
    path = node.ldar
    vram, loaded_mask = load_vram(project, path, index, screen)
    result = dict(vram=vram, sprite_pages={}, sprite_cluts={},
                  sprite_styles={}, sprite_primitives={}, sprite_names={}, sprite_origins={},
                  sprite_vrams={}, sprite_default=None, animation_users={},
                  sprite_unavailable={i for i, frame in enumerate(frames) if frame},
                  sprite_evidence={i: dict(status='unresolved', reason='No completed initialization and drawing trace in this load context.',
                                           contexts=[]) for i, frame in enumerate(frames) if frame},
                  native_notes=['Native context: bounded original-code initialization and drawing traces. '
                                'Visibility, audio and flag queries use the resolver\'s documented stubs. '
                                'Animation steps keep initialization fields; later AI and runtime VRAM updates are not simulated.'])
    found = executable(project, path)
    if found is not None:
        resources = loaded_resources(project, path, index)
        overlay = next((asset for (kind, _), asset in resources.items() if kind == 'INS'), None)
        result['animation_code'] = ([('overlay', found.build.overlay, bytes(project.asset_data(overlay)))]
                                    if overlay is not None else []) + [('executable', found.base, found.data[0x800:])]
        result['update_rate'] = 50 if 'European' in found.build.name else 60
        result['native_build'] = dict(name=found.build.name, executable_sha1=hashlib.sha1(found.data).hexdigest(),
                                     executable_sha256=hashlib.sha256(found.data).hexdigest(),
                                     sprite_sha256=hashlib.sha256(project.asset_data(node)).hexdigest(),
                                     overlay_sha256=(hashlib.sha256(project.asset_data(overlay)).hexdigest()
                                                     if overlay is not None else None),
                                     load_table=path, load_group=index, screen=screen,
                                     vram_source='Ordered literal LDAR rectangle uploads only',
                                     decomp_reference=DECOMP_REFERENCE)
    if screen is not None:
        result['native_notes'].append('System-screen initialization contexts are unresolved in this native bank view.')
        return result
    if index <= 0:
        result['native_notes'].append('A base load group alone does not identify an area-section initialization context.')
        return result
    resources = loaded_resources(project, path, index)
    slot = (node.code >> 8) & 15
    bank = resources.get(('SPR', slot))
    if bank is None or bytes(project.asset_data(bank)) != bytes(project.asset_data(node)):
        result['native_notes'].append('The selected bank is not loaded into its slot in this load context.')
        return result
    area, section = area_of(path), max(0, index - 1)
    resolver = BankTraceResolver(project, area, section, resources)
    resolver.event_poses = False
    resolver.measure_backdrops = False
    if not resolver.available:
        result['native_notes'].append(resolver.reason)
        return result
    if resolver.build.legacy8:
        result['native_notes'].append('This early build\'s native sprite draw capture is unresolved.')
        return result
    if not resolver.native_upload_tracking:
        result['native_notes'].append('Runtime VRAM upload monitoring is unresolved for this executable.')
        return result
    slots = resolver.placement_slots(area, section)
    batches = []
    for (kind, apd_slot), asset in resources.items():
        if kind != 'APD':
            continue
        try:
            batches.append((apd_slot, asset, parse_apd(project.asset_data(asset))))
        except FormatError:
            continue
    own_records = {p.raw for apd_slot, _, placements in batches if slots and apd_slot == slots[0] for p in placements}
    shared = (section, ~section, ~(section - 1))
    observations, blocked = [], {}
    modified_scripts = set()
    for apd_slot, asset, placements in batches:
        for placement in placements:
            active = slots is None or apd_slot == slots[0] or (
                placement.section in shared and placement.raw not in own_records if not resolver.build.early
                else apd_slot == slots[1] and placement.section in shared[:2])
            if not active:
                continue
            if slots and apd_slot != slots[0]:
                placement = replace(placement, extra=placement.extra + ((0x6B, bytes((placement.raw[15] >> 2,))),))
            visual = resolver.resolve(placement)
            if visual.get('sprite') != slot or not visual.get('animation_address'):
                continue
            key = (placement.raw, placement.position, placement.extra, placement.memory)
            ram = _snapshot_ram(resolver, key)
            regions = [('executable', resolver.base, ram[resolver.base & 0x1FFFFFFF:
                                                        (resolver.base & 0x1FFFFFFF) + len(resolver.exe) - 0x800]),
                       ('overlay', resolver.build.overlay, ram[resolver.build.overlay & 0x1FFFFFFF:
                                                               (resolver.build.overlay & 0x1FFFFFFF) + len(resolver.overlay_code)])]
            script = read_script(Memory(regions), visual['animation_address'], len(frames))
            if script is None:
                continue
            source = f'{getattr(asset, "label", "APD")} +0x{placement.offset:X}, object {placement.layer}:{placement.kind:02X}/{placement.variant:02X}'
            if _matches_loaded_script(resolver, script, len(frames)):
                result['animation_users'].setdefault(script.address, []).append(source)
            else:
                modified_scripts.add(script.address)
            style = {key: visual[key] for key in ('flip', 'blend', 'shade') if key in visual}
            base_context = dict(source=source, handler=resolver.handler_address(placement),
                                animation=script.address, page=visual['tpage'], clut=visual.get('clut'), style=style,
                                initialization_memory_sha256=hashlib.sha256(ram).hexdigest())
            drawn = _draw_steps(resolver, placement, script, ram=ram)
            captured = {step.address for step, _ in drawn}
            for step in script.steps:
                if frames[step.frame] and step.address not in captured:
                    blocked.setdefault(step.frame, []).append(dict(base_context, entry=step.address,
                        unresolved_reason='A linked object variant did not yield a complete native draw capture.'))
            for step, primitives in drawn:
                if not frames[step.frame]:
                    continue
                context = dict(base_context, entry=step.address)
                if not packets_loaded(primitives, loaded_mask):
                    blocked.setdefault(step.frame, []).append(dict(context,
                        unresolved_reason='Texture or CLUT words were not loaded by this context.',
                        draw_commands=primitives))
                    continue
                observations.append((step.frame, context, primitives))
    _collect(result, observations)
    _block_frames(result, blocked)
    rejected_uploads = sum('runtime VRAM upload' in reason for reason in resolver.native_failures.values())
    if rejected_uploads:
        result['native_notes'].append(f'{rejected_uploads} object initializers request uncaptured runtime VRAM uploads and remain unresolved.')
    if modified_scripts:
        result['native_notes'].append(f'{len(modified_scripts)} initialized animation scripts differ from the original loaded bytes; '
                                      'their links are excluded from the original-byte animation player.')
    result['native_notes'].append(f'{len(result["sprite_pages"])} frames have unambiguous draw traces in this load context; '
                                  'other frames require another explicit context or remain unresolved.')
    return result
