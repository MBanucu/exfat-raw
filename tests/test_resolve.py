"""Tests for filesystem/device resolution helpers.

Pure-functional — no mocking, uses real system calls only.
"""

import os
import tempfile
import unittest

from rawblock_io._resolve import _df_output


SYS_PATHS = ['/tmp', '/', os.getcwd()]


class TestDfOutput(unittest.TestCase):
    """_df_output must return (device, mount, fstype) for real paths."""

    def _check(self, path: str):
        result = _df_output(path)
        self.assertIsNotNone(result)
        device, mount_point, fstype = result
        self.assertIsInstance(device, str)
        self.assertGreater(len(device), 0)
        self.assertIsInstance(mount_point, str)
        self.assertGreater(len(mount_point), 0)
        # fstype may be empty on some platform/path combos
        # (e.g. macOS CI temp dirs), so only assert type.
        self.assertIsInstance(fstype, str)

    def test_returns_tuple_for_tmp(self):
        self._check('/tmp')

    def test_returns_tuple_for_root(self):
        self._check('/')

    def test_returns_tuple_for_cwd(self):
        self._check(os.getcwd())

    def test_returns_tuple_for_symlink(self):
        d = tempfile.mkdtemp(prefix='exfat_resolve_', dir='/tmp')
        try:
            target = os.path.join(d, 'target')
            link = os.path.join(d, 'mylink')
            with open(target, 'w') as f:
                f.write('x')
            os.symlink('target', link)
            self._check(link)
        finally:
            import shutil
            shutil.rmtree(d)

    def test_nonexistent_path_returns_none(self):
        self.assertIsNone(_df_output('/nonexistent_path_xyz123_test'))


if __name__ == '__main__':
    unittest.main()
