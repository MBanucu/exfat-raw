"""Backing-file strategy — reads/writes via the loop-device backing file."""

import os
import platform
import plistlib
import subprocess

from exfat_raw._strategies import IOStrategy, _try_pread, _try_pwrite


class BackingFileStrategy(IOStrategy):
    """Resolve the loop-device backing file and operate on that.

    When the *device* is a loop device (e.g. ``/dev/loop0``) this
    reads/writes the underlying backing file directly, bypassing
    the kernel block layer entirely.

    On macOS resolves via ``hdiutil info -plist`` instead.
    """

    def __init__(self):
        self._backing_cache: dict[str, str | None] = {}
        self._is_darwin = platform.system() == 'Darwin'

    def _resolve(self, device: str) -> str | None:
        if device not in self._backing_cache:
            if self._is_darwin:
                self._backing_cache[device] = self._resolve_darwin(device)
            else:
                self._backing_cache[device] = self._resolve_linux(device)
        return self._backing_cache[device]

    def _resolve_linux(self, device: str) -> str | None:
        dev_name = device.lstrip('/dev/')
        for cmd in (
            ['cat', f'/sys/block/{dev_name}/loop/backing_file'],
            ['sudo', 'cat', f'/sys/block/{dev_name}/loop/backing_file'],
            ['losetup', '-n', '-O', 'BACK-FILE', device],
            ['sudo', 'losetup', '-n', '-O', 'BACK-FILE', device],
        ):
            try:
                r = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=5)
                if r.returncode == 0:
                    return r.stdout.strip() or None
            except Exception:
                pass
        return None

    def _resolve_darwin(self, device: str) -> str | None:
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
                    if isinstance(ent, dict) and ent.get('dev-entry') == device:
                        return img.get('image-path')
        except Exception:
            pass
        return None

    def read(self, device: str, offset: int, size: int) -> bytes | None:
        backing = self._resolve(device)
        if backing and os.access(backing, os.R_OK):
            return _try_pread(backing, offset, size)
        return None

    def write(self, device: str, offset: int, data: bytes) -> bool:
        backing = self._resolve(device)
        if backing and os.access(backing, os.W_OK):
            return _try_pwrite(backing, offset, data)
        return False

    def clear_cache(self, device: str | None = None):
        if device is None:
            self._backing_cache.clear()
        else:
            self._backing_cache.pop(device, None)
