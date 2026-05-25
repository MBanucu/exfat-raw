"""Shared test utilities for exfat-raw tests.

Provides sparse-image decompression and loop-device lifecycle
via direct subprocess calls (no dependency on mount-strategy code).
"""

import gzip
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


KNOWN_IMG_SIZE = 8531738624  # apparent (uncompressed) size of sdcard.img


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


def setup_loop_device(img_path: str) -> tuple[str, str]:
    """Set up a loop device and mount an exFAT image.
    Returns (loop_dev, mount_point).
    Raises RuntimeError on failure.
    """
    r = subprocess.run(['sudo', 'losetup', '-f', '--show', str(img_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"losetup failed: {r.stderr}")
    loop_dev = r.stdout.strip()

    mount_point = tempfile.mkdtemp(prefix='exfat_raw_')
    r = subprocess.run(['sudo', 'mount', '-t', 'exfat', loop_dev, mount_point],
                       capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(['sudo', 'losetup', '-d', loop_dev], capture_output=True)
        shutil.rmtree(mount_point, ignore_errors=True)
        raise RuntimeError(f"mount failed: {r.stderr}")
    return loop_dev, mount_point


def teardown_loop_device(loop_dev: str, mount_point: str | None = None):
    """Unmount and detach a loop device."""
    if mount_point:
        subprocess.run(['sudo', 'umount', mount_point], capture_output=True)
        time.sleep(0.3)
        try:
            shutil.rmtree(mount_point, ignore_errors=True)
        except Exception:
            pass
    subprocess.run(['sudo', 'losetup', '-d', loop_dev], capture_output=True)
