"""Psy-Q note2pitch: VAB fine units are 1/128 of a semitone.

The library indexes a 12 * 16 entry pitch table, then shifts by octave.
SPU pitch 0x1000 advances one source sample per 44,100 Hz output sample.
"""
import math


def spu_pitch(note, centre, fine=0, bend=0.0):
    semitone = int(note) + 60 - int(centre)
    step = min(15, max(0, int(fine) // 8))
    if bend:
        units = math.floor((semitone + bend) * 16) + step
        semitone, step = divmod(units, 16)
    octave, key = divmod(semitone, 12)
    pitch = int(4096 * 2 ** ((key * 16 + step) / 192))
    shift = octave - 5
    pitch = pitch << shift if shift >= 0 else pitch >> -shift
    return max(1, min(0x3fff, pitch))


def sample_rate(note, centre, fine=0):
    return round(44100 * spu_pitch(note, centre, fine) / 4096)
