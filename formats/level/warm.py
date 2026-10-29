"""Optional disc-cache warm-up in a separate, low-priority process."""
from pathlib import Path


def warm_disc(path, cache_folder, shard=0, shards=1):
    """Work out this process's share of the sections. Several of these run
    side by side, each in its own process; the sections are dealt out by size,
    the biggest first to whichever process has the least so far, so that they
    finish together."""
    import sys
    if sys.platform == 'win32':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x40)  # IDLE_PRIORITY_CLASS
    from formats.archive.ldar import Project
    from formats.level.scene import sprite_pages, sprite_routines, area_of
    project = Project(path)
    project._analysis_folder = Path(cache_folder) if cache_folder else None
    sections = [(name, group.index, sum(a.size for a in group.assets)) for name, groups in project.ldars.items()
                if area_of(name) >= 0 for group in groups[1:] if group.assets]
    loads = [0] * shards
    mine = []
    for name, index, size in sorted(sections, key=lambda s: (-s[2], s[0], s[1])):
        target = loads.index(min(loads))
        loads[target] += size
        if target == shard:
            mine.append((name, index))
    sections = mine
    for tracer in (sprite_pages, sprite_routines):
        for name, index in sections:
            try:
                tracer(project, name, index)
            except Exception:
                # A warm-up failure must never affect ordinary on-demand loading.
                continue
