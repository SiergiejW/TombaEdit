"""Bounded MIPS initialization traces for the executables in game.builds.

This is an initial-pose resolver, not a running PSX emulator. It executes a
single object's initializer in isolated memory. Audio, visibility and flag
queries are stubbed; no BIOS, files, devices or game loop are exposed.
A build whose addresses are not listed keeps its APD markers and directly
linked models.

Routine addresses in the comments are the US retail ones. Handler tables go
by APD layer: layers 2 to 5 share one object pool (routine 8001DFE4), layer
7, the backdrop sprites, has its own pool and table (routine 8003438C), and
layer 8 objects are models in a pool of 45 with a third (routine 8002DB4C).
"""
import struct
from game.builds import executable

# Camera step used to measure how far a backdrop sprite follows the camera.
NUDGE = 64
# Scratchpad words, the same in every build: the loaded SPR, WMD and APD
# banks by slot, and the camera position.
SPR_TABLE, WMD_TABLE, APD_TABLE = 0x1F8002C8, 0x1F800330, 0x1F800358
CAMERA_X, CAMERA_Y = 0x1F800176, 0x1F800186
# Where the resolver keeps its one object and the banks it loads.
OBJECT, SPR_MEMORY, WMD_MEMORY, BANK_SPACING = 0x80300000, 0x80400000, 0x80800000, 0x40000
# Scripts and tables are looked for from the executable to this far past the
# start of the overlay.
REACH = 0x58C78


def runtime_area(area, section, early=False):
    """resolveAreaVariant maps resource variants back to gameplay areas.
    The 1997 builds have no variants."""
    if early:
        return area
    return 1 if area == 7 else 4 if area == 12 else 2 if area == 19 and section < 2 else area


class InitialPoseResolver:
    def __init__(self, project, area, section, resources):
        requested_area = area
        self.available = False
        self.reason = "This executable's object routines have not been located."
        self.cache = {}
        self.object_states = {}
        self.queued = set()
        self.stop_at_animation = False
        found = executable(project)
        if found is None or area < 0:
            return
        self.build = build = found.build
        area = runtime_area(area, section, build.early)
        self.area = area
        self.exe, self.base = found.data, found.base
        overlay = next((a for a in resources.values() if a.kind == 'INS'), None)
        if overlay is None:
            self.reason = 'The load group has no code overlay to run its objects from.'
            return
        try:
            from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
            from unicorn import mips_const as reg
        except ImportError:
            self.reason = 'Install the unicorn dependency to resolve sprite initial poses.'
            return
        self.reg = reg
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0, 0x1000000)
        self.u.mem_map(0x1F800000, 0x1000)
        code = project.asset_data(overlay)
        self.limit = max(build.overlay + REACH, build.overlay + len(code))
        self.code = ((self.base, found.end), (build.overlay, self.limit))
        self.write(self.base, self.exe[0x800:])
        self.write(build.overlay, code)
        self.write(build.area, struct.pack('<HH', area, max(0, section)))
        if build.variant and requested_area in (7, 12, 19):
            variant = {7: 6, 12: 8, 19: 17}[requested_area]
            if requested_area != 19 or section < 2:
                self.write(build.variant[0], struct.pack('<H', variant))
                self.write(build.variant[1], bytes((1 if requested_area in (7, 19) else 8,)))
        self.model_pointers = {}
        self.model_spans = {}      # (slot, index) -> (address, size)
        for (family, slot), asset in resources.items():
            if family not in ('SPR', 'WMD'):
                continue
            address = (SPR_MEMORY if family == 'SPR' else WMD_MEMORY) + slot * BANK_SPACING
            data = project.asset_data(asset)
            if len(data) >= BANK_SPACING:
                continue
            self.write(address, data)
            self.word((SPR_TABLE if family == 'SPR' else WMD_TABLE) + slot * 4, address)
            if family == 'WMD':
                count = struct.unpack_from('<I', data)[0]
                if count <= 4096 and 4 + 4 * count <= len(data):
                    offsets = struct.unpack_from(f'<{count}I', data, 4) + (len(data),)
                    for i, off in enumerate(offsets[:-1]):
                        self.model_pointers[address + off] = (slot, i)
                        self.model_spans[slot, i] = (address + off, offsets[i + 1] - off)
        self.baseline = self.read(0x80000000, 0x200000)
        self.scratch = self.read(0x1F800000, 0x1000)
        self.u.hook_add(UC_HOOK_CODE, self.hook)
        self.cpu_context = self.u.context_save()
        self.available = True
        self.reason = f'Initial poses traced from the {build.name} executable and the area overlay.'

    def read(self, address, count):
        return bytes(self.u.mem_read(address & 0x1FFFFFFF, count))

    def write(self, address, data):
        self.u.mem_write(address & 0x1FFFFFFF, data)

    def word(self, address, value):
        self.write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def run_handler(self, pc, obj, count):
        # Stopping inside a MIPS delay slot can leave a pending branch in
        # Unicorn. Each independent call starts with a clean CPU context;
        # object and bank memory still carry the state of the current update.
        self.u.context_restore(self.cpu_context)
        r = self.reg
        self.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
        self.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
        self.u.reg_write(r.UC_MIPS_REG_A0, obj)
        self.u.emu_start(pc, 0x80001000, count=count)

    def read_word(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def exe_word(self, address):
        return struct.unpack_from('<I', self.exe, address - self.base + 0x800)[0]

    def placement_slots(self, area, section):
        area = runtime_area(area, section, self.build.early)
        table = self.exe_word(self.build.slot_tables + area * 4)
        common = min(15, struct.unpack_from('<H', self.exe, self.build.common + area * 2 - self.base + 0x800)[0])
        return tuple((self.exe_word(table + i * 4) - APD_TABLE) // 4
                     for i in (section & 7, common))

    def picture_parts(self, placement):
        """Rectangles a layer 7 object in draw mode 2 is made of.

        The backdrop draw list (routine 8004DE40) picks a routine by the
        object's byte +0A, which is APD byte 12. Mode 2 (routine 8004E244)
        draws a fixed picture: the table at 8007EBEC, indexed by the variant,
        points at 18-byte records ending in 7FFF. A record is a texture page
        word, an X and Y offset from the object, U, V, width, height, the
        palette's VRAM position and a blend flag; the sampler's records have
        no flag and are 16 bytes. Returns
        [(tpage, x, y, u, v, width, height, clut)]."""
        if not self.available or placement.layer != 7 or placement.raw[12] != 2 or not self.build.pictures:
            return []
        try:
            at = self.read_word(self.build.pictures + placement.variant * 4)
            parts = []
            while len(parts) < 64 and self.base <= at < self.limit:
                tpage, x, y, u, v, width, height, clut_x, clut_y = struct.unpack('<hhhBBHHhh', self.read(at, 16))
                if tpage == 0x7FFF:
                    return parts
                if not (0 < width <= 256 and 0 < height <= 256):
                    break
                parts.append((tpage & 0x1FF, x, y, u, v, width, height, (clut_y & 511) << 6 | (clut_x >> 4) & 63))
                at += self.build.picture_record
        except Exception:
            pass
        return []

    def model_animation(self, placement):
        """Versions of a layer 8 object's model as its handler rewrites it.

        Some scenery is animated by code that edits the model in place, for
        instance stepping the texture coordinates of a water surface between
        two pictures. The handler is run for a few hundred updates with the
        model in memory; every time the model's bytes change the new version
        is kept. Returns [(model bytes, ticks)] for one cycle, or [] when
        nothing changes. Handlers only work while their object is in view,
        so a few camera positions are tried."""
        if not self.available or placement.layer != 8 or placement.model not in self.model_spans:
            return []
        if placement.raw in self.cache:
            return self.cache[placement.raw]
        r, raw, obj = self.reg, placement.raw, OBJECT
        address, size = self.model_spans[placement.model]
        original = self.read(address, size)
        pc = self.read_word(self.build.tables[8] + placement.kind * 4)
        x, y = placement.position[:2]
        found = []
        for camera in ((x - 160, y - 120), (0, 0), (x + 200, y - 120), (x - 500, y - 120)):
            self.write(0x80000000, self.baseline)
            self.write(0x1F800000, self.scratch)
            self.write(address, original)
            self.write(CAMERA_X, struct.pack('<h', max(-32768, min(32767, camera[0]))))
            self.write(CAMERA_Y, struct.pack('<h', max(-32768, min(32767, camera[1]))))
            self.write(obj, bytes(0x200))
            self.word(obj + 0x40, obj + 0x10)
            self.word(obj + 0x44, obj + 0x18)
            self.write(obj, bytes((1, 0, raw[2], raw[4])))
            for offset, value in ((0xC, raw[3]), (0xA, raw[12]), (0xF, raw[13]), (0x1C, raw[1]), (0x1D, raw[0])):
                self.write(obj + offset, bytes((value,)))
            self.write(obj + 0x2E, bytes((raw[5], 0)))
            for j, value in enumerate(placement.position):
                self.word(obj + 0x10 + j * 4, value << 16)
            self.word(obj + 0xA0, address)
            self.write(obj + 0xA4, b'\x01')
            runs = []
            try:
                for _ in range(400):
                    self.run_handler(pc, obj, 20000)
                    now = self.read(address, size)
                    if runs and runs[-1][0] == now:
                        runs[-1][1] += 1
                    elif len(runs) > 2 and now == runs[1][0]:
                        break                       # back at the start of the cycle
                    else:
                        runs.append([now, 1])
            except Exception:
                runs = []
            if len(runs) > 2:
                # The first run is the untouched model before the cycle starts.
                found = [(data, ticks) for data, ticks in runs[1:]]
                break
        self.write(address, original)
        self.cache[placement.raw] = found
        return found

    def backdrop_motion(self, obj, pc, placement):
        """How a layer 7 object reaches the screen.

        On each update it turns its placement into a position on the
        320 x 240 screen from the camera words at 1F800176 (X) and 1F800186
        (Y). Running that update with the camera at the origin and nudged on
        each axis gives the screen position and the fraction of camera
        movement the sprite follows. Objects that stay at their placement are
        ordinary world sprites and return nothing."""
        r, ready, scratch = self.reg, self.read(obj, 0x200), self.read(0x1F800000, 0x1000)

        def update(camera_x, camera_y):
            self.write(obj, ready)
            self.write(0x1F800000, scratch)
            self.write(CAMERA_X, struct.pack('<h', camera_x))
            self.write(CAMERA_Y, struct.pack('<h', camera_y))
            try:
                self.run_handler(pc, obj, 4000)
            except Exception:
                pass
            moved = self.read(obj, 0x20)
            return struct.unpack_from('<h', moved, 0x12)[0], struct.unpack_from('<h', moved, 0x16)[0]

        anchor = tuple(placement.position[:2])
        base = follow = None
        # A sprite that is off the screen is left where it was, so look from
        # a few camera positions until it shows.
        for start in (0, 512, 1024, 1536):
            seen, across, down = update(start, 0), update(start + NUDGE, 0), update(start, NUDGE)
            if seen != anchor and across != anchor and down != anchor:
                follow = ((seen[0] - across[0]) / NUDGE, (seen[1] - down[1]) / NUDGE)
                base = (round(seen[0] + start * follow[0]), seen[1])
                break
        if base is None or (start == 0 and follow == (0, 0) and base == anchor):
            return {}
        if follow == (1.0, 1.0):
            # Moves exactly with the camera: part of the level, not scenery
            # behind it.
            return dict(anchored=True)
        # Looping scenery comes back to the same place after the camera has
        # travelled one period; the strips of a loop are placed a period apart.
        period = 0
        if follow[0]:
            travel = next((c for c in (256, 512, 1024, 2048, 4096, 8192) if update(start + c, 0) == seen), 0)
            period = round(travel * follow[0])
        return dict(screen=base, follow=follow, period=period)

    def animation(self, address):
        """Follow an animation script: eight-byte steps of frame, two unused
        words here, and a duration whose top bits end the step list. 0000
        continues, 4000 and C000 jump through the pointer that follows, and
        8000 holds the frame. Returns [(frame, ticks)] for one pass."""
        frames, seen = [], set()
        while address not in seen and len(frames) < 512 and self.base <= address < self.limit:
            seen.add(address)
            frame, _, _, control = struct.unpack('<4H', self.read(address, 8))
            frames.append((frame, control & 0x3FFF or 1))
            if control & 0xC000 == 0x8000:
                break
            address = self.read_word(address + 8) if control & 0x4000 else address + 8
        return frames

    def in_exe(self, address, size):
        return self.base <= address and address + size <= self.base + len(self.exe) - 0x800

    def entrance(self, area, section):
        """Tomba's position at the section's first entrance, or None."""
        if not self.available:
            return None
        area = runtime_area(area, section, self.build.early)
        if not 0 <= area < 20 or not 0 <= section < 32:
            return None
        sections = self.exe_word(self.build.entrances + area * 4)
        if not self.in_exe(sections + section * 4, 4):
            return None
        record = self.exe_word(sections + section * 4)
        if not self.in_exe(record, 8):
            return None
        return struct.unpack_from('<3h', self.exe, record - self.base + 0x800)

    def collision_frame(self, area, section, alternate=False):
        """Where a section's collision sits: (along0, depth0, turned, slot).

        Collision is indexed by a coordinate along the path, 8 units a
        column, and by depth, 90 units a plane (routine 80042654). Objects
        reach the two through pointers at +40 and +44, which the allocators
        aim at their X and Z. When the entrance flag at 1F8001C8 is set the
        pointers are swapped: the path runs along world Z, and planes are
        counted down world X from depth0. The flag comes from the section's
        first entrance record (table at 8007BF78, routine 800243E8) and the
        origins from the table at 8007E9F8.

        The mansion's four outer walls are one area seen from four sides.
        There the origin comes from the table at 8007E9E8 and the flag also
        picks which WHM slot is used, returned as `slot`."""
        along0 = depth0 = 0
        turned, slot = False, 0
        entrance = None
        if not self.available:
            return along0, depth0, turned, slot
        build = self.build
        area = runtime_area(area, section, build.early)
        if not 0 <= area < 20 or not 0 <= section < 32:
            return along0, depth0, turned, slot
        sections = self.exe_word(build.entrances + area * 4)
        if self.in_exe(sections + section * 4, 4):
            entrances = self.exe_word(sections + section * 4)
            if self.in_exe(entrances, 8):
                entrance = struct.unpack_from('<3hH', self.exe, entrances - self.base + 0x800)
                turned = bool(entrance[3] & 1)
        table = self.exe_word(build.origins + area * 4)
        if area == 0 and section < 3:
            slot = None
        if area in (4, 12) and section < 4:
            table, slot = build.wall_origins, int(turned)
        elif area == 0 and section >= 3:
            # The hut bypasses the village's split bank selection. Behind
            # the hut and the pond clamp to plane 0 of their local slot 0;
            # the base slot 1 is still loaded but is not their collision.
            slot = 0
        if self.in_exe(table + section * 4, 4):
            along0, depth0 = struct.unpack_from('<hh', self.exe, table + section * 4 - self.base + 0x800)
        if alternate and area == 3 and section in (1, 5) and build.alternate_origin:
            # 800427D0 branches on the signed route state at [800A53DC]+2.
            # A negative state uses slot 1, the pair at 8007E9E4, and adds
            # 90 to the queried depth before indexing the plane table.
            along0, depth0 = struct.unpack_from('<hh', self.exe, build.alternate_origin - self.base + 0x800)
            return along0, depth0 - 90, turned, 1
        # Sections limited to one plane (byte table at 8007EAF4) clamp every
        # depth to it, so their depth origin is not meaningful; the plane is
        # where Tomba enters. The 1997 builds keep the limits in place of the
        # per-area pointers.
        limits, stride, width = build.plane_limits
        limits = limits + area * stride + section * width if stride else self.exe_word(limits + area * 4) + section
        single = self.in_exe(limits, width) and not any(self.exe[limits - self.base + 0x800:][:width])
        if turned and single and entrance is not None and area not in (4, 12):
            depth0 = entrance[0]
        return along0, depth0, turned, slot

    def hook(self, uc, address, size, user):
        r, build = self.reg, self.build
        if address == build.set_animation and self.stop_at_animation:
            self.completed = True
            uc.emu_stop()
        elif address == build.set_animation:
            pass                # the animation setter runs like any other code
        elif address in build.visibility:
            # Visibility tests also mark byte +1, which initializers use to
            # decide whether to start a sprite's animation.
            obj = uc.reg_read(r.UC_MIPS_REG_A0)
            if OBJECT <= obj < OBJECT + 0x200:
                self.write(obj + 1, b'\x01')
            uc.reg_write(r.UC_MIPS_REG_V0, 1)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address == build.get_clut:
            # GetClut(x, y): objects that pick their palette this way keep it.
            x, y = uc.reg_read(r.UC_MIPS_REG_A0), uc.reg_read(r.UC_MIPS_REG_A1)
            uc.reg_write(r.UC_MIPS_REG_V0, (y & 511) << 6 | (x >> 4) & 63)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address in build.draw_queues:
            # Handing an object to a draw list needs lists nobody set up here.
            # Which list it asked for says how it is drawn.
            self.queued.add(address)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address in build.silent:
            uc.reg_write(r.UC_MIPS_REG_V0, 0)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif not any(start <= address < end for start, end in self.code):
            uc.emu_stop()

    def resolve(self, placement):
        if not self.available or placement.layer not in (2, 3, 4, 5, 7):
            return {}
        key = (placement.raw, placement.position)
        if key not in self.cache:
            # Most initialisers finish on their own. Some run into parts of
            # the game that are not here; for those, stopping where the
            # animation is set is enough to learn what the object shows.
            self.cache[key] = self.attempt(placement, False) or self.attempt(placement, True)
            if (not self.cache[key] and not self.build.early and placement.layer == 5
                    and placement.kind == 4 and placement.variant == 3 and placement.raw[3] == 1):
                # The collectible's initializer removes it unless the event
                # byte at C114 is FF (US 80041284). Decode its conditional
                # pose with that byte set, without changing the initial scene.
                baseline = self.baseline
                changed = bytearray(baseline)
                changed[(self.build.area + 0x44C) & 0x1FFFFF] = 0xFF
                self.baseline = bytes(changed)
                try:
                    result = self.attempt(placement, False) or self.attempt(placement, True)
                finally:
                    self.baseline = baseline
                if result:
                    result['condition'] = 'Conditional collectible: the game shows it when its event flag is FF. Enable Event previews to inspect it.'
                    self.cache[key] = result
            event = self.build.event
            if not self.cache[key] and event and self.area == 0 and placement.layer == 5 and placement.kind == 0x12:
                # X00's initializer 80122F64 only draws this effect while
                # the event bytes BCA8/BCA9 select state 7E. Show a labelled
                # conditional pose instead of treating its link as missing.
                baseline = self.baseline
                changed = bytearray(baseline)
                changed[event & 0x1FFFFF:(event & 0x1FFFFF) + 2] = b'\x01\x7E'
                self.baseline = bytes(changed)
                result = self.attempt(placement, False) or self.attempt(placement, True)
                self.baseline = baseline
                if result:
                    result['condition'] = 'Event effect: only visible when event bytes BCA8/BCA9 select state 7E.'
                    self.cache[key] = result
        return self.cache[key]

    def handler_address(self, placement):
        """The actual dispatch entry, for inspection of a placed object."""
        if not self.available:
            return None
        table = self.build.tables.get(placement.layer)
        return self.read_word(table + placement.kind * 4) if table is not None else None

    def attempt(self, placement, stop_at_animation):
        from unicorn import UcError
        self.stop_at_animation = stop_at_animation
        r, raw, obj = self.reg, placement.raw, OBJECT
        parents = []
        parent = placement.parent
        while parent is not None and len(parents) < 32:
            self.resolve(parent)
            state = self.object_states.get((parent.raw, parent.position))
            if state is None:
                break
            parents.append((parent, state))
            parent = parent.parent
        self.write(0x80000000, self.baseline)
        self.write(0x1F800000, self.scratch)
        self.write(obj, bytes(0x200))
        self.word(obj + 0x40, obj + 0x10)
        self.word(obj + 0x44, obj + 0x18)
        self.write(obj, bytes((1, 0, raw[2], raw[4])))
        for offset, value in ((0xC, raw[3]), (0xA, raw[12]), (0xF, raw[13]),
                              (0x1C, raw[1]), (0x1D, raw[0])):
            self.write(obj + offset, bytes((value,)))
        self.write(obj + 0x2E, bytes((raw[5], 0)))
        self.write(obj + 0x74, struct.pack('<3h', 4096, 4096, 4096))
        if placement.model in self.model_spans:
            self.word(obj + 0xA0, self.model_spans[placement.model][0])
        for j, value in enumerate(placement.position):
            self.word(obj + 0x10 + j * 4, value << 16)
        # APD modes 2/3 link the child at +90 to its parent's live object.
        # Copy each initialized parent into separate memory, with its own
        # coordinate pointers. Attached sprites read these in their updates.
        for n, (parent, state) in enumerate(parents):
            address = OBJECT + 0x4000 + n * 0x400
            self.write(address, state)
            for offset in (0x40, 0x44):
                pointer = struct.unpack_from('<I', state, offset)[0]
                if OBJECT <= pointer < OBJECT + 0x200:
                    self.word(address + offset, address + pointer - OBJECT)
            self.word(address + 0x90, address + 0x400 if n + 1 < len(parents) else 0)
        if parents:
            self.word(obj + 0x90, OBJECT + 0x4000)
        pc = self.read_word(self.build.tables[placement.layer] + placement.kind * 4)
        result = {}
        try:
            for step in range(4):
                self.completed = False
                self.run_handler(pc, obj, 4000)
                sprite = self.read_word(obj + 0x3C)
                anim = self.read_word(obj + 0x24)
                model = self.read_word(obj + 0xA0)
                if model in self.model_pointers:
                    result['model'] = self.model_pointers[model]
                    result['scale'] = struct.unpack('<3h', self.read(obj + 0x74, 6))
                    result['rotation'] = struct.unpack('<3i', self.read(obj + 0x84, 12))
                    self.object_states[(raw, placement.position)] = self.read(obj, 0x200)
                    break
                if SPR_MEMORY <= sprite < WMD_MEMORY and (sprite - SPR_MEMORY) % BANK_SPACING == 0:
                    if self.base <= anim < self.limit:
                        if parents and step == 0 and not stop_at_animation:
                            # Initialization names the image; the first update
                            # attaches it to the parent (e.g. a hanging lamp).
                            continue
                        frames = self.animation(anim)
                        state = self.read(obj, 0x30)
                        self.object_states[(raw, placement.position)] = self.read(obj, 0x200)
                        if parents:
                            result['position'] = tuple(v / 65536 for v in struct.unpack('<3i', self.read(obj + 0x10, 12)))
                        # Draw routine 800487B0: bit 0 of +2E draws the parts as
                        # stored and a clear bit mirrors them about the origin;
                        # +1E is added to every part's texture page; bit 0 of
                        # +0D replaces the part CLUT with +08.
                        result.update(sprite=(sprite - SPR_MEMORY) // BANK_SPACING,
                                      frame=frames[0][0], frames=frames,
                                      animation_address=anim,
                                      flip=not state[0x2E] & 1,
                                      tpage=struct.unpack_from('<H', state, 0x1E)[0],
                                      clut=struct.unpack_from('<H', state, 8)[0] if state[0xD] & 1 else None,
                                      blend=bool(state[0xD] & 0x80))
                        result['sort_bias'] = struct.unpack_from('<b', state, 0xF)[0]
                        result['sort_fixed'] = bool(state[0xB])
                        result['sort_depth'] = struct.unpack_from('<h', state, 0x1A)[0]
                        result['screen_bias'] = (struct.unpack_from('<h', state, 0xE)[0]
                                                 if state[0xB] == 2 else result['sort_bias'])
                        if placement.layer == 7:
                            # Backdrop strips name a second frame in the word
                            # after the first; both are drawn at the anchor.
                            result['overlay'] = struct.unpack('<H', self.read(anim + 2, 2))[0]
                        if placement.layer == 7:
                            # Drawn from the screen-space list: the parts are
                            # never mirrored there, and the object works out
                            # its own screen position.
                            result['flip'] = False
                            result.update(self.backdrop_motion(obj, pc, placement))
                        elif self.backdrop_motion(obj, pc, placement).get('anchored'):
                            # Scenery in other layers that also keeps its own
                            # screen position, one to one with the camera.
                            result['anchored'] = True
                        break
        except UcError:
            pass
        return result


def table_pages(project):
    """Texture page base per SPR slot from the object table at 8007D6E4 in
    US retail (twelve-byte entries: page base, animation, slot, script
    pointer). Used for banks that no placed object shows. Empty for builds
    where the table has not been located."""
    found = executable(project)
    if found is None or not found.build.pages:
        return {}
    exe, base, votes, at = found.data, found.base, {}, found.build.pages
    layout = found.build.page_record
    size = struct.calcsize(layout)
    while found.holds(at, size):
        page, _, slot, pointer = struct.unpack_from(layout, exe, at - base + 0x800)
        if not (0 <= slot < 16 and page < 32 and 0x80010000 <= pointer < 0x80200000):
            break
        votes.setdefault(slot, {}).setdefault(page, 0)
        votes[slot][page] += 1
        at += size
    return {slot: max(pages, key=pages.get) for slot, pages in votes.items()}
