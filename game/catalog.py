"""Resolve executable File Link Arrays against the actual ISO directory."""
from dataclasses import dataclass
import struct
from disc.reader import DiscEntry, FormatError


def bcd(value):
    if value & 15 > 9 or value >> 4 > 9:
        raise ValueError("Invalid BCD")
    return (value >> 4) * 10 + (value & 15)


def link_record(data, offset):
    mm, ss, ff, _, size = struct.unpack_from("<BBBBI", data, offset)
    m, s, f = bcd(mm), bcd(ss), bcd(ff)
    if s >= 60 or f >= 75 or not size:
        raise ValueError("Invalid file link")
    return (m * 60 + s) * 75 + f - 150, size


@dataclass
class Catalog:
    executable: str
    offset: int
    links: dict
    matched: int

    @classmethod
    def discover(cls, disc):
        by_lba = {e.lba: e for e in disc.files}
        anchor = disc.entries.get("SYS/LDSYS.BIN")
        executables = [e for e in disc.files if e.path.startswith(("SCUS_", "SCES_", "SLPS_"))
                       or e.path.endswith(".EXE")]
        best = None
        for entry in executables:
            if entry.size > 8 * 1024 * 1024:
                continue
            data = disc.read(entry)
            if not data.startswith(b"PS-X EXE"):
                continue
            # Search for the actual LDSYS extent/size. Never assume a region's offset.
            candidates = []
            for pos in range(0x800, len(data) - 8, 4):
                try:
                    lba, size = link_record(data, pos)
                except (ValueError, struct.error):
                    continue
                if anchor and (lba, size) == (anchor.lba, anchor.size):
                    candidates.append(pos)
            for start in candidates:
                links, matched = {}, 0
                for pos in range(start, len(data) - 7, 8):
                    try:
                        lba, size = link_record(data, pos)
                    except (ValueError, struct.error):
                        break
                    if lba < 0 or (lba + disc.start) * disc.stride >= disc.byte_size:
                        break
                    actual = by_lba.get(lba)
                    index = (pos - start) // 8
                    if actual is not None:
                        links[index] = DiscEntry(actual.path, lba, size)
                        matched += 1
                    else:
                        links[index] = DiscEntry(f"[unlisted file {index:04X}]", lba, size)
                # Unrelated executable data can resemble valid MSF records.
                # Do not retain an unverified tail beyond the last ISO match.
                while links and links[max(links)].path.startswith("[unlisted"):
                    links.pop(max(links))
                if matched >= 8 and (best is None or matched > best.matched):
                    best = cls(entry.path, start, links, matched)
        if best is None:
            raise FormatError("No verified file-link table found. Disc folders remain available; "
                              "this build's LDAR layout is not supported yet.")
        return best
