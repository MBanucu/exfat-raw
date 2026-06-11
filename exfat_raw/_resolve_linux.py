"""Linux-specific device/mount/fs resolution."""

import os
import subprocess

from exfat_raw._resolve import _df_output


def resolve_device(path: str) -> str | None:
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


def resolve_mount_point(path: str) -> str | None:
    r = subprocess.run(
        ['findmnt', '-n', '-o', 'TARGET', '--target', str(path)],
        capture_output=True, text=True, timeout=5)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    return None


def detect_fs(path: str) -> str | None:
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
