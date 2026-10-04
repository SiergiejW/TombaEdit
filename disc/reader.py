"""Read-only ISO9660 reader for 2048-byte ISO and PSX raw BIN/CUE tracks."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import struct


class FormatError(ValueError):
    pass


@dataclass
class DiscEntry:
    path: str
    lba: int
    size: int
    directory: bool = False
    children: list = field(default_factory=list)


def cue_track(path):
    current_file = None
    track = None
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        match = re.match(r'\s*FILE\s+(?:"([^"]+)"|(\S+))\s+BINARY', line, re.I)
        if match:
            current_file = path.parent / (match[1] or match[2])
            track = None
        match = re.match(r'\s*TRACK\s+\d+\s+(\S+)', line, re.I)
        if match:
            track = match[1].upper()
        match = re.match(r'\s*INDEX\s+01\s+(\d+):(\d+):(\d+)', line, re.I)
        if match and track and track != "AUDIO":
            if track not in ("MODE1/2048", "MODE1/2352", "MODE2/2352"):
                raise FormatError(f"Unsupported CUE data track: {track}")
            if current_file is None:
                raise FormatError("CUE track has no FILE record")
            frames = (int(match[1]) * 60 + int(match[2])) * 75 + int(match[3])
            return current_file, frames, track
    raise FormatError("No supported data track with INDEX 01 in CUE")


class Disc:
    def __init__(self, path):
        self.source = Path(path).resolve()
        self.path = self.source
        self.start = 0
        hint = None
        if self.source.suffix.lower() == ".cue":
            self.path, self.start, hint = cue_track(self.source)
        self.byte_size = self.path.stat().st_size
        candidates = [(2048, 0), (2352, 24), (2352, 16)]
        if hint:
            candidates = [{"MODE1/2048": (2048, 0), "MODE1/2352": (2352, 16),
                           "MODE2/2352": (2352, 24)}[hint]]
        with self.path.open("rb") as f:
            for stride, offset in candidates:
                f.seek((self.start + 16) * stride + offset)
                pvd = f.read(2048)
                if pvd[:7] == b"\x01CD001\x01":
                    self.stride, self.payload_offset = stride, offset
                    break
            else:
                raise FormatError("No ISO9660 primary volume descriptor. Open the data-track BIN or its CUE.")
        if struct.unpack_from("<H", pvd, 128)[0] != 2048:
            raise FormatError("Unsupported ISO logical block size")
        self.volume = pvd[40:72].decode("ascii", "replace").strip()
        self.root = self._record(pvd[156:190], "")
        self.entries = {}
        self._walk(self.root, set(), 0)

    @property
    def files(self):
        return [e for e in self.entries.values() if not e.directory]

    def read_at(self, lba, size, offset=0):
        if min(lba, size, offset) < 0:
            raise FormatError("Negative disc range")
        lba += offset // 2048
        skip = offset % 2048
        blocks = (skip + size + 2047) // 2048
        start = (self.start + lba) * self.stride
        if start + blocks * self.stride > self.byte_size:
            raise FormatError(f"Disc extent outside image: LBA {lba}, {size} bytes")
        with self.path.open("rb") as f:
            f.seek(start)
            raw = f.read(blocks * self.stride)
        if self.stride == 2048:
            return raw[skip:skip + size]
        data = b"".join(raw[p + self.payload_offset:p + self.payload_offset + 2048]
                        for p in range(0, len(raw), self.stride))
        return data[skip:skip + size]

    def read(self, entry, limit=None, offset=0):
        if isinstance(entry, str):
            entry = self.entries[entry.upper()]
        size = max(0, entry.size - offset)
        return self.read_at(entry.lba, min(size, limit) if limit is not None else size, offset)

    @staticmethod
    def _record(record, path):
        if len(record) < 34:
            raise FormatError("Truncated ISO directory record")
        if record[26] or record[27] or record[25] & 0x80:
            raise FormatError("Interleaved or multi-extent ISO entries are unsupported")
        return DiscEntry(path, struct.unpack_from("<I", record, 2)[0] + record[1],
                         struct.unpack_from("<I", record, 10)[0], bool(record[25] & 2))

    def _walk(self, folder, visited, depth):
        if depth > 32 or folder.lba in visited:
            raise FormatError("Cyclic or excessively deep ISO directory")
        if folder.size > 16 * 1024 * 1024:
            raise FormatError("Unreasonably large ISO directory")
        visited.add(folder.lba)
        data = self.read(folder)
        pos = 0
        while pos < len(data):
            size = data[pos]
            if not size:
                pos = (pos // 2048 + 1) * 2048
                continue
            if size < 34 or pos + size > len(data):
                raise FormatError("Invalid ISO directory record length")
            record = data[pos:pos + size]
            pos += size
            name = record[33:33 + record[32]]
            if name in (b"\0", b"\1"):
                continue
            name = name.decode("ascii", "replace").split(";")[0]
            if name in (".", "..") or "/" in name or "\\" in name:
                raise FormatError("Invalid ISO filename")
            path = f"{folder.path}/{name}".lstrip("/")
            entry = self._record(record, path)
            self.entries[path.upper()] = entry
            folder.children.append(entry)
            if entry.directory:
                self._walk(entry, visited, depth + 1)
        visited.remove(folder.lba)
