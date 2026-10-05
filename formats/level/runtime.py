"""Bounded MIPS initialization traces for the verified US retail executable.

This is an initial-pose resolver, not a running PSX emulator. It executes a
single object's initializer in isolated memory. Audio, visibility and flag
queries are stubbed; no BIOS, files, devices or game loop are exposed.
Other builds keep their APD markers and directly linked models.
"""
import hashlib
import struct

US_SHA1 = '81cbc79f0230aeb4252e058039f47ac95a777f5a'
TABLES = {2: 0x800772BC, 3: 0x8007C6B0, 4: 0x8007D30C, 5: 0x8007E8A8}


class InitialPoseResolver:
    def __init__(self, project, area, section, resources):
        self.available = False
        self.reason = 'Object initialization is currently decoded for US retail.'
        self.cache = {}
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
                    for i, off in enumerate(struct.unpack_from(f'<{count}I', data, 4)):
                        self.model_pointers[address + off] = (slot, i)
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

    def collision_frame(self, area, section):
        """Where a section's collision sits: (x0, z0, step).

        Column 0 starts at x0 and plane 0 at z0 (table at 8007E9F8). Planes
        follow every `step` units of Z: 90, or -90 when the section's first
        entrance (table at 8007BF78, read by routine 800243E8) sets the flag
        that makes routine 80042654 count planes towards the camera."""
        x0 = z0 = 0
        step = 90
        if not self.available or not 0 <= area < 20 or not 0 <= section < 32:
            return x0, z0, step
        table = self.exe_word(0x8007E9F8 + area * 4)
        if section < 8 and self.in_exe(table + section * 4, 4):
            x0, z0 = struct.unpack_from('<hh', self.exe, table + section * 4 - self.base + 0x800)
        sections = self.exe_word(0x8007BF78 + area * 4)
        if self.in_exe(sections + section * 4, 4):
            entrances = self.exe_word(sections + section * 4)
            if self.in_exe(entrances, 8):
                if struct.unpack_from('<H', self.exe, entrances + 6 - self.base + 0x800)[0] & 1:
                    step = -90
        return x0, z0, step

    def hook(self, uc, address, size, user):
        r = self.reg
        if address == 0x800229FC:
            self.completed = True
            uc.emu_stop()
        elif address in (0x80022E44, 0x80022C08, 0x80022D3C, 0x80022F6C, 0x80023020, 0x800230BC):
            uc.reg_write(r.UC_MIPS_REG_V0, 1)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif address in (0x8001FFE8, 0x8005DE78, 0x80023608, 0x800236F4):
            uc.reg_write(r.UC_MIPS_REG_V0, 0)
            uc.reg_write(r.UC_MIPS_REG_PC, uc.reg_read(r.UC_MIPS_REG_RA))
        elif not (0x80010000 <= address < 0x80097FA8 or 0x800E7388 <= address < 0x80140000):
            uc.emu_stop()

    def resolve(self, placement):
        if not self.available or placement.layer not in TABLES:
            return {}
        key = placement.raw
        if key in self.cache:
            return self.cache[key]
        from unicorn import UcError
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
                        break
        except UcError:
            result = {}
        self.cache[key] = result
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
