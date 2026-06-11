"""DD strategy — falls back to ``sudo dd`` for raw block device I/O."""

import subprocess
import tempfile

from exfat_raw._strategies import IOStrategy, BLOCK_SIZE, _block_align


class DDStrategy(IOStrategy):
    """Fall back to ``sudo dd`` for read/write on physical block devices.

    Used when the process lacks direct access to the device and must
    elevate privileges via ``sudo``.

    I/O is always done in multiples of ``BLOCK_SIZE`` (512 bytes) to
    support platforms where the device requires sector-aligned access
    (e.g. macOS ``/dev/rdisk*`` raw devices).
    """

    def read(self, device: str, offset: int, size: int) -> bytes | None:
        try:
            aligned_off, total, skip = _block_align(offset, size)
            cmd = ['sudo', 'dd', f'if={device}', f'bs={BLOCK_SIZE}',
                   f'skip={aligned_off // BLOCK_SIZE}',
                   f'count={total // BLOCK_SIZE}']
            r = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
            if r.returncode != 0:
                return None
            return r.stdout[skip:skip + size]
        except FileNotFoundError:
            return None

    def write(self, device: str, offset: int, data: bytes) -> bool:
        try:
            aligned_off, total, skip = _block_align(offset, len(data))
            if skip == 0 and total == len(data):
                return self._write_blocks(device, aligned_off, data)
            buf = self.read(device, aligned_off, total)
            if buf is None or len(buf) < total:
                return False
            buf = bytearray(buf)
            buf[skip:skip + len(data)] = data
            return self._write_blocks(device, aligned_off, bytes(buf))
        except FileNotFoundError:
            return False

    def _write_blocks(self, device: str, offset: int, data: bytes) -> bool:
        with tempfile.NamedTemporaryFile() as tf:
            tf.write(data)
            tf.flush()
            cmd = ['sudo', 'dd', f'if={tf.name}', f'of={device}',
                   f'bs={BLOCK_SIZE}',
                   f'seek={offset // BLOCK_SIZE}',
                   f'count={len(data) // BLOCK_SIZE}',
                   'conv=fsync']
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL)
        return True
