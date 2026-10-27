"""Optional disc-cache warm-up in a separate, low-priority process."""
from pathlib import Path


def warm_disc(path, cache_folder):
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
    sections = [(name, group.index) for name, groups in project.ldars.items()
                if area_of(name) >= 0 for group in groups[1:] if group.assets]
    for tracer in (sprite_pages, sprite_routines):
        for name, index in sections:
            try:
                tracer(project, name, index)
            except Exception:
                # A warm-up failure must never affect ordinary on-demand loading.
                continue
