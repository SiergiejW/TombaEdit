"""SPU ADPCM and VAB decoding, shared with Tomba2Edit."""
import struct
MAGIC = b"pBAV"


HEADER = 32                 # VabHdr


PROGRAM_TABLE = 128 * 16    # ProgAtr[128]


TONE_TABLE = 16 * 32        # VagAtr[16], per program


SIZE_TABLE = 256 * 2        # waveform sizes, in units of 8 bytes


BLANK = 16                  # the empty block each waveform area opens with


BLOCK = 16                  # one ADPCM block: 2 header bytes, 28 samples


BLOCK_SAMPLES = 28


END = 0x01                  # last block of a waveform


REPEAT = 0x02               # on the last block: go back rather than stop


LOOP = 0x04                 # the block a repeat returns to


FILTERS = ((0, 0), (60, 0), (115, -52), (98, -55), (122, -60))


RATE = 22050


DEFINITIONS = 0x800A4D18


DEFINITION_SIZE = 8


def find_banks(data):
    """Every VAB header in the container, in file order."""
    out = []
    at = data.find(MAGIC)
    while at != -1:
        programs, _tones, vags = struct.unpack_from("<HHH", data, at + 18)
        head = header_length(programs)
        if at + head <= len(data):
            out.append({"offset": at, "programs": programs, "vags": vags,
                        "head": head, "end": at + head})
        at = data.find(MAGIC, at + 1)
    return out


def header_length(programs):
    return HEADER + PROGRAM_TABLE + programs * TONE_TABLE + SIZE_TABLE


def sizes(data, bank):
    """The waveform sizes of one bank, already in bytes."""
    at = bank["offset"] + HEADER + PROGRAM_TABLE + bank["programs"] * TONE_TABLE
    table = struct.unpack_from("<256H", data, at)
    return [table[i] * 8 for i in range(1, bank["vags"] + 1)]


def samples(data):
    """[(bank, index, offset, length)] for every waveform in the file.

    Banks whose headers run straight into one another share a waveform
    area and are handled as a group, which is what the first two in this
    file do; on its own, a bank is a group of one."""
    banks = find_banks(data)
    out = []
    group = []
    for n, bank in enumerate(banks):
        group.append((n, bank))
        packed = (n + 1 < len(banks)
                  and banks[n + 1]["offset"] == bank["end"])
        if packed:
            continue
        position = group[-1][1]["end"] + BLANK
        for number, member in group:
            for index, length in enumerate(sizes(data, member), start=1):
                out.append((number, index, position, length))
                position += length
        group = []
    return out


def decode(data, offset, limit):
    """One waveform as 16-bit samples.

    `limit` is what the size table recorded; decoding stops earlier if a
    block says it is the last, which is normal - the recorded size is
    rounded up and the final block or two are padding."""
    old = older = 0
    out = []
    for at in range(offset, offset + limit, BLOCK):
        block = data[at:at + BLOCK]
        if len(block) < BLOCK:
            break
        shift = block[0] & 0x0F
        if shift > 12:
            shift = 9               # what the hardware does with a bad shift
        k0, k1 = FILTERS[min(block[0] >> 4, 4)]
        for byte in block[2:]:
            for nibble in (byte & 0x0F, byte >> 4):
                if nibble > 7:
                    nibble -= 16
                value = (nibble << (12 - shift)) + ((old * k0 + older * k1) >> 6)
                value = -32768 if value < -32768 else (
                    32767 if value > 32767 else value)
                older, old = old, value
                out.append(value)
        if block[1] & END:
            break
    return out


def loops(data, offset, limit):
    """True if the waveform sustains rather than playing once through.

    What decides it is the repeat bit on the *last* block, not the loop
    marker: almost every waveform here marks its first block as a loop
    point, so reading that instead calls everything a loop."""
    for at in range(offset, offset + limit, BLOCK):
        block = data[at:at + BLOCK]
        if len(block) < BLOCK:
            break
        if block[1] & END:
            return bool(block[1] & REPEAT)
    return False


