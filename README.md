# exfat-raw

[![codecov](https://codecov.io/gh/MBanucu/exfat-raw/branch/main/graph/badge.svg)](https://codecov.io/gh/MBanucu/exfat-raw)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://www.python.org/)
[![PyPI version](https://img.shields.io/pypi/v/exfat-raw)](https://pypi.org/project/exfat-raw/)
[![License](https://img.shields.io/github/license/MBanucu/exfat-raw)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/MBanucu/exfat-raw/test.yml?branch=main)](https://github.com/MBanucu/exfat-raw/actions/workflows/test.yml)
[![Downloads](https://img.shields.io/pypi/dm/exfat-raw)](https://pypi.org/project/exfat-raw/)

Raw block-level read/write of exFAT filesystem timestamps — birth time (btime)
and modification time (mtime), directly from the on-disk directory entry,
bypassing the kernel driver's cache.

## Features

- **Read btime/mtime** — parse the exFAT directory entry on the raw block device
- **Write btime and mtime** — atomically update both timestamps in one raw-block access
- **3-tier I/O fallback** — tries direct `os.pread`/`os.pwrite` first (works on regular
  image files and accessible block devices), then loop device backing files, and
  finally falls back to `sudo dd` for restricted block devices
- **No kernel cache corruption** — understands the exFAT kernel driver's directory-entry
  cache incoherence and avoids `os.utime()` / `sync()` after raw writes
- **Pure stdlib** — zero runtime dependencies

## Usage

```python
from exfat_raw import ExfatRawIO, ExfatRawFilesystem, ExfatRawOps
from datetime import datetime, timezone

io = ExfatRawIO()
fs = ExfatRawFilesystem(io)
ops = ExfatRawOps(io, fs)

# Read birth time from a file on an exFAT mount
ts = ops.read_btime_raw("/mnt/sdcard/DCIM/100GOPRO/GH010001.MP4")
print(datetime.fromtimestamp(ts, tz=timezone.utc))

# Correct the timestamp
target = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
ops.fix_exfat_raw("/mnt/sdcard/DCIM/100GOPRO/GH010001.MP4", target, dry_run=False)

# Preserve btime while updating mtime
orig_btime_ts = ops.read_btime_raw(filepath)
orig_btime_dt = datetime.fromtimestamp(orig_btime_ts, tz=timezone.utc)
ops.fix_exfat_raw(filepath, new_mtime_dt, dry_run=False, btime_dt=orig_btime_dt)

# Work directly on a raw image file (no sudo, no mount)
io = ExfatRawIO()
fs = ExfatRawFilesystem(io)
boot = io.parse_boot("path/to/sdcard.img")
chain = fs.cluster_chain(boot, "path/to/sdcard.img", boot["root_cluster"])
```

> **Note:** All datetime parameters must be timezone-aware (e.g., `tzinfo=timezone.utc`). Naive datetimes are rejected with `ValueError`.

## Dependencies

- Python ≥ 3.10 (stdlib only — `os`, `struct`, `subprocess`, `tempfile`, `pathlib`)
- System tools: `sudo`, `dd`, `findmnt`, `losetup` — only needed for physical block
  devices; regular image files work with stdlib alone

## License

GNU General Public License v3.0 or later.

---

## Development

### Running tests

**Sandbox-safe** (no `sudo`, no mount — runs a pure-Python exFAT image):
```sh
python -m unittest discover -s tests -p 'test_exfat_raw_image.py' -v
```

**Full suite** (requires `sudo` + loop device + exfat-fuse):
```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

With Nix:
```sh
nix develop                   # enter dev shell
python -m unittest discover -s tests -p 'test_*.py' -v
```

The Nix package's `checkPhase` runs only the sandbox-safe tests (see `nix/exfat-raw/default.nix`).

---

Extracted from [gopro-timestamp-corrector](https://github.com/MBanucu/gopro-timestamp-corrector).
