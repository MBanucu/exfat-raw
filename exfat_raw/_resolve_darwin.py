"""macOS-specific device/mount/fs resolution."""

import os
import plistlib
import subprocess

from exfat_raw._resolve import _df_output


def resolve_device(path: str) -> str | None:
    info = _df_output(path)
    if info:
        dev = info[0]
        backing = _resolve_backing_file_darwin(dev)
        if backing and os.path.isfile(backing):
            return backing
        return dev
    return None


def _resolve_backing_file_darwin(dev_entry: str) -> str | None:
    try:
        r = subprocess.run(
            ['hdiutil', 'info', '-plist'],
            capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        plist = plistlib.loads(r.stdout.encode())
        for img in plist.get('images', []):
            if not isinstance(img, dict):
                continue
            for ent in img.get('system-entities', []):
                if isinstance(ent, dict) and ent.get('dev-entry') == dev_entry:
                    return img.get('image-path')
    except Exception:
        pass
    return None


def resolve_mount_point(path: str) -> str | None:
    info = _df_output(path)
    return info[1] if info else None



