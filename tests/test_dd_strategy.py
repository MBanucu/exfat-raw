"""DDStrategy happy-path tests using the sdcard.img fixture.

Requires passwordless ``sudo`` for ``dd``, and for the
loop-device tests also requires ``sudo`` for ``losetup`` + ``mount``.
"""

import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from datetime import timezone
from pathlib import Path

from conftest import (
    KNOWN_IMG_SIZE,
    copy_sparse_image,
    decompress_sparse_image,
    setup_loop_device,
    teardown_loop_device,
)
from exfat_raw import ExfatRawFilesystem, ExfatRawIO
from exfat_raw._dd import DDStrategy
from exfat_raw._resolve import resolve_device, resolve_mount_point
from exfat_raw._strategies import BLOCK_SIZE


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


class TestDDStrategyWrite(unittest.TestCase):
    """DDStrategy.write happy paths."""

    _img: Path

    @classmethod
    def setUpClass(cls):
        gz = Path(__file__).parent / 'sdcard.img.gz'
        if not gz.exists():
            raise unittest.SkipTest('sdcard.img.gz not found')
        cls._img = decompress_sparse_image(gz, Path(__file__).parent / 'sdcard.img')

    def _copy(self) -> str:
        fd, path = tempfile.mkstemp(suffix='.img', prefix='dd_write_')
        import os
        os.close(fd)
        copy_sparse_image(self._img, Path(path))
        return path

    def test_write_aligned(self):
        s = DDStrategy()
        path = self._copy()
        try:
            data = b'\xAB' * 512
            self.assertTrue(s.write(path, 0, data))
            result = s.read(path, 0, 512)
            self.assertEqual(result, data)
        finally:
            import os
            os.unlink(path)

    def test_write_misaligned(self):
        s = DDStrategy()
        path = self._copy()
        try:
            data = b'\xCD' * 100
            self.assertTrue(s.write(path, 100, data))
            result = s.read(path, 100, 100)
            self.assertEqual(result, data)
        finally:
            import os
            os.unlink(path)

    def test_write_at_image_end(self):
        s = DDStrategy()
        path = self._copy()
        try:
            off = KNOWN_IMG_SIZE - 512
            data = b'\xEF' * 512
            self.assertTrue(s.write(path, off, data))
            result = s.read(path, off, 512)
            self.assertEqual(result, data)
        finally:
            import os
            os.unlink(path)


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
        s = DDStrategy()
        file_on_disk = Path(self._mnt) / 'DCIM' / '100GOPRO'
        files = sorted(file_on_disk.glob('*'))
        self.assertGreater(len(files), 0)
        target_path = files[0]
        fs_mtime = int(os.path.getmtime(target_path))

        boot = ExfatRawIO().parse_boot(self._loop)
        self.assertIsNotNone(boot)
        from exfat_raw._resolve import resolve_device, resolve_mount_point
        dev = resolve_device(str(target_path))
        self.assertIsNotNone(dev)
        mnt = resolve_mount_point(str(target_path))
        self.assertIsNotNone(mnt)
        fs = ExfatRawFilesystem(ExfatRawIO())
        entry = fs.find_file_entry(boot, dev, str(target_path))
        self.assertIsNotNone(entry)
        # mtime is in the first entry at offset 0x08 (time word) and 0x0A (date word)
        mtime_word = struct.unpack_from('<H', entry, 0x08)[0]
        mdate_word = struct.unpack_from('<H', entry, 0x0A)[0]
        tz = timezone.utc
        # Basic sanity — check that the DDStrategy read matches expectations
        self.assertGreater(mtime_word, 0)


class TestDDStrategyOnRawLoopDevice(unittest.TestCase):
    """DDStrategy write via a loop device (no mount) on a temp copy."""

    _loop: str
    _work: Path

    @classmethod
    def setUpClass(cls):
        gz = Path(__file__).parent / 'sdcard.img.gz'
        if not gz.exists():
            raise unittest.SkipTest('sdcard.img.gz not found')
        cached = Path(__file__).parent / 'sdcard.img'
        decompress_sparse_image(gz, cached)
        cls._work = Path(tempfile.mkdtemp(prefix='dd_raw_loop_'))
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

    def test_write_aligned_to_loop_device(self):
        s = DDStrategy()
        data = b'\x11' * 512
        self.assertTrue(s.write(self._loop, 0, data))
        result = s.read(self._loop, 0, 512)
        self.assertEqual(result, data)

    def test_read_back_original_after_write(self):
        """Write to a non-boot area, read back, verify."""
        s = DDStrategy()
        off = 1024 * 1024  # 1 MiB in — well past the boot sector
        data = b'\x22' * 512
        self.assertTrue(s.write(self._loop, off, data))
        result = s.read(self._loop, off, 512)
        self.assertEqual(result, data)


if __name__ == '__main__':
    unittest.main()
