"""Platform-specific helpers to resolve a block device and mount point from a
file path.

Dispatches to an OS-specific submodule (``_resolve_linux`` or
``_resolve_darwin``) at module-load time and re-exports the public API.
"""

import importlib
import platform
import subprocess


SYSTEM = platform.system()


def _df_output(path: str) -> tuple[str, str, str] | None:
    """Return ``(device, mount_point, fstype)`` for *path* via ``df``."""
    try:
        if SYSTEM == 'Darwin':
            r = subprocess.run(
                ['df', str(path)],
                capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return None
            lines = r.stdout.strip().splitlines()
            if len(lines) < 2:
                return None
            parts = lines[1].split()
            if len(parts) < 3:
                return None
            device = parts[0]
            mount_point = parts[-1]
            stat_r = subprocess.run(
                ['stat', '-f', '%T', str(path)],
                capture_output=True, text=True, timeout=5)
            fstype = stat_r.stdout.strip() if stat_r.returncode == 0 else ''
            return device, mount_point, fstype
        else:
            r = subprocess.run(
                ['df', '--output=fstype,target,source', str(path)],
                capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return None
            lines = r.stdout.strip().splitlines()
            if len(lines) < 2:
                return None
            cols = lines[1].split(None, 2)
            if len(cols) < 3:
                return None
            return cols[2], cols[1], cols[0]
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


# ---------------------------------------------------------------------------
# Platform dispatch — import the OS-specific submodule at load time and
# alias its public API.  Each submodule must expose ``resolve_device``
# and ``resolve_mount_point``.
# ---------------------------------------------------------------------------

_mod = importlib.import_module(f'._resolve_{SYSTEM.lower()}', __package__)
resolve_device = _mod.resolve_device
resolve_mount_point = _mod.resolve_mount_point
