"""Pluggable I/O strategy classes for ExfatRawIO.

Each strategy implements a different mechanism for reading/writing raw
blocks on a device path. Strategies are tried in order until one succeeds.
"""

import os
import subprocess
import tempfile
from abc import ABC, abstractmethod


class IOStrategy(ABC):
    """Pluggable read/write strategy for raw block I/O."""

    @abstractmethod
    def read(self, device: str, offset: int, size: int) -> bytes | None:
        """Read *size* bytes from *device* at *offset*.

        Return bytes on success, or ``None`` to fall through to the
        next strategy in the chain.
        """

    @abstractmethod
    def write(self, device: str, offset: int, data: bytes) -> bool | None:
        """Write *data* to *device* at *offset*.

        Return ``True`` when handled, or ``None``/``False`` to fall
        through to the next strategy.
        """

    def clear_cache(self, device: str | None = None):
        """Drop cached state for *device* (or all if ``None``)."""


def _try_pread(path: str, offset: int, size: int) -> bytes | None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            return os.pread(fd, size, offset)
        finally:
            os.close(fd)
    except OSError:
        return None


def _try_pwrite(path: str, offset: int, data: bytes) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY)
        try:
            n = os.pwrite(fd, data, offset)
            assert n == len(data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


class DirectIOStrategy(IOStrategy):
    """Read/write directly on *device* via ``os.pread``/``os.pwrite``.

    Works for regular files (e.g. disk images) and any block device
    the process has permission to access.
    """

    def read(self, device: str, offset: int, size: int) -> bytes | None:
        return _try_pread(device, offset, size)

    def write(self, device: str, offset: int, data: bytes) -> bool:
        return _try_pwrite(device, offset, data)


class BackingFileStrategy(IOStrategy):
    """Resolve the loop-device backing file and operate on that.

    When the *device* is a loop device (e.g. ``/dev/loop0``) this
    reads/writes the underlying backing file directly, bypassing
    the kernel block layer entirely.
    """

    def __init__(self):
        self._backing_cache: dict[str, str | None] = {}

    def _resolve(self, device: str) -> str | None:
        if device not in self._backing_cache:
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
                        self._backing_cache[device] = r.stdout.strip() or None
                        break
                except Exception:
                    pass
            else:
                self._backing_cache[device] = None
        return self._backing_cache[device]

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


class DDStrategy(IOStrategy):
    """Fall back to ``sudo dd`` for read/write on physical block devices.

    Used when the process lacks direct access to the device and must
    elevate privileges via ``sudo``.
    """

    def read(self, device: str, offset: int, size: int) -> bytes | None:
        try:
            cmd = ['sudo', 'dd', f'if={device}', 'bs=1',
                   f'skip={offset}', f'count={size}']
            r = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
            if r.returncode != 0:
                return None
            return r.stdout
        except FileNotFoundError:
            return None

    def write(self, device: str, offset: int, data: bytes) -> bool:
        try:
            with tempfile.NamedTemporaryFile() as tf:
                tf.write(data)
                tf.flush()
                cmd = ['sudo', 'dd', f'if={tf.name}', f'of={device}',
                       'bs=1', f'seek={offset}', f'count={len(data)}',
                       'conv=fsync']
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            return False
