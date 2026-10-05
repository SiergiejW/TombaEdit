"""Bounded MIPS initialization traces for the verified US retail executable.

This is an initial-pose resolver, not a running PSX emulator. It executes a
single object's initializer in isolated memory. Audio, visibility and flag
queries are stubbed; no BIOS, files, devices or game loop are exposed.
Other builds keep their APD markers and directly linked models.
"""
import hashlib
import struct

US_SHA1 = '81cbc79f0230aeb4252e058039f47ac95a777f5a'
# Handler tables by APD layer. Layers 2 to 5 share one object pool (routine
# 8001DFE4); layer 7, the backdrop sprites, has its own pool and table
# (routine 8003438C).
# Layer 8 objects are models with a handler of their own, in a pool of 45
# run through this table (routine 8002DB4C).
MODEL_TABLE = 0x8007C68C
# Routines that append an object to one of the per-frame draw lists.
DRAW_QUEUES = (0x80018BC8, 0x80018C04, 0x80018C40, 0x80018C8C, 0x80018CC8, 0x80018D04, 0x80018D40)
# Camera step used to measure how far a backdrop sprite follows the camera.
NUDGE = 64
TABLES = {2: 0x800772BC, 3: 0x8007C6B0, 4: 0x8007D30C, 5: 0x8007E8A8, 7: 0x8007D57C}


class InitialPoseResolver:
    def __init__(self, project, area, section, resources):
        self.available = False
        self.reason = 'Object initialization is currently decoded for US retail.'
        self.cache = {}
        self.queued = set()
        self.stop_at_animation = False
        entries = [e for e in project.disc.files if e.path == 'SCUS_942.36']
        if not entries or area < 0:
            return
        exe = project.disc.read(entries[0])
        if hashlib.sha1(exe).hexdigest() != US_SHA1:
            return
        self.exe = exe
        self.base = struct.unpack_from('<I', exe, 0x18)[0]
        overlay = next((a for a in resources.values() if a.kind == 'INS'), None)
        if overlay is None:
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
        self.write(self.base, exe[0x800:])
        self.write(0x800E7388, project.asset_data(overlay))
        self.write(0x8009BCC8, struct.pack('<HH', area, max(0, section)))
        self.model_pointers = {}
        self.model_spans = {}      # (slot, index) -> (address, size)
        for (family, slot), asset in resources.items():
            if family not in ('SPR', 'WMD'):
                continue
            address = (0x80400000 if family == 'SPR' else 0x80800000) + slot * 0x40000
            data = project.asset_data(asset)
            if len(data) >= 0x40000:
                continue
            self.write(address, data)
            self.word((0x1F8002C8 if family == 'SPR' else 0x1F800330) + slot * 4, address)
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
        self.available = True
        self.reason = 'Initial poses traced from the US executable and the area X overlay.'

    def read(self, address, count):
        return bytes(self.u.mem_read(address & 0x1FFFFFFF, count))

    def write(self, address, data):
        self.u.mem_write(address & 0x1FFFFFFF, data)

    def word(self, address, value):
        self.write(address, struct.pack('<I', value & 0xFFFFFFFF))

    def read_word(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def exe_word(self, address):
        return struct.unpack_from('<I', self.exe, address - self.base + 0x800)[0]

    def placement_slots(self, area, section):
        table = self.exe_word(0x8007F0C8 + area * 4)
        common = min(15, struct.unpack_from('<H', self.exe, 0x8007B294 + area * 2 - self.base + 0x800)[0])
        return tuple((self.exe_word(table + i * 4) - 0x1F800358) // 4
                     for i in (section & 7, common))

    def picture_parts(self, placement):
        """Rectangles a layer 7 object in draw mode 2 is made of.

        The backdrop draw list (routine 8004DE40) picks a routine by the
        object's byte +0A, which is APD byte 12. Mode 2 (routine 8004E244)
        draws a fixed picture: the table at 8007EBEC, indexed by the variant,
        points at 18-byte records ending in 7FFF. A record is a texture page
        word, an X and Y offset from the object, U, V, width, height, the
        palette's VRAM position and a blend flag. Returns
        [(tpage, x, y, u, v, width, height, clut)]."""
        if not self.available or placement.layer != 7 or placement.raw[12] != 2:
            return []
        try:
            at = self.read_word(0x8007EBEC + placement.variant * 4)
            parts = []
            while len(parts) < 64 and 0x80010000 <= at < 0x80140000:
                tpage, x, y, u, v, width, height, clut_x, clut_y, _ = struct.unpack('<hhhBBHHhhh', self.read(at, 18))
                if tpage == 0x7FFF:
                    return parts
                if not (0 < width <= 256 and 0 < height <= 256):
                    break
                parts.append((tpage & 0x1FF, x, y, u, v, width, height, (clut_y & 511) << 6 | (clut_x >> 4) & 63))
                at += 18
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
        r, raw, obj = self.reg, placement.raw, 0x80300000
        address, size = self.model_spans[placement.model]
        original = self.read(address, size)
        pc = self.read_word(MODEL_TABLE + placement.kind * 4)
        x, y = placement.position[:2]
        found = []
        for camera in ((x - 160, y - 120), (0, 0), (x + 200, y - 120), (x - 500, y - 120)):
            self.write(0x80000000, self.baseline)
            self.write(0x1F800000, self.scratch)
            self.write(address, original)
            self.write(0x1F800176, struct.pack('<h', max(-32768, min(32767, camera[0]))))
            self.write(0x1F800186, struct.pack('<h', max(-32768, min(32767, camera[1]))))
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
                    self.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
                    self.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
                    self.u.reg_write(r.UC_MIPS_REG_A0, obj)
                    self.u.emu_start(pc, 0x80001000, count=20000)
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
            self.write(0x1F800176, struct.pack('<h', camera_x))
            self.write(0x1F800186, struct.pack('<h', camera_y))
            try:
                self.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
                self.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
                self.u.reg_write(r.UC_MIPS_REG_A0, obj)
                self.u.emu_start(pc, 0x80001000, count=4000)
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
        while address not in seen and len(frames) < 512 and 0x80010000 <= address < 0x80140000:
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
        if not self.available or not 0 <= area < 20 or not 0 <= section < 32:
            return None
        sections = self.exe_word(0x8007BF78 + area * 4)
        if not self.in_exe(sections + section * 4, 4):
            return None
        record = self.exe_word(sections + section * 4)
        if not self.in_exe(record, 8):
            return None
        return struct.unpack_from('<3h', self.exe, record - self.base + 0x800)

    def collision_frame(self, area, section):
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
        turned, slot = False, None
        entrance = None
        if not self.available or not 0 <= area < 20 or not 0 <= section < 32:
            return along0, depth0, turned, slot
        sections = self.exe_word(0x8007BF78 + area * 4)
        if self.in_exe(sections + section * 4, 4):
            entrances = self.exe_word(sections + section * 4)
            if self.in_exe(entrances, 8):
                entrance = struct.unpack_from('<3hH', self.exe, entrances - self.base + 0x800)
                turned = bool(entrance[3] & 1)
        table = self.exe_word(0x8007E9F8 + area * 4)
        if area in (4, 12) and section < 4:
            table, slot = 0x8007E9E8, int(turned)
        if section < 8 and self.in_exe(table + section * 4, 4):
            along0, depth0 = struct.unpack_from('<hh', self.exe, table + section * 4 - self.base + 0x800)
        # Sections limited to one plane (byte table at 8007EAF4) clamp every
        # depth to it, so their depth origin is not meaningful; the plane is
        # where Tomba enters.
        limits = self.exe_word(0x8007EAF4 + area * 4)
        single = self.in_exe(limits + section, 1) and self.exe[limits + section - self.base + 0x800] == 0
        if turned and single and entrance is not None and slot is None:
            depth0 = entrance[0]
        return along0, depth0, turned, slot

    def hook(self, uc, address, size, user):
        r = self.reg
        if address == 0x800229FC and self.stop_at_animation:
            self.completed = True
            uc.emu_stop()
        elif address == 0x800229FC:
            pass                # the animation setter runs like any other code
        elif address in (0x80022E44, 0x80022C08, 0x80022D3C, 0x80022F6C, 0x80023020, 0x800230BC):
            uc.reg_write(r.UC_MIPS_REG_V0, 1)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address == 0x8005DE78:
            # GetClut(x, y): objects that pick their palette this way keep it.
            x, y = uc.reg_read(r.UC_MIPS_REG_A0), uc.reg_read(r.UC_MIPS_REG_A1)
            uc.reg_write(r.UC_MIPS_REG_V0, (y & 511) << 6 | (x >> 4) & 63)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address in DRAW_QUEUES:
            # Handing an object to a draw list needs lists nobody set up here.
            # Which list it asked for says how it is drawn.
            self.queued.add(address)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address in (0x8001FFE8, 0x80023608, 0x800236F4):
            uc.reg_write(r.UC_MIPS_REG_V0, 0)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif not (0x80010000 <= address < 0x80097FA8 or 0x800E7388 <= address < 0x80140000):
            uc.emu_stop()

    def resolve(self, placement):
        if not self.available or placement.layer not in TABLES:
            return {}
        key = placement.raw
        if key not in self.cache:
            # Most initialisers finish on their own. Some run into parts of
            # the game that are not here; for those, stopping where the
            # animation is set is enough to learn what the object shows.
            self.cache[key] = self.attempt(placement, False) or self.attempt(placement, True)
        return self.cache[key]

    def attempt(self, placement, stop_at_animation):
        from unicorn import UcError
        self.stop_at_animation = stop_at_animation
        r, raw, obj = self.reg, placement.raw, 0x80300000
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
        for j, value in enumerate(placement.position):
            self.word(obj + 0x10 + j * 4, value << 16)
        pc = self.read_word(TABLES[placement.layer] + placement.kind * 4)
        result = {}
        try:
            for _ in range(4):
                self.completed = False
                self.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
                self.u.reg_write(r.UC_MIPS_REG_RA, 0x80001000)
                self.u.reg_write(r.UC_MIPS_REG_A0, obj)
                self.u.emu_start(pc, 0x80001000, count=4000)
                sprite = self.read_word(obj + 0x3C)
                anim = self.read_word(obj + 0x24)
                model = self.read_word(obj + 0xA0)
                if model in self.model_pointers:
                    result['model'] = self.model_pointers[model]
                    break
                if 0x80400000 <= sprite < 0x80800000 and (sprite - 0x80400000) % 0x40000 == 0:
                    if 0x80010000 <= anim < 0x80140000:
                        frames = self.animation(anim)
                        state = self.read(obj, 0x30)
                        # Draw routine 800487B0: bit 0 of +2E draws the parts as
                        # stored and a clear bit mirrors them about the origin;
                        # +1E is added to every part's texture page; bit 0 of
                        # +0D replaces the part CLUT with +08.
                        result.update(sprite=(sprite - 0x80400000) // 0x40000,
                                      frame=frames[0][0], frames=frames,
                                      flip=not state[0x2E] & 1,
                                      tpage=struct.unpack_from('<H', state, 0x1E)[0],
                                      clut=struct.unpack_from('<H', state, 8)[0] if state[0xD] & 1 else None,
                                      blend=bool(state[0xD] & 0x80))
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
            result = {}
        return result


def table_pages(project):
    """Texture page base per SPR slot from the US object table at 8007D6E4
    (twelve-byte entries: page base, animation, slot, script pointer). Used
    for banks that no placed object shows. Empty for other builds."""
    entries = [e for e in project.disc.files if e.path == 'SCUS_942.36']
    if not entries:
        return {}
    exe = project.disc.read(entries[0])
    if hashlib.sha1(exe).hexdigest() != US_SHA1:
        return {}
    base, votes, at = struct.unpack_from('<I', exe, 0x18)[0], {}, 0x8007D6E4
    while True:
        page, _, slot, pointer = struct.unpack_from('<BBhI', exe, at - base + 0x800)
        if not (0 <= slot < 16 and page < 32 and 0x80010000 <= pointer < 0x80200000):
            break
        votes.setdefault(slot, {}).setdefault(page, 0)
        votes[slot][page] += 1
        at += 12
    return {slot: max(pages, key=pages.get) for slot, pages in votes.items()}
