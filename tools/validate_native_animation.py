"""Compare animation playback with bounded original MIPS service calls.

Run without arguments for the local JP, US and PAL retail CUEs, or supply
one or more disc paths. Optional --output writes the complete JSON trace.
The images are opened read-only. No game code or extracted artwork is saved.

The native routines receive synthetic animation entries in isolated RAM.
This checks timer words, script pointers and completion returns, not game
handler cadence, AI transitions, sprite rendering or PSX GPU fidelity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from formats.archive.ldar import Project
from formats.sprites.animations import AnimationCursor, Memory, read_script
from game.builds import executable


DEFAULT_IMAGES = (
    ROOT / 'rom/Ore! Tomba (Japan).cue',
    ROOT / 'rom/Tomba! (USA).cue',
    ROOT / 'rom/Tombi! (Europe) (En,Es,Pt,Sv,Da).cue',
)
OBJECT, SCRIPT, RETURN = 0x80300000, 0x80310000, 0x80001000
CONTROLS = ((0x0000, 'NEXT'), (0x4000, 'JUMP'), (0x8000, 'END'), (0xC000, 'JUMP_END'))


def require(condition, message):
    if not condition:
        raise AssertionError(message)


class NativeAnimation:
    """Run only AnimLoadDuration and AnimAdvance from a recognized image."""

    def __init__(self, exe):
        from unicorn import Uc, UC_ARCH_MIPS, UC_MODE_MIPS32, UC_MODE_LITTLE_ENDIAN
        from unicorn import mips_const
        self.reg = mips_const
        self.u = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 | UC_MODE_LITTLE_ENDIAN)
        self.u.mem_map(0, 0x400000)
        self.write(exe.base, exe.data[0x800:])
        self.context = self.u.context_save()
        self.load = exe.build.set_animation
        # Matched retail layout: AnimLoadDuration, AnimJump, then AnimAdvance.
        # JP 80020DE4/80020E38; US 800229FC/80022A50;
        # PAL 8001FE6C/8001FEC0. Every result below checks the actual service.
        self.advance = self.load + 0x54

    def write(self, address, data):
        self.u.mem_write(address & 0x1FFFFFFF, data)

    def read(self, address, size):
        return bytes(self.u.mem_read(address & 0x1FFFFFFF, size))

    def call(self, pc):
        r = self.reg
        self.u.context_restore(self.context)
        self.u.reg_write(r.UC_MIPS_REG_A0, OBJECT)
        self.u.reg_write(r.UC_MIPS_REG_SP, 0x803F0000)
        self.u.reg_write(r.UC_MIPS_REG_RA, RETURN)
        self.u.emu_start(pc, RETURN, count=1000)
        require(self.u.reg_read(r.UC_MIPS_REG_PC) == RETURN,
                f'Native service {pc:08X} did not return within 1000 instructions')
        return self.u.reg_read(r.UC_MIPS_REG_V0)

    def state(self, returned):
        pointer = struct.unpack('<I', self.read(OBJECT + 0x24, 4))[0]
        timer = struct.unpack('<H', self.read(OBJECT + 0x2C, 2))[0]
        return pointer, timer, returned


def validate_image(path):
    path = path.resolve()
    project = Project(path)
    exe = executable(project)
    require(exe is not None, f'No recognized executable profile for {path}')
    native = NativeAnimation(exe)
    cases, comparisons = [], 0
    for flag, name in CONTROLS:
        for timer in (0, 1, 2, 0x3FFF):
            payload = struct.pack('<HHhH', 1, 0, -2, flag | timer)
            if flag & 0x4000:
                payload += struct.pack('<I', SCRIPT)
            elif flag == 0:
                payload += struct.pack('<HHhH', 2, 0, 0, 0x8001)
            script = read_script(Memory([('test script', SCRIPT, payload)]), SCRIPT, 3)
            require(script is not None, f'Decoder rejected synthetic {name}/{timer} case')
            cursor = AnimationCursor(script)
            native.write(SCRIPT, payload)
            native.write(OBJECT, bytes(0x100))
            native.write(OBJECT + 0x24, struct.pack('<I', SCRIPT))
            native.call(native.load)
            loaded = struct.unpack('<H', native.read(OBJECT + 0x2C, 2))[0]
            require(loaded == timer, f'{exe.build.name}: AnimLoadDuration {loaded} != {timer}')
            samples, injected = [], False
            for index in range(5):
                python_return = cursor.tick()
                actual = native.state(native.call(native.advance))
                expected = (script.steps[cursor.step].address, cursor.left & 0xFFFF, int(python_return))
                require(actual == expected,
                        f'{exe.build.name}: {name}/{timer}, sample {index}: '
                        f'native {actual!r} != Python {expected!r}')
                samples.append(dict(sample=index, injected_boundary_before_call=injected,
                                    pointer=f'{actual[0]:08X}', timer_word=actual[1],
                                    completion_return=actual[2]))
                comparisons += 1
                # Check both ordinary countdown and transition boundaries in a
                # bounded run. This does NOT claim to execute 65536 native calls.
                injected = cursor.left > 10
                if injected:
                    cursor.left = 1
                    native.write(OBJECT + 0x2C, struct.pack('<H', 1))
            cases.append(dict(control=name, flags=f'0x{flag:04X}', timer_word=timer,
                              decoded_calls_per_step=script.steps[0].duration,
                              samples=samples))
    return dict(image=str(path), build=exe.build.name,
                executable_sha1=hashlib.sha1(exe.data).hexdigest(),
                executable_sha256=hashlib.sha256(exe.data).hexdigest(),
                anim_load_duration=f'{native.load:08X}', anim_advance=f'{native.advance:08X}',
                native_load_duration_calls_compared=len(cases),
                native_advance_calls_compared=comparisons, cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', type=Path, nargs='*', help='User-supplied retail CUE/BIN/ISO paths')
    parser.add_argument('--output', type=Path, help='Write the complete validation report as JSON')
    args = parser.parse_args()
    images = args.images or DEFAULT_IMAGES
    missing = [str(path) for path in images if not path.is_file()]
    if missing:
        parser.error('Disc image(s) not found: ' + ', '.join(missing))
    results = []
    for path in images:
        result = validate_image(path)
        results.append(result)
        print(f"{result['build']}: {result['native_advance_calls_compared']} AnimAdvance calls "
              f"and {result['native_load_duration_calls_compared']} AnimLoadDuration cases matched")
    report = dict(
        format='tomba-native-animation-validation-v1',
        scope='Bounded original AnimLoadDuration/AnimAdvance calls on synthetic scripts; '
              'not a game-loop, sprite-rendering or GPU validation.',
        boundary_method='For timers greater than ten after a comparison, both the native object '
                        'and Python cursor are set to one call remaining before the next sample. '
                        'Zero-timer wrap and native transition boundaries are therefore checked '
                        'without claiming full 65536-call native runs.',
        implementation_sha256=hashlib.sha256((ROOT / 'formats/sprites/animations.py').read_bytes()).hexdigest(),
        validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        native_load_duration_calls_compared=sum(r['native_load_duration_calls_compared'] for r in results),
        native_advance_calls_compared=sum(r['native_advance_calls_compared'] for r in results),
        images=results)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
        print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
