"""DDStrategy happy-path tests using the sdcard.img fixture.

Requires passwordless ``sudo`` for ``dd``, and for the
loop-device tests also requires ``sudo`` for ``losetup`` + ``mount``.
"""

import os
import platform
import shutil
import struct
import subprocess
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from conftest import (
    copy_sparse_image,
    decompress_sparse_image,
    setup_loop_device,
    teardown_loop_device,
)
from exfat_raw._dd import DDStrategy
from exfat_raw._strategies import BLOCK_SIZE

SYSTEM = platform.system()


class TestDDStrategyRead(unittest.TestCase):
    """DDStrategy.read happy paths."""

    _img: Path

    @classmethod
    def setUpClass(cls):
        gz = Path(__file__).parent / 'sdcard.img.gz'
        if not gz.exists():
            raise unittest.SkipTest('sdcard.img.gz not found')
        cls._img = decompress_sparse_image(gz, Path(__file__).parent / 'sdcard.img')

    def test_read_boot_sector(self):
        s = DDStrategy()
        data = s.read(str(self._img), 0, 512)
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 512)
        sig = struct.unpack_from('<H', data, 510)[0]
        self.assertEqual(sig, 0xAA55)

    def test_read_partial_at_offset(self):
        s = DDStrategy()
        data = s.read(str(self._img), 100, 200)
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 200)

    def test_read_full_image(self):
        s = DDStrategy()
        chunk = s.read(str(self._img), 0, BLOCK_SIZE * 2)
        self.assertIsNotNone(chunk)
        self.assertEqual(len(chunk), BLOCK_SIZE * 2)


@unittest.skipIf(SYSTEM == 'Darwin', 'loop-device DDStrategy tests require Linux')
class TestDDStrategyWriteLoopDevice(unittest.TestCase):
    """DDStrategy write via loop device (no mount)."""

    _loop: str
    _work: Path

    @classmethod
    def setUpClass(cls):
        gz = Path(__file__).parent / 'sdcard.img.gz'
        if not gz.exists():
            raise unittest.SkipTest('sdcard.img.gz not found')
        cached = Path(__file__).parent / 'sdcard.img'
        decompress_sparse_image(gz, cached)
        cls._work = Path(tempfile.mkdtemp(prefix='dd_write_loop_'))
        img = cls._work / 'sdcard.img'
        copy_sparse_image(cached, img)
        r = subprocess.run(
            ['sudo', 'losetup', '-f', '--show', str(img)],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"losetup failed: {r.stderr}")
        cls._loop = r.stdout.strip()
        cls.addClassCleanup(cls._teardown)

    @classmethod
    def _teardown(cls):
        subprocess.run(['sudo', 'losetup', '-d', cls._loop], capture_output=True)
        shutil.rmtree(cls._work, ignore_errors=True)

    def test_write_aligned_to_loop(self):
        s = DDStrategy()
        data = b'\x11' * 512
        self.assertTrue(s.write(self._loop, 0, data))
        result = s.read(self._loop, 0, 512)
        self.assertEqual(result, data)

    def test_write_misaligned_to_loop(self):
        """Misaligned write exercises the read-modify-write path."""
        s = DDStrategy()
        data = b'\x22' * 100
        self.assertTrue(s.write(self._loop, 100, data))
        result = s.read(self._loop, 100, 100)
        self.assertEqual(result, data)

    def test_write_non_boot_area(self):
        """Write to 1 MiB — well past the boot sector."""
        s = DDStrategy()
        off = 1024 * 1024
        data = b'\x33' * 512
        self.assertTrue(s.write(self._loop, off, data))
        result = s.read(self._loop, off, 512)
        self.assertEqual(result, data)


@unittest.skipIf(SYSTEM == 'Darwin', 'loop-device DDStrategy tests require Linux')
class TestDDStrategyOnLoopDevice(unittest.TestCase):
    """DDStrategy read/write via a mounted loop device (real block device path)."""

    _loop: str
    _mnt: str
    _img: Path

    @classmethod
    def setUpClass(cls):
        gz = Path(__file__).parent / 'sdcard.img.gz'
        if not gz.exists():
            raise unittest.SkipTest('sdcard.img.gz not found')
        cached = Path(__file__).parent / 'sdcard.img'
        decompress_sparse_image(gz, cached)
        cls._work = Path(tempfile.mkdtemp(prefix='dd_loop_'))
        cls._img = cls._work / 'sdcard.img'
        copy_sparse_image(cached, cls._img)
        cls._loop, cls._mnt = setup_loop_device(str(cls._img))
        cls.addClassCleanup(teardown_loop_device, cls._loop, cls._mnt)
        cls.addClassCleanup(shutil.rmtree, cls._work, ignore_errors=True)

    def test_read_boot_sector_from_loop_device(self):
        s = DDStrategy()
        data = s.read(self._loop, 0, 512)
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 512)
        sig = struct.unpack_from('<H', data, 510)[0]
        self.assertEqual(sig, 0xAA55)

    def test_read_file_content_via_loop_device(self):
        from datetime import timezone

        from exfat_raw import ExfatRawFilesystem, ExfatRawIO
        from exfat_raw._resolve import resolve_device, resolve_mount_point

        s = DDStrategy()
        file_on_disk = Path(self._mnt) / 'DCIM' / '100GOPRO'
        files = sorted(file_on_disk.glob('*'))
        self.assertGreater(len(files), 0)
        target_path = files[0]

        boot = ExfatRawIO().parse_boot(self._loop)
        self.assertIsNotNone(boot)
        dev = resolve_device(str(target_path))
        self.assertIsNotNone(dev)
        mnt = resolve_mount_point(str(target_path))
        self.assertIsNotNone(mnt)
        fs = ExfatRawFilesystem(ExfatRawIO())
        entry = fs.find_file_entry(boot, dev, str(target_path))
        self.assertIsNotNone(entry)
        mtime_word = struct.unpack_from('<H', entry, 0x08)[0]
        self.assertGreater(mtime_word, 0)


if __name__ == '__main__':
    unittest.main()
