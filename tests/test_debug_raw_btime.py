"""Debug tests for exFAT raw block write/read cycle on CI.

Isolates each step of the pipeline to identify why the raw block write
reports success but the data does not persist on Ubuntu CI kernels (<6.12).
"""

import logging
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conftest import (
    copy_sparse_image,
    decompress_sparse_image,
    setup_loop_device,
    teardown_loop_device,
)


def _raw_io():
    from exfat_raw import ExfatRawIO, ExfatRawFilesystem, ExfatRawOps
    io = ExfatRawIO()
    fs = ExfatRawFilesystem(io)
    ops = ExfatRawOps(io, fs)
    return io, fs, ops


def _read_mtime(filepath):
    ts = os.path.getmtime(filepath)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


logger = logging.getLogger(__name__)

if os.environ.get('EXFAT_RAW_VERBOSE', '').lower() not in ('', '0', 'false', 'no'):
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')


def _stat_birth_time(path: str) -> int | None:
    if sys.platform == 'darwin':
        r = subprocess.run(['stat', '-f', '%B', path],
                           capture_output=True, text=True)
    else:
        r = subprocess.run(['stat', '-c', '%W', path],
                           capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        try:
            return int(r.stdout.strip())
        except ValueError:
            return None
    return None


class DebugRawBtime(unittest.TestCase):
    """Isolate each step: dd write, boot parse, entry lookup, btime read/write."""

    _loop_dev = None
    _mount_point = None
    _work_dir = None
    _target = None

    @classmethod
    def setUpClass(cls):
        import shutil
        gz_path = Path(__file__).parent / 'sdcard.img.gz'
        if not gz_path.exists():
            raise unittest.SkipTest(f'Compressed image not found at {gz_path}')

        cached = Path(__file__).parent / 'sdcard.img'
        decompress_sparse_image(gz_path, cached)

        cls._work_dir = Path(tempfile.mkdtemp(prefix='exfat_debug_'))
        cls._img_path = cls._work_dir / 'sdcard.img'
        copy_sparse_image(cached, cls._img_path)

        cls._loop_dev, cls._mount_point = setup_loop_device(cls._img_path)
        cls.addClassCleanup(teardown_loop_device, cls._loop_dev, cls._mount_point)
        cls.addClassCleanup(shutil.rmtree, cls._work_dir, ignore_errors=True)
        cls._target = Path(cls._mount_point) / 'DCIM' / '100GOPRO'
        if not cls._target.exists():
            raise unittest.SkipTest(f'{cls._target} not found')

        # Write test pattern at known offset BEFORE any exFAT modifications,
        # so test_05 can verify it on kernels where the exFAT driver remounts
        # read-only after detecting raw block writes (CI's kernel <6.12).
        from exfat_raw._resolve import resolve_device
        dev = resolve_device(str(cls._mount_point))
        cls._test_05_offset = 50000 * 512  # ~25 MB, well within pre-allocated sparse file region
        cls._test_05_pattern = b'CLUSTER_WRITE_TEST_99'
        r = subprocess.run(
            ['sudo', 'dd', f'of={dev}', 'bs=1', f'seek={cls._test_05_offset}',
             f'count={len(cls._test_05_pattern)}'],
            input=cls._test_05_pattern, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        cls._test_05_available = r.returncode == 0

    def _first_file(self):
        files = sorted(self._target.glob('*.MP4')) or sorted(self._target.iterdir())
        return files[0]

    def _resolve_device(self):
        from exfat_raw._resolve import resolve_device
        return resolve_device(str(self._mount_point))

    @property
    def _io(self):
        if not hasattr(self, '__io'):
            self.__io, self.__fs, self.__ops = _raw_io()
        return self.__io

    @property
    def _fs(self):
        if not hasattr(self, '__fs'):
            self.__io, self.__fs, self.__ops = _raw_io()
        return self.__fs

    @property
    def _ops(self):
        if not hasattr(self, '__ops'):
            self.__io, self.__fs, self.__ops = _raw_io()
        return self.__ops

    def _exfat_boot(self):
        dev = self._resolve_device()
        self.assertIsNotNone(dev)
        boot = self._io.parse_boot(dev)
        self.assertIsNotNone(boot)
        return boot, dev

    def test_01_dd_write_read_raw(self):
        dev = self._resolve_device()
        test_offset = 100000 * 512
        expected = b'DEBUG_TEST_PATTERN_42'
        subprocess.run(
            ['sudo', 'dd', f'of={dev}', 'bs=1',
             f'seek={test_offset}', f'count={len(expected)}'],
            input=expected, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL)
        subprocess.run(['sync'])
        r = subprocess.run(
            ['sudo', 'dd', f'if={dev}', 'bs=1',
             f'skip={test_offset}', f'count={len(expected)}'],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        actual = r.stdout
        self.assertEqual(expected, actual,
                         f'dd write/read mismatch: expected={expected!r} actual={actual!r}')

    def test_02_dd_write_file_cluster_direct(self):
        boot, dev = self._exfat_boot()
        first = self._first_file()
        entry = self._fs.find_file_entry(boot, str(dev), str(first))
        self.assertIsNotNone(entry, f'Could not find entry for {first.name}')

        time_word = struct.unpack_from('<H', entry, 0x0C)[0]
        date_word = struct.unpack_from('<H', entry, 0x0E)[0]
        time_ms = entry[0x16]
        logger.debug('%s: raw entry creation time_word=%d date_word=%d time_ms=%d', first.name, time_word, date_word, time_ms)

    def test_03_btime_readback_before_correction(self):
        first = self._first_file()
        btime_val = self._ops.read_btime_raw(str(first))
        stat_val = _stat_birth_time(str(first))
        logger.debug('%s: raw_btime=%s stat_btime=%s', first.name, btime_val, stat_val)
        self.assertIsNotNone(btime_val, 'raw btime readback returned None')

    def test_04_fix_exfat_raw_then_readback(self):
        first = self._first_file()

        orig_mtime = _read_mtime(first)
        self.assertIsNotNone(orig_mtime)
        delta = timedelta(hours=-2)
        target_dt = orig_mtime + delta
        target_ts = int(target_dt.replace(tzinfo=timezone.utc).timestamp())

        logger.debug('%s: orig_mtime=%s target_dt=%s target_ts=%s', first.name, orig_mtime, target_dt, target_ts)

        before_btime = self._ops.read_btime_raw(str(first))
        logger.debug('%s: before_btime=%s', first.name, before_btime)

        self._ops.fix_exfat_raw(str(first), target_dt, dry_run=False)

        after_btime = self._ops.read_btime_raw(str(first))
        after_stat = _stat_birth_time(str(first))
        logger.debug('%s: after_raw=%s after_stat=%s', first.name, after_btime, after_stat)

        if after_btime is not None:
            diff = abs(after_btime - target_ts)
            logger.debug('%s: diff=%ds (target_ts=%s after_raw=%s)', first.name, diff, target_ts, after_btime)
            if diff > 2:
                from exfat_raw._pure import _exfat_decode_time
                dev = self._resolve_device()
                boot = self._io.parse_boot(str(dev))
                post_entry = self._fs.find_file_entry(boot, str(dev), str(first))
                if post_entry:
                    pt_word = struct.unpack_from('<H', post_entry, 0x0C)[0]
                    pd_word = struct.unpack_from('<H', post_entry, 0x0E)[0]
                    pms = post_entry[0x16]
                    decoded = _exfat_decode_time(pt_word, pd_word, pms)
                    logger.debug('%s: post-fix raw entry time_word=%d date_word=%d time_ms=%d decoded=%s', first.name, pt_word, pd_word, pms, decoded)
                    logger.debug('%s: post-fix raw entry bytes: %s', first.name, post_entry.hex())
        self.assertEqual(after_btime, target_ts,
                         f'{first.name}: raw btime ({after_btime}) != target ({target_ts})')

    def test_05_raw_write_different_cluster(self):
        if not self._test_05_available:
            self.skipTest('setUpClass dd write failed')
        dev = self._resolve_device()
        if not dev:
            self.skipTest('Could not resolve loop device')
        r = subprocess.run(
            ['sudo', 'dd', f'if={dev}', 'bs=1',
             f'skip={self._test_05_offset}',
             f'count={len(self._test_05_pattern)}'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if r.returncode != 0:
            err = r.stderr.decode(errors='replace').strip()[:200] if r.stderr else ''
            self.skipTest(f'dd read failed at offset {self._test_05_offset}: {err}')
        self.assertEqual(self._test_05_pattern, r.stdout,
                         f'Cluster readback mismatch at offset {self._test_05_offset}')

    def test_06_find_entry_name_match(self):
        boot, dev = self._exfat_boot()
        first = self._first_file()
        entry = self._fs.find_file_entry(boot, str(dev), str(first))
        self.assertIsNotNone(entry)

        time_word = struct.unpack_from('<H', entry, 0x08)[0]
        date_word = struct.unpack_from('<H', entry, 0x0A)[0]
        time_ms = entry[0x14]
        from exfat_raw._pure import _exfat_decode_time
        raw_mtime = _exfat_decode_time(time_word, date_word, time_ms)

        via_raw_api = self._ops.read_mtime_raw(str(first))
        self.assertIsNotNone(via_raw_api, f'{first.name}: read_mtime_raw returned None')
        diff = int(raw_mtime.timestamp()) - via_raw_api
        logger.debug('%s: raw_mtime=%s via_raw_api=%s diff=%ds', first.name, raw_mtime, via_raw_api, diff)
        self.assertLessEqual(abs(diff), 2,
                             f'{first.name}: decoded mtime ({raw_mtime}) differs from '
                             f'read_mtime_raw ({via_raw_api}) by {diff}s')

    def test_07_write_all_files_then_readback(self):
        files = sorted(self._target.glob('*'))
        self.assertGreaterEqual(len(files), 1)
        delta = timedelta(hours=-2)
        errors = []
        for fp in files[:12]:
            orig_mtime = _read_mtime(fp)
            target_dt = orig_mtime + delta
            target_ts = int(target_dt.replace(tzinfo=timezone.utc).timestamp())

            before_btime = self._ops.read_btime_raw(str(fp))
            self._ops.fix_exfat_raw(str(fp), target_dt, dry_run=False)
            after_btime = self._ops.read_btime_raw(str(fp))

            after_stat = _stat_birth_time(str(fp))

            logger.debug('%s: before=%s after_raw=%s after_stat=%s target=%s orig_mtime=%s', fp.name, before_btime, after_btime, after_stat, target_ts, int(orig_mtime.timestamp()))

            if after_btime is not None:
                diff = abs(after_btime - target_ts)
                if diff > 2:
                    errors.append(f'{fp.name}: raw={after_btime} target={target_ts} diff={diff}')
        self.assertEqual(errors, [], '\n'.join(errors))


if __name__ == '__main__':
    unittest.main()
