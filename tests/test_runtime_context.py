"""Independent object calls must not inherit a stopped MIPS branch."""
import struct
import unittest
from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN, UC_HOOK_CODE
from unicorn import mips_const
from formats.level.runtime import InitialPoseResolver


class RuntimeContextTests(unittest.TestCase):
    def test_stopped_delay_slot_does_not_redirect_next_object(self):
        resolver = InitialPoseResolver.__new__(InitialPoseResolver)
        resolver.reg = mips_const
        resolver.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        resolver.u.mem_map(0, 0x400000)
        resolver.cpu_context = resolver.u.context_save()
        # Interrupt a jump just before its delay-slot instruction. A second
        # object then starts at a separate function that should write 7.
        jump = 0x08000000 | ((0x80002200 >> 2) & 0x3FFFFFF)
        resolver.write(0x80002000, struct.pack('<2I', jump, 0))
        resolver.write(0x80002200, struct.pack('<4I', 0x24080009, 0xAC880000, 0x03E00008, 0))
        resolver.write(0x80002100, struct.pack('<4I', 0x24080007, 0xAC880000, 0x03E00008, 0))
        resolver.u.hook_add(UC_HOOK_CODE, lambda u, address, size, data:
                            u.emu_stop() if address == 0x80002004 else None)
        resolver.run_handler(0x80002000, 0x80300000, 100)
        resolver.run_handler(0x80002100, 0x80300000, 100)
        self.assertEqual(resolver.read_word(0x80300000), 7)


if __name__ == '__main__':
    unittest.main()
