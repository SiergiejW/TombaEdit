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
from pathlib import Path
import numpy as np
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
# How far from an object's first animation script its others are looked for.
CLASS_SCRIPTS = 0x800
# The pointers to one object's scripts lie within this many bytes.
SCRIPT_RUN = 0x100
# Objects are allocated from free lists kept in scratchpad words, the same
# in every build: (name, list pointer, count, slots given, slot size). The
# tracer hands each list spare slots here, so that what an object or a
# section controller spawns is made as in the game and can be read back.
SPAWN_AT = 0x80C00000
POOLS = (('objects', 0x1F800208, 0x1F800238, 48, 0x100), ('player', 0x1F800204, 0x1F800236, 8, 0x100),
         ('models', 0x1F80020C, 0x1F80023A, 16, 0x100), ('controllers', 0x1F800210, 0x1F80023E, 10, 0x40),
         ('backdrops', 0x1F800214, 0x1F80023C, 16, 0x100))
POOL_LISTS = SPAWN_AT + 0x40000
# A made-up caller's page base and bank, which no real object has: what a
# spawned object copies from its caller is told apart by them.
CALLER_PAGE, CALLER_BANK = 0x1FF, 0x80BFFF00
CONTROLLER = SPAWN_AT + 0x50000
# Updates a section controller is given to spawn what it spawns.
CONTROLLER_UPDATES = 90
# Where the tracer keeps a stand-in for Tomba when his entry is run.
PLAYER_STANDIN = SPAWN_AT + 0x60000


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
        self.measure_backdrops = True
        found = executable(project, next((a.ldar for a in resources.values()), None))
        if found is None or area < 0:
            return
        self.requested = (area, section)
        self.build = build = found.build
        area = runtime_area(area, section, build.early)
        self.area = area
        self.exe, self.base = found.data, found.base
        overlay = next((a for a in resources.values() if a.kind == 'INS'), None)
        if overlay is None and not build.legacy8:
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
        code = project.asset_data(overlay) if overlay else self.exe[0x800:]
        self.overlay_code = code
        self.overlay_words = np.frombuffer(bytes(code[:len(code) // 4 * 4]), '<u4')
        self.reach = {}
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
            table = (0x1F800150 if family == 'SPR' else 0x1F8001B8) if build.legacy8 else (SPR_TABLE if family == 'SPR' else WMD_TABLE)
            self.word(table + slot * 4, address)
            if family == 'WMD':
                count = struct.unpack_from('<I', data)[0]
                if count <= 4096 and 4 + 4 * count <= len(data):
                    offsets = struct.unpack_from(f'<{count}I', data, 4) + (len(data),)
                    for i, off in enumerate(offsets[:-1]):
                        self.model_pointers[address + off] = (slot, i)
                        self.model_spans[slot, i] = (address + off, offsets[i + 1] - off)
        self.baseline = self.read(0x80000000, 0x200000)
        self.scratch = self.read(0x1F800000, 0x1000)
        # Most instructions need no Python callback. Intercept only engine
        # services and execution outside the two permitted code regions.
        regions = []
        for start, end in sorted(self.code):
            if regions and start <= regions[-1][1]:
                regions[-1] = (regions[-1][0], max(end, regions[-1][1]))
            else:
                regions.append((start, end))
        cursor = 0
        for start, end in regions + [(0x100000000, 0x100000000)]:
            if cursor < start:
                self.u.hook_add(UC_HOOK_CODE, self.hook, begin=cursor, end=start - 1)
            cursor = end
        services = {build.set_animation, build.get_clut, *build.visibility, *build.draw_queues, *build.silent}
        for address in services:
            if any(start <= address < end for start, end in regions):
                self.u.hook_add(UC_HOOK_CODE, self.hook, begin=address, end=address)
        self.cpu_context = self.u.context_save()
        # What the game's own draw routines make of a traced object.
        self.town = Path(overlay.source.path).name.upper() if overlay and overlay.source else ''
        self.drawer = None
        self.draw_states = {}
        self.drawn = {}
        self.available = True
        self.reason = f'Initial poses traced from the {build.name} executable' + ('.' if build.legacy8 else ' and the area overlay.')

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
        return tuple((self.exe_word(table + i * 4) - (0x1F8001D8 if self.build.legacy8 else APD_TABLE)) // 4
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
        [(tpage, x, y, u, v, width, height, clut, blend)], in the order
        of the table."""
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
                blend = self.build.picture_record >= 18 and bool(struct.unpack('<h', self.read(at + 16, 2))[0])
                parts.append((tpage & 0x1FF, x, y + self.build.picture_top, u, v, width, height,
                              (clut_y & 511) << 6 | (clut_x >> 4) & 63, blend))
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
            self.spawn(obj, placement)
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

    def model_colour_animation(self, placement, model):
        """Run the model writer called by an object's update states.

        A model can be a zero-colour template until a later state fills it.
        Execute actual callees in isolation and accept only colour changes
        to the same validated mesh; no material is guessed or copied in.
        """
        state = self.object_states.get((placement.raw, placement.position))
        if state is None or model not in self.model_spans:
            return [], None
        from formats.sprites.ownership import Ownership
        from formats.models.wmd import parse_wmd
        if not hasattr(self, 'animation_ownership'):
            self.animation_ownership = Ownership([
                ('overlay', self.build.overlay, self.overlay_code),
                ('executable', self.base, self.exe[0x800:])], 0x1F800150 if self.build.legacy8 else SPR_TABLE)
        pc = self.handler_address(placement)
        calls, pending = set(), [(pc, 0)]
        while pending and len(calls) < 64:
            routine, depth = pending.pop()
            if depth >= 3:
                continue
            for call in self.animation_ownership.scan(routine)[1]:
                if call not in calls and self.animation_ownership.memory.region(call) == 'overlay':
                    calls.add(call)
                    pending.append((call, depth + 1))
        address, size = self.model_spans[model]
        original = self.read(address, size)
        envelope = struct.pack('<2I', 1, 8)
        reference = parse_wmd(envelope + original)[0]
        positions = [p['vertices'] for p in reference.polygons]
        for call in sorted(calls):
            if self.animation_ownership.memory.region(call) != 'overlay':
                continue
            self.write(0x80000000, self.baseline)
            self.write(0x1F800000, self.scratch)
            self.write(OBJECT, state)
            self.write(address, original)
            self.write(OBJECT + 6, b'\0')
            seen, frames = set(), []
            try:
                for _ in range(32):
                    self.run_handler(call, OBJECT, 30000)
                    now = self.read(address, size)
                    if now == original:
                        break
                    mesh = parse_wmd(envelope + now)[0]
                    if ([p['vertices'] for p in mesh.polygons] != positions or
                            not any(np.any(p['colors']) for p in mesh.polygons)):
                        break
                    if now in seen:
                        self.write(address, original)
                        return frames, call
                    seen.add(now)
                    frames.append((now, 1))
            except Exception:
                pass
            finally:
                self.write(address, original)
        return [], None

    def backdrop_motion(self, obj, pc, placement):
        """How a layer 7 object reaches the screen.

        On each update it turns its placement into a position on the
        320 x 240 screen from the camera words at 1F800176 (X) and 1F800186
        (Y). Running that update with the camera at the origin and nudged on
        each axis gives the screen position and the fraction of camera
        movement the sprite follows. Objects that stay at their placement are
        ordinary world sprites and return nothing."""
        if not self.measure_backdrops:
            return {}
        r, ready, scratch = self.reg, self.read(obj, 0x200), self.read(0x1F800000, 0x1000)

        def update(camera_x, camera_y):
            self.write(obj, ready)
            self.write(0x1F800000, scratch)
            self.write(0x1F80028A if self.build.legacy8 else CAMERA_X, struct.pack('<h', camera_x))
            self.write(0x1F80028E if self.build.legacy8 else CAMERA_Y, struct.pack('<h', camera_y))
            try:
                self.run_handler(pc, obj, 4000)
            except Exception:
                pass
            moved = self.read(obj, 0x20)
            return struct.unpack_from('<h', moved, 0x12)[0], struct.unpack_from('<h', moved, 0x16)[0]

        anchor = tuple(placement.position[:2])
        base = follow = None
        # A sprite that is off the screen is left where it was, so look from
        # a few camera positions until it shows: along the level at its top,
        # then round the placement at its height. Some only update once the
        # camera has passed them.
        for start, height in [(start, 0) for start in (0, 512, 1024, 1536)] + \
                [(start, anchor[1] - 120) for start in (anchor[0] - 160, anchor[0], anchor[0] + 160, 2048, 4096)]:
            seen, across, down = update(start, height), update(start + NUDGE, height), update(start, height + NUDGE)
            if seen != anchor and across != anchor and down != anchor:
                follow = ((seen[0] - across[0]) / NUDGE, (seen[1] - down[1]) / NUDGE)
                base = (round(seen[0] + start * follow[0]), round(seen[1] + height * follow[1]))
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
            travel = next((c for c in (256, 512, 1024, 2048, 4096, 8192) if update(start + c, height) == seen), 0)
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
            frames.append((frame, control & 0x3FFF or 65536))
            if control & 0xC000 == 0x8000:
                break
            address = self.read_word(address + 8) if control & 0x4000 else address + 8
        return frames

    def spawners(self):
        """Routines of the loaded code that create objects: those that call
        a routine reading an object pool's free list."""
        if hasattr(self, '_spawners'):
            return self._spawners
        import bisect
        from formats.sprites.animations import code_constants, routines
        heads = {head for _, head, _, _, _ in POOLS}
        images = [(self.build.overlay, bytes(self.overlay_code)), (self.base, bytes(self.exe[0x800:]))]
        starts, pools = {}, set()
        for base, data in images:
            starts[base] = sorted(routines(base, data))
            for value, where in code_constants(base, data).items():
                if value in heads:
                    for at in where:
                        k = bisect.bisect_right(starts[base], at) - 1
                        if k >= 0:
                            pools.add(starts[base][k])
        calls = [3 << 26 | (address >> 2) & 0x3FFFFFF for address in pools]
        found = set()
        for base, data in images:
            words = np.frombuffer(data[:len(data) // 4 * 4], '<u4')
            for i in np.nonzero(np.isin(words, calls))[0]:
                k = bisect.bisect_right(starts[base], base + 4 * int(i)) - 1
                if k >= 0:
                    found.add(starts[base][k])
        self._spawners = sorted(found - pools)
        return self._spawners

    def spawn_from(self, pc, argument):
        """Placements of the objects routine `pc` creates when a made-up
        object calls it with `argument` (and zeros after it). What takes its
        page or its bank from the caller is left out: the caller is made up."""
        from unicorn import UcError
        from formats.level.apd import Placement
        self.write(0x80000000, self.baseline)
        self.write(0x1F800000, self.scratch)
        self.prepare_pools()
        self.spawn(OBJECT, Placement(0, bytes(16), (0, 0, 0)))
        self.write(OBJECT + 0x1E, struct.pack('<H', CALLER_PAGE))
        self.word(OBJECT + 0x3C, CALLER_BANK)
        r = self.reg
        try:
            self.u.context_restore(self.cpu_context)
            for register, value in ((r.UC_MIPS_REG_SP, 0x803F0000), (r.UC_MIPS_REG_RA, 0x80001000),
                                    (r.UC_MIPS_REG_A0, OBJECT), (r.UC_MIPS_REG_A1, argument),
                                    (r.UC_MIPS_REG_A2, 0), (r.UC_MIPS_REG_A3, 0)):
                self.u.reg_write(register, value)
            self.u.emu_start(pc, 0x80001000, count=20000)
        except (UcError, OSError):
            # A routine that needs a real caller can stop Unicorn itself.
            return []
        return [self.child(pool, address, state) for pool, address, state in self.spawned()
                if struct.unpack_from('<H', state, 0x1E)[0] != CALLER_PAGE
                and struct.unpack_from('<I', state, 0x3C)[0] != CALLER_BANK]

    def animation_memory(self):
        """The overlay and the executable as formats.sprites.animations
        reads them."""
        if not hasattr(self, '_animation_memory'):
            from formats.sprites.animations import Memory
            self._animation_memory = Memory([('overlay', self.build.overlay, self.overlay_code),
                                             ('executable', self.base, self.exe[0x800:])])
        return self._animation_memory

    def code_animations(self, pc, slot, count):
        """Scripts assigned to anim +24 by this object's reachable code."""
        if not pc or not count:
            return {}
        if not hasattr(self, 'animation_ownership'):
            from formats.sprites.ownership import Ownership
            self.animation_ownership = Ownership([
                ('overlay', self.build.overlay, self.overlay_code),
                ('executable', self.base, self.exe[0x800:])], 0x1F800150 if self.build.legacy8 else SPR_TABLE)
        return self.animation_ownership.scripts(pc, slot, count)

    def animation_preview(self, placement, visual):
        """An assigned motion containing the held initialization pose.

        Initializers often select a one-frame wait. Use its handler's motion
        containing that pose for inspection; this is not a simulation of AI.
        """
        if len(visual.get('frames', ())) != 1 or placement.layer == 7:
            return visual
        slot = visual.get('sprite')
        if slot is None:
            return visual
        bank = self.read_word((0x1F800150 if self.build.legacy8 else SPR_TABLE) + slot * 4)
        count = struct.unpack('<H', self.read(bank + 2, 2))[0] // 4
        frame = visual['frames'][0][0]
        choices = [s for s in self.code_animations(self.handler_address(placement), slot, count).values()
                   if frame in s.frames and len(set(s.frames)) > 1 and s.loop is not None]
        if not choices:
            return visual
        script = min(choices, key=lambda s: (len(s.steps), s.address))
        return dict(visual, frames=[(s.frame, s.ticks or 65536) for s in script.steps],
                    animation_preview=script.address, animation_initial=visual['animation_address'])

    def code_frames(self, pc, near, count):
        """Frames of the other animations an object's code can start.

        An object is created showing one animation; the rest of what it
        does (walking, talking, breaking) is set by its routine and the
        routines that one calls, each loading the address of a script or of
        one fixed pointer to a script. `pc` is the object's routine, `near`
        the script it starts with and `count` the number of frames in its
        bank.

        Only scripts stored close to the first are taken: a class keeps its
        scripts together, and what its code loads from elsewhere belongs to
        something it creates. A pointer reached by indexing a table is not
        followed, since which entry is read depends on the object's
        variant; pointers that lie between two the code names are, being
        the same object's states picked by number."""
        key = (pc, near, count)
        if key in self.reach:
            return self.reach[key]
        low, high = self.build.overlay, self.build.overlay + len(self.overlay_code)
        words, code = self.overlay_words, self.overlay_code
        seen, queue, frames, cells = set(), [pc], set(), set()

        def script(address):
            """Frames of the script at `address`, or None if it is not one."""
            if not (low <= address < high) or address & 3 or abs(address - near) > CLASS_SCRIPTS:
                return None
            found, at = [], address
            while len(found) < 64 and low <= at < high - 8:
                frame, a, b, control = struct.unpack_from('<4H', code, at - low)
                if frame >= count or a or b or (control & 0x3FFF) > 2000:
                    return None
                found.append(frame)
                if control & 0xC000:
                    return found
                at += 8
            return None

        def pointed(cell):
            return script(struct.unpack_from('<I', code, cell - low)[0]) if low <= cell < high - 4 else None

        while queue and len(seen) < 48:
            start = queue.pop()
            if start in seen or not (low <= start < high):
                continue
            seen.add(start)
            index = (start - low) // 4
            upper = {}
            for i in range(index, min(len(words), index + 0x600)):
                word = int(words[i])
                op, rs, rt, imm = word >> 26, word >> 21 & 31, word >> 16 & 31, word & 0xFFFF
                if i > index and word >> 16 == 0x27BD and imm & 0x8000:
                    break               # the next routine's stack frame
                if op == 3:
                    queue.append(0x80000000 | (word & 0x3FFFFFF) << 2)
                elif op == 15:
                    upper[rt] = (imm << 16, i)
                elif op == 0 and (word >> 11 & 31) in upper:
                    upper.pop(word >> 11 & 31)      # indexed: not one fixed address
                elif op in (9, 13, 35) and rs in upper and i - upper[rs][1] < 8:
                    address = (upper[rs][0] + (imm if op == 13 else (imm ^ 0x8000) - 0x8000)) & 0xFFFFFFFF
                    found = script(address)
                    if found:
                        frames.update(found)
                    found = pointed(address)
                    if found:
                        frames.update(found)
                        cells.add(address)
        if cells and max(cells) - min(cells) <= SCRIPT_RUN:
            for cell in range(min(cells), max(cells), 4):
                frames.update(pointed(cell) or ())
        self.reach[key] = frames
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
        if build.legacy8:
            along0, depth0 = struct.unpack_from('<hh', self.exe,
                build.origins + area * 24 + section * 4 - self.base + 0x800)
            return along0, depth0, False, 0
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
        key = (placement.raw, placement.position, placement.extra, placement.memory)
        if key not in self.cache:
            # Most initialisers finish on their own. Some run into parts of
            # the game that are not here; for those, stopping where the
            # animation is set is enough to learn what the object shows.
            self.cache[key] = self.attempt(placement, False) or self.attempt(placement, True)
            pond_fish = self.area == 0 and (placement.layer, placement.kind) == (3, 0x5A)
            if (not self.cache[key] and not self.build.early and (pond_fish or (placement.layer == 5
                    and placement.kind == 4 and placement.variant == 3 and placement.raw[3] == 1))):
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
                    result['condition'] = ('Pond fish' if pond_fish else 'Conditional collectible') + ': the game shows it when its event flag is FF. Enable Event previews to inspect it.'
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

    def spawn(self, obj, placement):
        """Fill a cleared object from a placement record as the record
        spawner does (routine 8004CB00 of the European build): the record's
        bytes go to their fields, and +6B gets the record's room number from
        byte 15, less one for a section's own list (an area-wide record or a
        script sets it with `extra`). Layer 3 scenery of types 18, 19, 24
        and 33 also takes its box from byte 14."""
        raw = placement.raw
        self.write(obj, bytes(0x200))
        self.word(obj + 0x40, obj + 0x10)
        self.word(obj + 0x44, obj + 0x18)
        self.write(obj, bytes((1, 0, raw[2], raw[4])))
        for offset, value in ((0xC, raw[3]), (0xA, raw[12]), (0xF, raw[13]), (0x1C, raw[1]), (0x1D, raw[0]),
                              (0x6B, ((raw[15] >> 2) - 1) & 0xFF)):
            self.write(obj + offset, bytes((value,)))
        self.write(obj + 0x2E, bytes((raw[5], 0)))
        if raw[1] & 0x7F == 3 and raw[2] in (0x18, 0x19, 0x24, 0x33):
            self.write(obj + 0x6C, struct.pack('<h', raw[14]))
        for j, value in enumerate(placement.position):
            self.word(obj + 0x10 + j * 4, value << 16)

    def draw(self, placement, frame=None):
        """The primitives the game's draw routine makes of a traced sprite
        object (formats.level.draw), relative to its position, showing SPR
        frame `frame` or the one it starts on. None when the object was not
        traced to a sprite or the routine draws nothing."""
        if self.available and self.build.legacy8:
            return None
        key = (placement.raw, placement.position, placement.extra, placement.memory)
        state = self.draw_states.get(key)
        if state is None:
            return None
        if (key, frame) not in self.drawn:
            if self.drawer is None:
                from formats.level.draw import DrawCapture, town_of
                self.drawer = DrawCapture(self.exe, self.base, self.read, town_of(self.town))
                self.drawer.load([(0x80000000, self.baseline), (SPR_MEMORY, WMD_MEMORY - SPR_MEMORY)])
            obj, nearby, scratch = state
            prims = None
            if self.drawer.available:
                try:
                    # The category byte is cleared when an object frees
                    # itself; its layer is the list it was drawn from.
                    prims = self.drawer.capture(OBJECT, obj, scratch, category=placement.layer, frame_entry=frame,
                                                memory=[(OBJECT + 0x4000, nearby)])
                except Exception:
                    prims = None
            self.drawn[key, frame] = prims or None
        return self.drawn[key, frame]

    def handler_address(self, placement):
        """The actual dispatch entry, for inspection of a placed object."""
        if not self.available:
            return None
        table = self.build.tables.get(placement.layer)
        return self.read_word(table + placement.kind * 4) if table is not None else None

    def attempt(self, placement, stop_at_animation):
        if self.build.legacy8:
            from formats.level.prepre8 import attempt
            return attempt(self, placement, stop_at_animation)
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
        self.prepare_pools()
        for address, data in placement.memory:
            self.write(address, data)
        self.spawn(obj, placement)
        self.write(obj + 0x74, struct.pack('<3h', 4096, 4096, 4096))
        if placement.model in self.model_spans:
            self.word(obj + 0xA0, self.model_spans[placement.model][0])
            self.write(obj + 0xA4, b'\x01')
        for offset, value in placement.extra:
            self.write(obj + offset, value)
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
            self.word(OBJECT + 0x4000 + 0x94, obj)
            for j, value in enumerate(struct.unpack_from('<3h', raw, 6)):
                self.word(obj + 0x30 + j * 4, value << 16)
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
                    result['lit'] = bool(self.read(obj + 0xA4, 1)[0])
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
                        if placement.layer != 7:
                            self.draw_states[(raw, placement.position, placement.extra, placement.memory)] = (
                                self.read(obj, 0x200), self.read(OBJECT + 0x4000, 0x400 * max(1, len(parents))),
                                self.read(0x1F800000, 0x400))
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
                        result['shade'] = self.read(obj + 0x6B, 1)[0]
                        result['sort_bias'] = struct.unpack_from('<b', state, 0xF)[0]
                        result['sort_fixed'] = bool(state[0xB])
                        result['sort_depth'] = struct.unpack_from('<h', state, 0x1A)[0]
                        result['screen_bias'] = (struct.unpack_from('<h', state, 0xE)[0]
                                                 if state[0xB] == 2 else result['sort_bias'])
                        if placement.layer == 7:
                            # Backdrop strips name a second frame in the word
                            # after the first; both are drawn at the anchor.
                            result['overlay'] = struct.unpack('<H', self.read(anim + 2, 2))[0]
                            if raw[12] == 4:
                                result['overlay_rise'] = struct.unpack('<h', self.read(obj + 0x20, 2))[0]
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
        if result:
            children = self.spawned()
            if children:
                result['spawned'] = children
        return result

    def prepare_pools(self):
        """Give every object free list its spare, cleared slots."""
        if self.build.legacy8:
            from formats.level.prepre8 import prepare_pools
            return prepare_pools(self)
        for k, (name, items, count, slots, size) in enumerate(POOLS):
            start = SPAWN_AT + k * 0x8000
            self.write(start, bytes(slots * size))
            listed = POOL_LISTS + k * 0x100
            self.write(listed, struct.pack(f'<{slots}I', *(start + i * size for i in range(slots))))
            self.word(items, listed)
            self.write(count, struct.pack('<h', slots))

    def spawned(self):
        """[(pool name, address, bytes)] of the spare slots now in use."""
        if self.build.legacy8:
            from formats.level.prepre8 import spawned
            return spawned(self)
        out = []
        for k, (name, items, count, slots, size) in enumerate(POOLS):
            start = SPAWN_AT + k * 0x8000
            pool = self.read(start, slots * size)
            for i in range(slots):
                if pool[i * size]:
                    out.append((name, start + i * size, pool[i * size:(i + 1) * size]))
        return out

    def child(self, pool, address, state, parent=None, origin=''):
        """A Placement for an object found in a spare slot: its fields as the
        spawner left them, with the spawning object's memory copied to where
        its pointers point (`parent`: (address, bytes))."""
        from formats.level.apd import Placement
        layer = state[0x1C] & 0x7F
        position = tuple(struct.unpack_from('<h', state, at)[0] for at in (0x12, 0x16, 0x1A))
        raw = bytearray(16)
        raw[0], raw[1], raw[2], raw[3], raw[4], raw[5] = state[0x1D], state[0x1C], state[2], state[0xC], state[3], state[0x2E]
        struct.pack_into('<3h', raw, 6, *position)
        raw[12], raw[13] = state[0xA], state[0xF]
        body = bytearray(state[:0x200].ljust(0x200, b'\0'))
        memory = ()
        if parent is not None:
            # Pointers into the spawner are pointed at its copy.
            at, data = parent
            copy = OBJECT + 0x4000
            for offset in range(0, len(body) - 3, 4):
                pointer = struct.unpack_from('<I', body, offset)[0]
                if at <= pointer < at + len(data):
                    struct.pack_into('<I', body, offset, copy + pointer - at)
            memory = ((copy, bytes(data)),)
        # The coordinate pointers are set again for the tracer's object.
        extra = ((0, bytes(body[:0x40])), (0x48, bytes(body[0x48:0xD4])))
        native = 0
        if self.build.legacy8:
            native = raw[1] & 127
            raw[1] = (raw[1] & 128) | {4: 3, 5: 4, 6: 5, 7: 8, 8: 7, 9: 8}.get(native, native)
        return Placement(-1, bytes(raw), position, extra=extra, memory=memory, origin=origin, native_layer=native)

    def entry_hook(self):
        """The routine Tomba's start (playerInitMode, 800F0490 in the
        European overlays) runs for the area when he enters a section, or
        None. It is reached through a jump table on the area word; every
        case that has a routine is `jal routine; move a0, s0`."""
        if not self.available:
            return None
        if hasattr(self, '_entry_hook'):
            return self._entry_hook
        self._entry_hook = None
        words = self.overlay_words
        base = self.build.overlay
        low = self.build.area & 0xFFFF
        high = (self.build.area + 0x8000) >> 16 & 0xFFFF
        for i in range(len(words) - 12):
            w = int(words[i])
            # lhu reg, low(area) after a lui of its upper half
            if w >> 26 != 0x25 or w & 0xFFFF != low or int(words[i - 1]) != (0x3C000000 | (w >> 21 & 31) << 16 | high):
                continue
            reg = w >> 16 & 31
            follow = [int(x) for x in words[i + 1:i + 10]]
            limit = next((x & 0xFFFF for x in follow if x >> 26 == 0x0B and (x >> 21 & 31) == reg), None)
            lui_at = next((k for k, x in enumerate(follow) if x >> 16 == 0x3C01), None)
            if limit is None or lui_at is None:
                continue
            loads = [x for x in follow[lui_at + 1:] if x >> 26 == 0x23 and (x >> 21 & 31) == 1]
            if not loads:
                continue
            table = ((follow[lui_at] & 0xFFFF) << 16) + ((loads[0] & 0xFFFF ^ 0x8000) - 0x8000) & 0xFFFFFFFF
            cases = []
            for k in range(limit):
                try:
                    case = self.read_word(table + 4 * k)
                    first, second = struct.unpack('<II', self.read(case, 8))
                except Exception:
                    cases = []
                    break
                cases.append(0x80000000 | (first & 0x3FFFFFF) << 2 if first >> 26 == 3 and second == 0x02002021 else None)
            if sum(c is not None for c in cases) >= 3:
                if self.area < len(cases):
                    self._entry_hook = cases[self.area]
                break
        return self._entry_hook

    def entry_spawns(self):
        """What Tomba's entry into the section spawns: the area's entry
        routine (entry_hook) run once on a stand-in for him, with a new
        game's flags. [(pool, address, bytes)]."""
        hook = self.entry_hook()
        if hook is None:
            return []
        from unicorn import UcError
        self.write(0x80000000, self.baseline)
        self.write(0x1F800000, self.scratch)
        self.prepare_pools()
        self.write(PLAYER_STANDIN, bytes(0x200))
        self.word(PLAYER_STANDIN + 0x40, PLAYER_STANDIN + 0x10)
        self.word(PLAYER_STANDIN + 0x44, PLAYER_STANDIN + 0x18)
        try:
            self.stop_at_animation = False
            self.run_handler(hook, PLAYER_STANDIN, 200000)
        except UcError:
            pass
        return self.spawned()

    def controller_spawns(self):
        """[(type, variant, [(pool, address, bytes)])]: what each section
        controller spawns. The controllers are listed by area and section in
        the executable (build.controllers); each is made in a spare slot,
        started if its record says so, and updated CONTROLLER_UPDATES times."""
        if not self.available or not self.build.controllers:
            return []
        lists, routines = self.build.controllers
        area, section = self.requested
        out = []
        try:
            table = self.exe_word(lists + area * 4)
            if not self.in_exe(table + section * 4, 4):
                return []
            at = self.exe_word(table + section * 4)
            records = []
            while self.in_exe(at, 4) and self.exe[at - self.base + 0x800] != 0xFF and len(records) < 32:
                records.append(struct.unpack_from('<4B', self.exe, at - self.base + 0x800))
                at += 4
        except struct.error:
            return []
        from unicorn import UcError
        for kind, variant, _, start in records:
            pc = self.exe_word(routines + kind * 4) if self.in_exe(routines + kind * 4, 4) else None
            if pc is None:
                continue
            self.write(0x80000000, self.baseline)
            self.write(0x1F800000, self.scratch)
            self.prepare_pools()
            self.write(CONTROLLER, bytes(0x40))
            self.write(CONTROLLER, bytes((1, 0, kind, variant)))
            try:
                for _ in range(CONTROLLER_UPDATES + (1 if start else 0)):
                    self.stop_at_animation = False
                    self.run_handler(pc, CONTROLLER, 20000)
                    if not self.read(CONTROLLER, 1)[0]:
                        break
            except UcError:
                pass
            out.append((kind, variant, self.spawned()))
        return out


def item_sprites(project, table=None, overlay=None, counts=None):
    """{SPR slot: {frame: (texture page base, CLUT word or None)}} for the
    pictures of items, from the item descriptors in the executable.

    The item routine (8003FDD4 in US retail) looks an item's type up in a
    table of descriptor numbers and copies a twenty-byte descriptor into
    the object: draw mode, page base, SPR slot, the flags of +0D, how the
    palette is chosen, how the animation is, the palette's place in VRAM,
    a box and a pointer to the animations. The palette is the one named
    (0), the row below it by the variant (1), one of a table by the variant
    (2) or the row below by two event flags (3); the animation the first
    (0) or the variant's (1).

    A descriptor's animations are in the executable or in one area's
    overlay. `overlay` is the code loaded with the bank being looked at and
    `counts` the number of frames in each loaded bank by slot: a descriptor
    pointing into the overlay is taken when its scripts read as scripts of
    that bank, and otherwise belongs to another area."""
    found = executable(project, table)
    if found is None or not found.build.items:
        return {}
    index, pointers, palettes = found.build.items
    out = {}

    low = found.build.overlay
    high = low + (len(overlay) if overlay is not None else 0)

    def peek(fmt, address):
        """Read from the executable or the overlay; None outside both."""
        size = struct.calcsize(fmt)
        if found.holds(address, size):
            return found.unpack(fmt, address)
        if low <= address and address + size <= high:
            return struct.unpack_from(fmt, overlay, address - low)
        return None

    def frames(script, limit):
        """Frames of a script, or [] when it does not read as one."""
        seen = []
        while len(seen) < 64:
            step = peek('<4H', script)
            if step is None:
                return []
            frame, a, b, control = step
            if not found.holds(script, 8) and (a or b or frame >= limit):
                return []
            seen.append(frame)
            if control & 0xC000:
                return seen
            script += 8
        return []

    def clut(x, y):
        return (y & 511) << 6 | (x >> 4) & 63

    numbers = found.data[index - found.base + 0x800: pointers - found.base + 0x800]
    for number in sorted(set(numbers)):
        at = found.word(pointers + number * 4)
        if not found.holds(at, 20):
            continue
        _, _, page, _, slot, flags, palette, varied, x, y, _, anims = found.unpack('<8Bhh4sI', at)
        limit = (counts or {}).get(slot, 0) if not found.holds(anims, 4) else 1 << 16
        for variant in range(16 if varied == 1 else 1):
            pointer = peek('<I', anims + variant * 4)
            if pointer is None or not limit:
                break
            script = pointer[0]
            if not flags & 1:
                word = None
            elif palette == 2:
                word = clut(*found.unpack('<hh', palettes + variant * 8))
            else:
                word = clut(x, y + (variant if palette == 1 else 0))
            shown = frames(script, limit)
            if not shown:
                break
            for frame in shown:
                out.setdefault(slot, {}).setdefault(frame, (page, word))
    return out


def table_pages(project, table=None):
    """Texture page base per SPR slot from the object table at 8007D6E4 in
    US retail (twelve-byte entries: page base, animation, slot, script
    pointer). Used for banks that no placed object shows. Empty for builds
    where the table has not been located."""
    found = executable(project, table)
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
