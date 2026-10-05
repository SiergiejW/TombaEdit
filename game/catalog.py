"""Resolve executable File Link Arrays against the actual ISO directory."""
from dataclasses import dataclass
import struct
import hashlib
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
    stride: int = 8

    @classmethod
    def discover(cls, disc):
        by_lba = {e.lba: e for e in disc.files}
        anchor = disc.entries.get("SYS/LDSYS.BIN") or disc.entries.get('SYSTEM/A00000.GAM')
        executables = [e for e in disc.files if e.path.startswith(("SCUS_", "SCES_", "SLPS_", 'SLPM_'))
                       or e.path.endswith(".EXE")]
        best = None
        for entry in executables:
            if entry.size > 8 * 1024 * 1024:
                continue
            data = disc.read(entry)
            if not data.startswith(b"PS-X EXE"):
                continue
            digest = hashlib.sha1(data).hexdigest()
            if digest == '1e69d1414dcca09fe360fe69337fc8e62968fda7':
                # This preview reserves 24 link indices between its system
                # and area files. The executable's embedded load records use
                # the original indices, including these empty slots.
                links, matched = {}, 0
                start = 0x66DF4
                for index in range(1055):
                    try:
                        lba, size = link_record(data, start + index * 8)
                    except (ValueError, struct.error):
                        continue
                    actual = by_lba.get(lba)
                    if actual is not None:
                        links[index] = DiscEntry(actual.path, lba, size)
                        matched += 1
                if matched > 1000:
                    return cls(entry.path, start, links, matched)
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
              for stride in ((8,) if anchor and anchor.path == 'SYS/LDSYS.BIN' else (8, 24)):
                links, matched = {}, 0
                holes = 0
                for pos in range(start, len(data) - 7, stride):
                    try:
                        lba, size = link_record(data, pos)
                    except (ValueError, struct.error):
                        if data[pos:pos + 8] == bytes(8) and holes < 64:
                            holes += 1
                            continue
                        break
                    holes = 0
                    if lba < 0 or (lba + disc.start) * disc.stride >= disc.byte_size:
                        break
                    actual = by_lba.get(lba)
                    index = (pos - start) // stride
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
                        best = cls(entry.path, start, links, matched, stride)
            # The Pure Pure sampler stores 64-byte records with ISO names;
            # CdSearchFile fills their extent fields at runtime.
            needle = b'\\TOMBA\\A00000.GAM;1'
            start = data.find(needle)
            if start >= 0:
                links = {}
                for index, pos in enumerate(range(start, len(data), 64)):
                    name = data[pos:pos + 46].split(b'\0')[0].decode('ascii', 'replace').split(';')[0].replace('\\', '/').lstrip('/')
                    actual = disc.entries.get(name.upper())
                    if actual is None:
                        break
                    links[index] = actual
                if len(links) >= 8 and (best is None or len(links) > best.matched):
                    best = cls(entry.path, start, links, len(links), 64)
        if best is None:
            raise FormatError("No verified file-link table found. Disc folders remain available; "
                              "this build's LDAR layout is not supported yet.")
        return best
