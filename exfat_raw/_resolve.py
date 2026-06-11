"""Filesystem/device resolution helpers — extract a block device and mount
point from a file path, and detect the filesystem type.
"""

import os
import platform
import subprocess


SYSTEM = platform.system()


# ---------------------------------------------------------------------------
# Shared helper — portable ``df`` parsing
# ---------------------------------------------------------------------------

def _df_output(path: str) -> tuple[str, str, str] | None:
    """Return ``(device, mount_point, fstype)`` for *path* via ``df``."""
    try:
        if SYSTEM == 'Darwin':
            r = subprocess.run(
                ['df', '-T', str(path)],
                capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return None
            lines = r.stdout.strip().splitlines()
            if len(lines) < 2:
                return None
            parts = lines[1].split()
            if len(parts) < 3:
                return None
            return parts[0], parts[-1], parts[1]
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
# resolve_device
# ---------------------------------------------------------------------------

def _resolve_device_linux(path: str) -> str | None:
    st = os.stat(path)
    major = os.major(st.st_dev)
    minor = os.minor(st.st_dev)
    with open('/proc/partitions') as f:
        for line in f:
            parts = line.split()
            if len(parts) == 4 and parts[0].isdigit():
                if int(parts[0]) == major and int(parts[1]) == minor:
                    return f'/dev/{parts[3]}'
    try:
        link = os.readlink(f'/sys/dev/block/{major}:{minor}')
        return os.path.join('/dev', os.path.basename(link))
    except OSError:
        return None


def _resolve_device_darwin(path: str) -> str | None:
    info = _df_output(path)
    return info[0] if info else None


def resolve_device(path: str) -> str | None:
    """Resolve *path* to its block device (e.g. ``/dev/sda1``, ``/dev/disk2s1``)."""
    if SYSTEM == 'Darwin':
        return _resolve_device_darwin(path)
    return _resolve_device_linux(path)


# ---------------------------------------------------------------------------
# resolve_mount_point
# ---------------------------------------------------------------------------

def _resolve_mount_point_linux(path: str) -> str | None:
    r = subprocess.run(
        ['findmnt', '-n', '-o', 'TARGET', '--target', str(path)],
        capture_output=True, text=True, timeout=5)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return None


def _resolve_mount_point_darwin(path: str) -> str | None:
    info = _df_output(path)
    return info[1] if info else None


def resolve_mount_point(path: str) -> str | None:
    """Resolve *path* to its mount point."""
    if SYSTEM == 'Darwin':
        return _resolve_mount_point_darwin(path)
    return _resolve_mount_point_linux(path)


# ---------------------------------------------------------------------------
# detect_fs
# ---------------------------------------------------------------------------

def _detect_fs_linux(path: str) -> str | None:
    try:
        result = subprocess.run(
            ['df', '--output=fstype', str(path)],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if len(lines) >= 2:
                fs = lines[1].strip()
                if fs:
                    return 'exfat' if fs == 'fuseblk' else fs
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return _detect_fs_from_mounts(path)


def _detect_fs_darwin(path: str) -> str | None:
    info = _df_output(path)
    if info:
        return 'exfat' if info[2].lower() == 'fuseblk' else info[2].lower()
    try:
        r = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return None
        path_str = str(path)
        best = (None, 0)
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[1] == 'on':
                mp = parts[2]
                if path_str.startswith(mp) and len(mp) > best[1]:
                    fs_raw = parts[3].lstrip('(').split(',')[0]
                    best = (('exfat' if fs_raw == 'fuseblk' else fs_raw), len(mp))
        return best[0]
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def detect_fs(path: str) -> str | None:
    """Detect filesystem type for the mount containing *path*."""
    if SYSTEM == 'Darwin':
        return _detect_fs_darwin(path)
    return _detect_fs_linux(path)


# ---------------------------------------------------------------------------
# Fallback — Linux /proc/mounts
# ---------------------------------------------------------------------------

def _detect_fs_from_mounts(path: str) -> str | None:
    try:
        with open('/proc/mounts') as f:
            mounts = [(ln.split()[0], ln.split()[1], ln.split()[2])
                      for ln in f if len(ln.split()) >= 3]
    except OSError:
        return None
    path_str = str(path)
    best = (None, 0)
    for dev, mp, fs in mounts:
        if path_str.startswith(mp) and len(mp) > best[1]:
            best = ('exfat' if fs == 'fuseblk' else fs, len(mp))
    return best[0]
