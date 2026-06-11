"""Pluggable I/O strategy classes for ExfatRawIO.

Each strategy implements a different mechanism for reading/writing raw
blocks on a device path. Strategies are tried in order until one succeeds.

The base class and shared helpers live here; each concrete strategy is
defined in its own submodule and re-exported below.
"""

import os
from abc import ABC, abstractmethod


class IOStrategy(ABC):
    """Pluggable read/write strategy for raw block I/O."""

    @abstractmethod
    def read(self, device: str, offset: int, size: int) -> bytes | None:
        """Read *size* bytes from *device* at *offset*.

        Return bytes on success, or ``None`` to fall through to the
        next strategy in the chain.
        """

    @abstractmethod
    def write(self, device: str, offset: int, data: bytes) -> bool | None:
        """Write *data* to *device* at *offset*.

        Return ``True`` when handled, or ``None``/``False`` to fall
        through to the next strategy.
        """

    def clear_cache(self, device: str | None = None):
        """Drop cached state for *device* (or all if ``None``)."""


def _try_pread(path: str, offset: int, size: int) -> bytes | None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            return os.pread(fd, size, offset)
        finally:
            os.close(fd)
    except OSError:
        return None


def _try_pwrite(path: str, offset: int, data: bytes) -> bool:
    try:
        fd = os.open(path, os.O_WRONLY)
        try:
            n = os.pwrite(fd, data, offset)
            assert n == len(data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError:
        return False


BLOCK_SIZE = 512


def _block_align(offset: int, size: int) -> tuple[int, int, int]:
    """Return ``(aligned_offset, total_bytes, prefix_skip)``.

    Rounds *offset* down and *size* up so the resulting region is aligned
    to ``BLOCK_SIZE``.  *prefix_skip* is the number of bytes before the
    caller's data in the first block.
    """
    aligned = (offset // BLOCK_SIZE) * BLOCK_SIZE
    end = offset + size
    aligned_end = ((end + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE
    return aligned, aligned_end - aligned, offset - aligned


# ---------------------------------------------------------------------------
# Re-export each concrete strategy from its own submodule.
# ---------------------------------------------------------------------------

from exfat_raw._direct_io import DirectIOStrategy  # noqa: E402
from exfat_raw._backing_file import BackingFileStrategy  # noqa: E402
from exfat_raw._dd import DDStrategy  # noqa: E402
