"""Direct I/O strategy — reads/writes via ``os.pread``/``os.pwrite``."""

from exfat_raw._strategies import IOStrategy, _try_pread, _try_pwrite


class DirectIOStrategy(IOStrategy):
    """Read/write directly on *device* via ``os.pread``/``os.pwrite``.

    Works for regular files (e.g. disk images) and any block device
    the process has permission to access.
    """

    def read(self, device: str, offset: int, size: int) -> bytes | None:
        return _try_pread(device, offset, size)

    def write(self, device: str, offset: int, data: bytes) -> bool:
        return _try_pwrite(device, offset, data)
