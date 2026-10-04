"""The STR movies: finding them, and taking them apart.

Tomba 2 has three - LOGO.STR, OP.STR and END.STR, in the disc's MOVIE
folder. An STR is not a container in any general sense; it is a run of
CD sectors written in the order the drive will read them, with the video
and the audio interleaved through each other so that neither has to be
buffered. Seven video sectors, one audio sector, over and over.

A video sector carries a 32-byte header saying which frame it belongs to
and how many sectors that frame spans, then 2016 bytes of the frame's
bitstream. Putting a frame back together is concatenating its sectors'
2016-byte pieces; decoding it is formats/movie/mdec.py.

An audio sector is ordinary CD-XA - the same Form 2 ADPCM as the music
and the voice - so formats/audio/xa.py decodes it unchanged.

Three sources work, and they are not equally good:

    a bin/cue data track     whole 2352-byte sectors. Both the video and
                             the audio survive, which is what you want.
    a 2048-byte .iso         the video, and nothing else.
    an extracted MOVIE\\*.STR the same again: 2048 bytes a sector,
                             because that is what copying a file off a
                             CD gives you.

The video survives a 2048-byte extraction because it only ever used
2048 bytes of its sectors. The audio does not: those are Form 2 sectors
holding 2324 bytes, and 276 bytes of every one of them are simply not
in the copy.
"""
import mmap
import os
import struct

from formats.movie import mdec
from formats.audio import xa

# The magic on a video sector's header: 0x0160, then 0x8001 for video.
VIDEO_MAGIC = 0x80010160
SECTOR_HEADER = 32
FLAT_SECTOR = 2048          # the user data in a sector, however it is framed

# The movies, in the order they are shown.
NAMES = ("LOGO.STR", "OP.STR", "END.STR")

# The drive plays a movie at double speed: 150 sectors a second. Used to
# work out the frame rate when a movie has no audio to measure against.
SECTORS_PER_SECOND = 150.0


class StrError(Exception):
    """Raised when a file cannot be read as an STR."""


class Movie:
    """One STR, indexed but not yet decoded.

    Indexing walks every sector once, which is a second or so for the
    24 MB END.STR, and after it a frame can be decoded on its own -
    every frame in an STR stands alone, so seeking is free."""

    def __init__(self, name, path, lba, count, stride=FLAT_SECTOR, offset=0):
        self.name = name
        self.path = path
        self.lba = lba              # 0 for an extracted file
        self.count = count          # sectors
        self.stride = stride        # bytes a sector in the file it is in
        self.offset = offset        # where user data starts in one
        self.width = 0
        self.height = 0
        self.version = 0
        self.frames = []            # [[sector index, ...], ...]
        self.audio_sectors = []
        self.rate = 37800
        self.channels = 2
        self._index()

    # --- reading sectors ------------------------------------------------

    @property
    def raw(self):
        """Whether this copy has whole CD sectors, and so any audio."""
        return self.stride == xa.SECTOR

    def _sector(self, handle, index):
        handle.seek((self.lba + index) * self.stride)
        return handle.read(self.stride)

    def _payload(self, sector):
        """The 2048 bytes of user data in a sector, however it is framed."""
        return sector[self.offset:self.offset + FLAT_SECTOR]

    def _index(self):
        """Walk the movie once and note where every frame's sectors are.

        Frames are keyed by the number in their sector headers rather
        than by counting: a movie that is cut short mid-frame, or one
        whose last frame is short a sector, should still list the frames
        that are whole."""
        frames = {}
        order = []
        with open(self.path, "rb") as f:
            for index in range(self.count):
                sector = self._sector(f, index)
                if len(sector) < self.stride:
                    break
                if self.raw:
                    submode = sector[xa.SUBHEADER + 2]
                    if submode & 0x24 == 0x24:          # Form 2 audio
                        self.audio_sectors.append(index)
                        self.rate, self.channels = _coding(
                            sector[xa.SUBHEADER + 3])
                        continue
                payload = self._payload(sector)
                if len(payload) < SECTOR_HEADER:
                    continue
                magic, chunk, chunks, number, size, width, height = \
                    struct.unpack_from("<IHHIIHH", payload, 0)
                if magic != VIDEO_MAGIC:
                    continue
                if not self.width:
                    self.width, self.height = width, height
                    header = mdec.frame_header(payload[SECTOR_HEADER:])
                    self.version = header[2] if header else 0
                if number not in frames:
                    frames[number] = [None] * chunks
                    order.append(number)
                pieces = frames[number]
                if chunk < len(pieces):
                    pieces[chunk] = index
        self.frames = [frames[n] for n in order
                       if all(piece is not None for piece in frames[n])]

    # --- what the movie is ----------------------------------------------

    @property
    def has_audio(self):
        return bool(self.audio_sectors)

    @property
    def audio_samples(self):
        """Samples per channel in the movie's audio."""
        return (len(self.audio_sectors) * xa.SAMPLES_PER_SECTOR
                // max(self.channels, 1))

    @property
    def fps(self):
        """Frames a second.

        Measured against the audio where there is any: the movie is as
        long as its soundtrack, and dividing the frames by that is the
        only figure that keeps the two together in an export. Without
        audio there is nothing to measure against, so it falls back to
        the rate the drive reads at."""
        if not self.frames:
            return 0.0
        if self.has_audio and self.audio_samples:
            return len(self.frames) / (self.audio_samples / self.rate)
        return len(self.frames) * SECTORS_PER_SECOND / max(self.count, 1)

    @property
    def duration(self):
        """Seconds."""
        return len(self.frames) / self.fps if self.fps else 0.0

    # --- getting the pictures and the sound out -------------------------

    def frame_bytes(self, number):
        """The demuxed bitstream of frame `number`, header and all.

        Opens the file per call rather than holding a handle: the panel
        decodes on a worker thread while an export decodes on the GUI
        thread, and a shared handle's file position belongs to whoever
        seeked last."""
        pieces = self.frames[number]
        out = bytearray()
        size = 0
        with open(self.path, "rb") as f:
            for place, index in enumerate(pieces):
                payload = self._payload(self._sector(f, index))
                if not place:
                    # The header says how much of the frame is really
                    # the frame; past that is whatever was in the sector
                    # when it was written.
                    size = struct.unpack_from("<I", payload, 0x0C)[0]
                out += payload[SECTOR_HEADER:]
        return bytes(out[:size]) if 0 < size <= len(out) else bytes(out)

    def frame(self, number):
        """Frame `number` as an (h, w, 3) uint8 RGB array."""
        return mdec.decode(self.frame_bytes(number), self.width, self.height)

    def wav(self):
        """The movie's soundtrack as WAV bytes, or None if it has none."""
        if not self.has_audio:
            return None
        with open(self.path, "rb") as f:
            samples, rate, speakers = xa.decode_channel(
                f, self.lba, self.audio_sectors)
        return xa.wav_bytes(samples, rate, speakers)

    def sectors_bytes(self):
        """The movie's own sectors, as they sit on the disc.

        A raw copy, so what comes out of a BIN is a 2352-byte STR that
        ffmpeg and the emulators read directly."""
        with open(self.path, "rb") as f:
            f.seek(self.lba * self.stride)
            return f.read(self.count * self.stride)


def _coding(byte):
    """(rate, channels) from an XA sector's coding byte."""
    channels, rate, _bits = xa.coding(byte)
    return rate, channels


