"""DDStrategy happy-path tests using the sdcard.img fixture.

Requires passwordless ``sudo`` for ``dd``, and for the
loop-device tests also requires ``sudo`` for ``losetup`` + ``mount``
(Linux) or ``hdiutil`` (macOS).
"""

import platform
import re
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from conftest import (
    copy_sparse_image,
    decompress_sparse_image,
    setup_loop_device,
    setup_raw_device,
    teardown_loop_device,
    teardown_raw_device,
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


class TestDDStrategyWriteLoopDevice(unittest.TestCase):
    """DDStrategy write via loop device (no mount)."""

    _dev: str
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
        cls._dev = setup_raw_device(str(img))
        cls.addClassCleanup(cls._teardown)

    @classmethod
    def _teardown(cls):
        teardown_raw_device(cls._dev)
        shutil.rmtree(cls._work, ignore_errors=True)

    def test_write_aligned(self):
        s = DDStrategy()
        data = b'\x11' * 512
        self.assertTrue(s.write(self._dev, 0, data))
        result = s.read(self._dev, 0, 512)
        self.assertEqual(result, data)

    def test_write_misaligned(self):
        """Misaligned write exercises the read-modify-write path."""
        s = DDStrategy()
        data = b'\x22' * 100
        self.assertTrue(s.write(self._dev, 100, data))
        result = s.read(self._dev, 100, 100)
        self.assertEqual(result, data)

    def test_write_non_boot_area(self):
        """Write to 1 MiB — well past the boot sector."""
        s = DDStrategy()
        off = 1024 * 1024
        data = b'\x33' * 512
        self.assertTrue(s.write(self._dev, off, data))
        result = s.read(self._dev, off, 512)
        self.assertEqual(result, data)


class TestDDStrategyOnLoopDevice(unittest.TestCase):
    """DDStrategy read/write via a mounted loop device (real block device path).

    On macOS the mounted partition device cannot be read via ``sudo dd``
    (exFAT driver blocks direct I/O), so ``test_read_boot_sector`` uses
    a raw (un-mounted) device instead.  The filesystem-content test uses
    the mounted device via ``ExfatRawIO`` (which succeeds via ``os.pread``).
    """

    _loop: str
    _raw_dev: str
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
        # On macOS the mounted partition device can't be read via sudo dd
        # (exFAT driver blocks direct I/O).  Derive the parent whole-disk
        # device for raw-block tests.  On Linux the loop device itself is
        # already a whole-disk device.
        if SYSTEM == 'Darwin':
            cls._raw_dev = re.sub(r's\d+$', '', cls._loop)
        else:
            cls._raw_dev = cls._loop
        cls.addClassCleanup(teardown_loop_device, cls._loop, cls._mnt)
        cls.addClassCleanup(shutil.rmtree, cls._work, ignore_errors=True)

    def test_read_boot_sector_from_loop_device(self):
        s = DDStrategy()
        data = s.read(self._raw_dev, 0, 512)
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 512)
        sig = struct.unpack_from('<H', data, 510)[0]
        self.assertEqual(sig, 0xAA55)

    def test_read_file_content_via_loop_device(self):
        from datetime import timezone

        from exfat_raw import ExfatRawFilesystem, ExfatRawIO
        from exfat_raw._resolve import resolve_device, resolve_mount_point

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
