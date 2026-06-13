"""Shared test utilities for exfat-raw tests.

Provides sparse-image decompression, loop-device lifecycle,
and raw-device lifecycle via direct subprocess calls
(no dependency on mount-strategy code).
"""

import gzip
import os
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


KNOWN_IMG_SIZE = 8531738624  # apparent (uncompressed) size of sdcard.img

SYSTEM = platform.system()
_PART_RE = re.compile(r'disk\d+s\d+')


def decompress_sparse_image(gz_path: Path, dest_path: Path) -> Path:
    """Decompress *gz_path* → *dest_path* if not already present.
    Writes non-zero data blocks directly into a sparse file.
    """
    if dest_path.exists():
        return dest_path
    import fcntl
    lock_path = dest_path.with_suffix('.img.lock')
    with open(lock_path, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if not dest_path.exists():
            _write_sparse(gz_path, dest_path)
    return dest_path


def _write_sparse(gz_path: Path, img_path: Path):
    CHUNK = 1024 * 1024
    fd = os.open(img_path, os.O_CREAT | os.O_WRONLY)
    os.ftruncate(fd, KNOWN_IMG_SIZE)
    os.close(fd)
    zero = b'\x00' * CHUNK
    offset = 0
    with gzip.open(gz_path, 'rb') as src, open(img_path, 'rb+') as dst:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            if chunk != zero[:len(chunk)]:
                os.lseek(dst.fileno(), offset, os.SEEK_SET)
                dst.write(chunk)
            offset += len(chunk)


# ---------------------------------------------------------------------------
# Portable sparse-aware file copy
# ---------------------------------------------------------------------------

def copy_sparse_image(src: Path, dst: Path):
    """Copy *src* → *dst* preserving sparseness across platforms.

    On Linux uses ``cp --sparse=always``; on macOS uses plain ``cp``
    (APFS preserves holes natively).
    """
    if SYSTEM != 'Darwin':
        subprocess.run(['cp', '--sparse=always', str(src), str(dst)],
                       check=True, capture_output=True)
    else:
        subprocess.run(['cp', str(src), str(dst)],
                       check=True, capture_output=True)


# ---------------------------------------------------------------------------
# Linux  — losetup + mount
# ---------------------------------------------------------------------------

def _setup_loop_device_linux(img_path: str) -> tuple[str, str]:
    r = subprocess.run(['sudo', 'losetup', '-f', '--show', str(img_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"losetup failed: {r.stderr}")
    loop_dev = r.stdout.strip()
    mount_point = tempfile.mkdtemp(prefix='exfat_raw_')
    r = subprocess.run([
        'sudo', 'mount', '-t', 'exfat',
        '-o', f'uid={os.getuid()},gid={os.getgid()}',
        loop_dev, mount_point,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(['sudo', 'losetup', '-d', loop_dev], capture_output=True)
        shutil.rmtree(mount_point, ignore_errors=True)
        raise RuntimeError(f"mount failed: {r.stderr}")
    return loop_dev, mount_point


def _teardown_loop_device_linux(loop_dev: str, mount_point: str | None = None):
    if mount_point:
        subprocess.run(['sudo', 'umount', mount_point], capture_output=True)
        time.sleep(0.3)
        try:
            shutil.rmtree(mount_point, ignore_errors=True)
        except Exception:
            pass
    subprocess.run(['sudo', 'losetup', '-d', loop_dev], capture_output=True)


# ---------------------------------------------------------------------------
# macOS — hdiutil + mount
# ---------------------------------------------------------------------------

def _setup_loop_device_darwin(img_path: str) -> tuple[str, str]:
    # Try auto-mount first: attach without -nomount, parse plist output
    r = subprocess.run([
        'hdiutil', 'attach', '-plist', '-imagekey',
        'diskimage-class=CRawDiskImage', str(img_path),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"hdiutil attach failed: {r.stderr}")

    plist = plistlib.loads(r.stdout.encode())
    entities = plist.get('system-entities', [])

    for ent in entities:
        if ent.get('mount-point'):
            ent_dev = ent.get('dev-entry')
            if ent_dev:
                return ent_dev, ent['mount-point']

    # Auto-mount didn't work — detach, retry with -nomount + manual mount
    for ent in entities:
        dev = ent.get('dev-entry')
        if dev:
            subprocess.run(['hdiutil', 'detach', dev],
                           capture_output=True, timeout=10)

    r = subprocess.run([
        'hdiutil', 'attach', '-nomount', '-plist', '-imagekey',
        'diskimage-class=CRawDiskImage', str(img_path),
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"hdiutil attach (-nomount) failed: {r.stderr}")

    plist = plistlib.loads(r.stdout.encode())
    entities = plist.get('system-entities', [])

    mount_point = tempfile.mkdtemp(prefix='exfat_raw_')
    for ent in entities:
        dev = ent.get('dev-entry', '')
        if _PART_RE.search(dev):
            r = subprocess.run(
                ['sudo', 'mount', '-t', 'exfat', dev, mount_point],
                capture_output=True, text=True)
            if r.returncode == 0:
                return dev, mount_point

    # No partition mounted — try the whole-disk device
    for ent in entities:
        dev = ent.get('dev-entry', '')
        if dev and not _PART_RE.search(dev):
            r = subprocess.run(
                ['sudo', 'mount', '-t', 'exfat', dev, mount_point],
                capture_output=True, text=True)
            if r.returncode == 0:
                return dev, mount_point

    disk_dev = next((ent.get('dev-entry', '') for ent in entities if ent.get('dev-entry')), None)
    if disk_dev:
        subprocess.run(['hdiutil', 'detach', disk_dev], capture_output=True)
    shutil.rmtree(mount_point, ignore_errors=True)
    raise RuntimeError(f"mount failed for {entities}")


def _teardown_loop_device_darwin(loop_dev: str, mount_point: str | None = None):
    if mount_point:
        subprocess.run(['sudo', 'umount', mount_point], capture_output=True)
        time.sleep(0.3)
        try:
            shutil.rmtree(mount_point, ignore_errors=True)
        except Exception:
            pass
    subprocess.run(
        ['hdiutil', 'detach', loop_dev],
        capture_output=True, timeout=10)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def setup_loop_device(img_path: str) -> tuple[str, str]:
    """Set up a loop device and mount an exFAT image.
    Returns (device, mount_point).
    Raises RuntimeError on failure.
    """
    if SYSTEM == 'Darwin':
        return _setup_loop_device_darwin(img_path)
    return _setup_loop_device_linux(img_path)


def teardown_loop_device(loop_dev: str, mount_point: str | None = None):
    """Unmount and detach a loop device."""
    if SYSTEM == 'Darwin':
        _teardown_loop_device_darwin(loop_dev, mount_point)
    else:
        _teardown_loop_device_linux(loop_dev, mount_point)


# ---------------------------------------------------------------------------
# Raw (un-mounted) device attach/detach — for DDStrategy write tests
# ---------------------------------------------------------------------------

def _setup_raw_device_linux(img_path: str) -> str:
    r = subprocess.run(['sudo', 'losetup', '-f', '--show', img_path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"losetup failed: {r.stderr}")
    return r.stdout.strip()


def _teardown_raw_device_linux(dev: str):
    subprocess.run(['sudo', 'losetup', '-d', dev], capture_output=True)


def _setup_raw_device_darwin(img_path: str) -> str:
    r = subprocess.run([
        'hdiutil', 'attach', '-nomount', '-plist', '-imagekey',
        'diskimage-class=CRawDiskImage', img_path,
    ], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"hdiutil attach (-nomount) failed: {r.stderr}")
    plist = plistlib.loads(r.stdout.encode())
    entities = plist.get('system-entities', [])
    # Return the first whole-disk entry (no slice suffix)
    for ent in entities:
        dev = ent.get('dev-entry', '')
        if dev and not _PART_RE.search(dev):
            return dev
    if entities:
        return entities[0].get('dev-entry', '')
    raise RuntimeError("hdiutil attach returned no devices")


def _teardown_raw_device_darwin(dev: str):
    subprocess.run(['hdiutil', 'detach', dev], capture_output=True, timeout=10)


def setup_raw_device(img_path: str) -> str:
    """Attach *img_path* as a raw block device without mounting.
    Returns the device path (e.g. ``/dev/loop0`` or ``/dev/disk5``).
    Raises RuntimeError on failure.
    """
    if SYSTEM == 'Darwin':
        return _setup_raw_device_darwin(img_path)
    return _setup_raw_device_linux(img_path)


def teardown_raw_device(dev: str):
    """Detach a raw block device."""
    if SYSTEM == 'Darwin':
        _teardown_raw_device_darwin(dev)
    else:
        _teardown_raw_device_linux(dev)
