"""Tests for filesystem/device resolution helpers.

Pure-functional — no mocking, uses real system calls only.
"""

import os
import shutil
import tempfile
import unittest

from exfat_raw._resolve import _df_output


class TestDfOutput(unittest.TestCase):
    """_df_output must return correct (device, mount, fstype) for real paths."""

    def test_returns_tuple_for_tmp(self):
        result = _df_output('/tmp')
        self.assertIsNotNone(result)
        device, mount_point, fstype = result
        self.assertIsInstance(device, str)
        self.assertGreater(len(device), 0)
        self.assertIsInstance(mount_point, str)
        self.assertGreater(len(mount_point), 0)
        self.assertIsInstance(fstype, str)
        self.assertGreater(len(fstype), 0)

    def test_returns_tuple_for_root(self):
        result = _df_output('/')
        self.assertIsNotNone(result)
        device, mount_point, fstype = result
        self.assertIsInstance(device, str)
        self.assertGreater(len(device), 0)
        self.assertIsInstance(mount_point, str)
        self.assertGreater(len(mount_point), 0)
        self.assertIsInstance(fstype, str)
        self.assertGreater(len(fstype), 0)

    def test_returns_tuple_for_cwd(self):
        result = _df_output(os.getcwd())
        self.assertIsNotNone(result)
        device, mount_point, fstype = result
        self.assertIsInstance(device, str)
        self.assertGreater(len(device), 0)
        self.assertIsInstance(mount_point, str)
        self.assertGreater(len(mount_point), 0)
        self.assertIsInstance(fstype, str)
        self.assertGreater(len(fstype), 0)

    def test_returns_tuple_for_file_in_temp_dir(self):
        d = tempfile.mkdtemp(prefix='exfat_resolve_')
        try:
            fpath = os.path.join(d, 'somefile')
            with open(fpath, 'w') as f:
                f.write('x')
            result = _df_output(fpath)
            self.assertIsNotNone(result)
            device, mount_point, fstype = result
            self.assertIsInstance(device, str)
            self.assertGreater(len(device), 0)
            self.assertIsInstance(mount_point, str)
            self.assertGreater(len(mount_point), 0)
            self.assertIsInstance(fstype, str)
            self.assertGreater(len(fstype), 0)
        finally:
            shutil.rmtree(d)

    def test_nonexistent_path_returns_none(self):
        result = _df_output('/nonexistent_path_xyz123_test')
        self.assertIsNone(result)

    def test_returns_tuple_for_symlink(self):
        d = tempfile.mkdtemp(prefix='exfat_resolve_')
        try:
            target = os.path.join(d, 'target')
            link = os.path.join(d, 'mylink')
            with open(target, 'w') as f:
                f.write('x')
            os.symlink('target', link)
            result = _df_output(link)
            self.assertIsNotNone(result)
            device, mount_point, fstype = result
            self.assertIsInstance(device, str)
            self.assertGreater(len(device), 0)
            self.assertIsInstance(mount_point, str)
            self.assertGreater(len(mount_point), 0)
            self.assertIsInstance(fstype, str)
            self.assertGreater(len(fstype), 0)
        finally:
            shutil.rmtree(d)


if __name__ == '__main__':
    unittest.main()
