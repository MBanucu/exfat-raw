"""Raw exFAT block-read/write operations.

Layers (one file per layer):
  ``_pure``        — CRC, time encoding/decoding (stateless)
  ``_io``          — ``ExfatRawIO`` (strategy chain + boot parse)
  ``_fs``          — ``ExfatRawFilesystem`` (FAT, clusters, directory traversal)
  ``_ops``         — ``ExfatRawOps`` (high-level read/write of btime/mtime)

I/O strategies and device resolution are delegated to the
``rawblock_io`` package.

Singletons
==========
``exfat_io`` — default ``ExfatRawIO`` instance
``exfat_ops`` — default ``ExfatRawOps`` instance composed from ``exfat_io`` + ``ExfatRawFilesystem``

Tests should create their own ``ExfatRawIO()`` / ``ExfatRawOps()`` instances for cache isolation.

Verbosity
=========
Set ``EXFAT_RAW_VERBOSE=1`` to enable info-level log output
(e.g. progress messages from ``fix_exfat_raw``).
"""

import logging
import os

if os.environ.get('EXFAT_RAW_VERBOSE', '').lower() not in ('', '0', 'false', 'no'):
    logging.basicConfig(level=logging.INFO, format='%(message)s')

from rawblock_io import IOStrategy, DirectIOStrategy, BackingFileStrategy, DDStrategy
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
