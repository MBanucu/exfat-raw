"""Low-level raw block I/O for exFAT filesystems.

I/O strategies are tried in order until one succeeds. The default
chain is: direct I/O → backing file → ``sudo dd``.
"""

import platform
import struct

from exfat_raw._strategies import (
    IOStrategy,
    DirectIOStrategy,
    BackingFileStrategy,
    DDStrategy,
)


def _default_strategies() -> list[IOStrategy]:
    if platform.system() == 'Darwin':
        return [DirectIOStrategy(), DDStrategy()]
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

    def parse_boot(self, device: str):
        try:
            data = self.read(device, 0, 512)
        except Exception:
            return None
        if len(data) < 512:
            return None
        sig = struct.unpack_from('<H', data, 510)[0]
        if sig != 0xAA55:
            return None
        bps = 1 << data[0x6C]
        spc = 1 << data[0x6D]
        return {
            'bytes_per_sector': bps,
            'sec_per_cluster': spc,
            'cluster_size': bps * spc,
            'fat_offset': struct.unpack_from('<I', data, 0x50)[0] * bps,
            'cluster_heap_offset': struct.unpack_from('<I', data, 0x58)[0] * bps,
            'root_cluster': struct.unpack_from('<I', data, 0x60)[0],
        }
