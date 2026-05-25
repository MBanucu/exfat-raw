# exfat-raw

Raw block-level read/write of exFAT filesystem timestamps — birth time (btime)
and modification time (mtime), directly from the on-disk directory entry,
bypassing the kernel driver's cache.

## Features

- **Read btime/mtime** — parse the exFAT directory entry on the raw block device
- **Write btime and mtime** — atomically update both timestamps in one raw-block access
- **Backing-file fast path** — uses `os.pread`/`os.pwrite` on loop device backing files
  (no subprocess overhead) with fallback to `sudo dd` for physical devices
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
```

## Dependencies

- Python ≥ 3.10 (stdlib only — `os`, `struct`, `subprocess`, `tempfile`, `pathlib`)
- System tools: `sudo`, `dd`, `findmnt`, `losetup` (for backing-file resolution and
  physical device fallback)

## License

GNU General Public License v3.0 or later.

---

Extracted from [gopro-timestamp-corrector](https://github.com/MBanucu/gopro-timestamp-corrector).
