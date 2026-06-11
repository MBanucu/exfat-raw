"""Test fix_exfat_raw parameter combinations: update_cache, btime_dt, dry_run.

Requires loop device setup (sudo + FUSE).  Uses the sdcard.img fixture.
"""

import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from conftest import (
    copy_sparse_image,
    decompress_sparse_image,
    setup_loop_device,
    teardown_loop_device,
)


def _ops():
    from exfat_raw import ExfatRawIO, ExfatRawFilesystem, ExfatRawOps
    io = ExfatRawIO()
    return ExfatRawOps(io, ExfatRawFilesystem(io))


class TestFixExfatRawParams(unittest.TestCase):
    """Exhaustive parameter tests for ExfatRawOps.fix_exfat_raw."""

    _target: Path
    _files: list[Path]

    @classmethod
    def setUpClass(cls):
        gz = Path(__file__).parent / 'sdcard.img.gz'
        if not gz.exists():
            raise unittest.SkipTest('sdcard.img.gz not found')
        cached = Path(__file__).parent / 'sdcard.img'
        decompress_sparse_image(gz, cached)
        cls._work = Path(tempfile.mkdtemp(prefix='exfat_params_'))
        cls._img = cls._work / 'sdcard.img'
        copy_sparse_image(cached, cls._img)
        cls._loop, cls._mnt = setup_loop_device(str(cls._img))
        cls.addClassCleanup(teardown_loop_device, cls._loop, cls._mnt)
        cls.addClassCleanup(shutil.rmtree, cls._work, ignore_errors=True)
        cls._target = Path(cls._mnt) / 'DCIM' / '100GOPRO'
        if not cls._target.exists():
            raise unittest.SkipTest('100GOPRO not found')
        cls._files = sorted(cls._target.glob('*'))

    def test_update_cache_false_writes_raw_block(self):
        """update_cache=False must still write the correct data to the raw block."""
        ops = _ops()
        f = self._files[0]
        ts = int(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)

        ops.fix_exfat_raw(str(f), dt, dry_run=False, update_cache=False)

        after_mtime = ops.read_mtime_raw(str(f))
        self.assertIsNotNone(after_mtime)
        self.assertEqual(after_mtime, ts)
        after_btime = ops.read_btime_raw(str(f))
        self.assertIsNotNone(after_btime)
        self.assertEqual(after_btime, ts)

    def test_update_cache_true_updates_both(self):
        """update_cache=True must set both btime and mtime in the raw block."""
        ops = _ops()
        f = self._files[1]
        ts = int(datetime(2025, 12, 25, 10, 30, 0, tzinfo=timezone.utc).timestamp())
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)

        ops.fix_exfat_raw(str(f), dt, dry_run=False, update_cache=True)

        after_mtime = ops.read_mtime_raw(str(f))
        self.assertIsNotNone(after_mtime)
        self.assertEqual(after_mtime, ts)
        after_btime = ops.read_btime_raw(str(f))
        self.assertIsNotNone(after_btime)
        self.assertEqual(after_btime, ts)

    def test_btime_dt_preserves_with_update_cache_false(self):
        """btime_dt must preserve creation time even when update_cache=False."""
        ops = _ops()
        f = self._files[2]
        orig_btime_raw = ops.read_btime_raw(str(f))
        self.assertIsNotNone(orig_btime_raw)
        orig_btime_dt = datetime.fromtimestamp(orig_btime_raw, tz=timezone.utc)

        new_ts = int(datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        new_dt = datetime.fromtimestamp(new_ts, tz=timezone.utc)

        ops.fix_exfat_raw(str(f), new_dt, dry_run=False,
                          btime_dt=orig_btime_dt, update_cache=False)

        after_btime = ops.read_btime_raw(str(f))
        self.assertIsNotNone(after_btime)
        self.assertEqual(after_btime, orig_btime_raw,
                         'btime should be preserved')
        after_mtime = ops.read_mtime_raw(str(f))
        self.assertIsNotNone(after_mtime)
        self.assertEqual(after_mtime, new_ts,
                         'mtime should be updated')

    def test_dry_run_does_not_modify(self):
        """dry_run=True must not alter raw block data."""
        ops = _ops()
        f = self._files[3]
        before_mtime = ops.read_mtime_raw(str(f))
        before_btime = ops.read_btime_raw(str(f))

        dt = datetime(2099, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ops.fix_exfat_raw(str(f), dt, dry_run=True)

        after_mtime = ops.read_mtime_raw(str(f))
        after_btime = ops.read_btime_raw(str(f))
        self.assertEqual(after_mtime, before_mtime,
                         'dry_run should not change mtime')
        self.assertEqual(after_btime, before_btime,
                         'dry_run should not change btime')


if __name__ == '__main__':
    unittest.main()
