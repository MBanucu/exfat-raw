"""Shared test utilities for exfat-raw tests.

Provides sparse-image decompression and loop-device lifecycle
via direct subprocess calls (no dependency on mount-strategy code).
"""

import gzip
import os
import platform
import plistlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


KNOWN_IMG_SIZE = 8531738624  # apparent (uncompressed) size of sdcard.img

SYSTEM = platform.system()


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

    mount_dev = mount_point = None
    for ent in entities:
        if ent.get('mount-point'):
            mount_dev = ent['dev-entry']
            mount_point = ent['mount-point']
            break

    if mount_dev and mount_point:
        return mount_dev, mount_point

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

    disk_dev = None
    part_devs = []
    for ent in entities:
        dev = ent.get('dev-entry', '')
        if dev and not dev[-1].isdigit():
            disk_dev = dev
        else:
            part_devs.append(dev)

    if not disk_dev and part_devs:
        disk_dev = part_devs[0]
    elif not disk_dev and entities:
        disk_dev = entities[0].get('dev-entry', '')

    mount_point = tempfile.mkdtemp(prefix='exfat_raw_')
    candidates = part_devs + ([disk_dev] if disk_dev else [])
    for dev in candidates:
        if not dev:
            continue
        mount_cmd = ['sudo', 'mount', '-t', 'exfat']
        if SYSTEM != 'Darwin':
            mount_cmd += ['-o', f'uid={os.getuid()},gid={os.getgid()}']
        mount_cmd += [dev, mount_point]
        r = subprocess.run(mount_cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return dev, mount_point

    if disk_dev:
        subprocess.run(['hdiutil', 'detach', disk_dev], capture_output=True)
    shutil.rmtree(mount_point, ignore_errors=True)
    raise RuntimeError(f"mount failed for disk={disk_dev} parts={part_devs}")


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
