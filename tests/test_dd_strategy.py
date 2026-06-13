"""DDStrategy happy-path tests using the sdcard.img fixture.

Requires passwordless ``sudo`` for ``dd``.  No loop device or mount needed.
"""

import struct
import tempfile
import unittest
from pathlib import Path

from conftest import KNOWN_IMG_SIZE, copy_sparse_image, decompress_sparse_image
from exfat_raw._dd import DDStrategy
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


if __name__ == '__main__':
    unittest.main()
