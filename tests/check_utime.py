"""Check os.utime capability on exFAT before running tests.

Sets up a loop device from the test image, attempts os.utime
on an existing file, reports the result, then tears down.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conftest import decompress_sparse_image, setup_loop_device, teardown_loop_device

TARGET_DIR = 'DCIM/100GOPRO'


def main() -> int:
    gz = Path(__file__).parent / 'sdcard.img.gz'
    if not gz.exists():
        print('::error ::sdcard.img.gz not found')
        return 1

    cached = Path(__file__).parent / 'sdcard.img'
    decompress_sparse_image(gz, cached)

    work = Path(tempfile.mkdtemp(prefix='exfat_utime_check_'))
    img = work / 'sdcard.img'
    subprocess.run(['cp', '--sparse=always', str(cached), str(img)],
                   check=True, capture_output=True)

    loop_dev = mount_point = None
    try:
        loop_dev, mount_point = setup_loop_device(str(img))

        target = Path(mount_point) / TARGET_DIR
        files = sorted(target.glob('*'))
        if not files:
            print(f'::error ::no files found in {target}')
            return 1
        scratch = files[0].resolve()

        kernel_ver = os.uname().release
        mount_out = subprocess.run(
            ['mount', '-t', 'exfat'], capture_output=True, text=True).stdout

        print(f'[capability] kernel: {kernel_ver}')
        print(f'[capability] mount:  {mount_point}')
        for line in mount_out.strip().splitlines():
            if mount_point in line:
                print(f'[capability] mount_info: {line}')
        print(f'[capability] test_file: {scratch.name}')

        # primary check
        utime_ok = True
        utime_error = ''
        try:
            os.utime(scratch, (1234567890.0, 1234567890.0))
        except (OSError, PermissionError) as exc:
            utime_ok = False
            utime_error = f'{type(exc).__name__}: {exc}'

        if utime_ok:
            print(f'[capability] os.utime ... OK')
        else:
            print(f'[capability] os.utime ... FAIL')
            print(f'[capability]   reason: {utime_error}')

        # double-check via stat
        if utime_ok:
            st = scratch.stat()
            reported = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
            expected = datetime.fromtimestamp(1234567890.0, tz=timezone.utc)
            match = abs((reported - expected).total_seconds()) <= 1
            print(f'[capability] stat verifies {"OK" if match else "MISMATCH"}'
                  f'  (expected={expected}, got={reported})')
            if not match:
                utime_ok = False

        # summary
        if utime_ok:
            print('[capability] result: os.utime WORKS on this kernel/driver')
        else:
            print('[capability] result: os.utime DOES NOT WORK on this kernel/driver')

        return 0 if utime_ok else 1

    finally:
        if loop_dev:
            teardown_loop_device(loop_dev, mount_point)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
