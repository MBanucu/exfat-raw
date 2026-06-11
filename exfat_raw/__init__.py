"""Raw exFAT block-read/write operations.

Layers (one file per layer):
  ``_pure``        — CRC, time encoding/decoding (stateless)
  ``_resolve``     — Block device / mount point resolution
  ``_strategies``  — Pluggable I/O strategy base class & helpers
  ``_direct_io``   — ``DirectIOStrategy``
  ``_backing_file`` — ``BackingFileStrategy``
  ``_dd``          — ``DDStrategy``
  ``_io``          — ``ExfatRawIO`` (strategy chain + boot parse)
  ``_fs``          — ``ExfatRawFilesystem`` (FAT, clusters, directory traversal)
  ``_ops``         — ``ExfatRawOps`` (high-level read/write of btime/mtime)

Singletons
==========
``exfat_io`` — default ``ExfatRawIO`` instance
``exfat_ops`` — default ``ExfatRawOps`` instance composed from ``exfat_io`` + ``ExfatRawFilesystem``

Tests should create their own ``ExfatRawIO()`` / ``ExfatRawOps()`` instances for cache isolation.
"""

from exfat_raw._strategies import IOStrategy, DirectIOStrategy, BackingFileStrategy, DDStrategy
from exfat_raw._io import ExfatRawIO
from exfat_raw._fs import ExfatRawFilesystem
from exfat_raw._ops import ExfatRawOps

exfat_io: ExfatRawIO = ExfatRawIO()
exfat_fs: ExfatRawFilesystem = ExfatRawFilesystem(exfat_io)
exfat_ops: ExfatRawOps = ExfatRawOps(exfat_io, exfat_fs)

__all__ = [
    'IOStrategy',
    'DirectIOStrategy',
    'BackingFileStrategy',
    'DDStrategy',
    'ExfatRawIO',
    'ExfatRawFilesystem',
    'ExfatRawOps',
    'exfat_io',
    'exfat_fs',
    'exfat_ops',
]
