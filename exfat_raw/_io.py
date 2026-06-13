"""Low-level raw block I/O for exFAT filesystems.

I/O strategies are tried in order until one succeeds. The default
chain is: direct I/O → backing file → ``sudo dd``.
"""

import struct

from exfat_raw._strategies import (
    IOStrategy,
    DirectIOStrategy,
    BackingFileStrategy,
    DDStrategy,
)


def _default_strategies() -> list[IOStrategy]:
    return [DirectIOStrategy(), BackingFileStrategy(), DDStrategy()]


class ExfatRawIO:
    """Raw block I/O — delegates to a chain of pluggable strategies.

    Parameters
    ----------
    strategies
        Ordered list of ``IOStrategy`` instances. Defaults to
        ``[DirectIOStrategy(), BackingFileStrategy(), DDStrategy()]``
        on Linux; ``[DirectIOStrategy(), DDStrategy()]`` on macOS.
    """

    def __init__(self, strategies: list[IOStrategy] | None = None):
        self._strategies = strategies or _default_strategies()

    def clear_cache(self, device: str | None = None):
        for s in self._strategies:
            s.clear_cache(device)

    def read(self, device: str, offset: int, size: int) -> bytes:
        for s in self._strategies:
            result = s.read(device, offset, size)
            if result is not None:
                return result
        return b''

    def write(self, device: str, offset: int, data: bytes):
        for s in self._strategies:
            if s.write(device, offset, data):
                return

    @staticmethod
    def _parse_boot_bytes(data: bytes) -> dict | None:
        if len(data) < 512:
            return None
        sig = struct.unpack_from('<H', data, 510)[0]
        if sig != 0xAA55:
            return None
        oem = data[3:11]
        if oem != b'EXFAT   ':
            return None
        bps_shift = data[0x6C]
        if bps_shift not in (9, 10, 11, 12):
            return None
        bps = 1 << bps_shift
        spc_shift = data[0x6D]
        if bps_shift + spc_shift > 25:
            return None
        spc = 1 << spc_shift
        ver = struct.unpack_from('<H', data, 0x68)[0]
        if ver != 0x0100:
            return None
        return {
            'bytes_per_sector': bps,
            'sec_per_cluster': spc,
            'cluster_size': bps * spc,
            'fat_offset': struct.unpack_from('<I', data, 0x50)[0] * bps,
            'cluster_heap_offset': struct.unpack_from('<I', data, 0x58)[0] * bps,
            'root_cluster': struct.unpack_from('<I', data, 0x60)[0],
        }

    def parse_boot(self, device: str):
        try:
            data = self.read(device, 0, 512)
        except Exception:
            return None
        return self._parse_boot_bytes(data)
