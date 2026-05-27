"""Build minimal exFAT filesystem images in pure Python — no external tools."""

import os
import struct
from datetime import datetime, timezone

SECTOR_SIZE = 512


def _exfat_crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


def _entry_set_crc(entries: list[bytes]) -> int:
    crc = 0
    for e in entries:
        crc = _exfat_crc16(e[:2], crc)
        crc = _exfat_crc16(b'\x00\x00', crc)
        crc = _exfat_crc16(e[4:], crc)
    return crc


def _encode_time(dt: datetime) -> tuple[int, int, int]:
    utc = dt.replace(tzinfo=timezone.utc)
    total_sec = int(utc.timestamp())
    year, month, day = utc.year, utc.month, utc.day
    hour, minute = utc.hour, utc.minute
    sec = total_sec % 60
    ms = utc.microsecond // 1000
    date_word = ((year - 1980) << 9) | (month << 5) | day
    time_word = (hour << 11) | (minute << 5) | (sec // 2)
    time_ms = (sec % 2) * 100 + (ms // 10)
    return date_word, time_word, time_ms


def _build_file_entry_set(
    name: str,
    first_cluster: int,
    data_length: int,
    create_dt: datetime,
    modify_dt: datetime,
) -> list[bytes]:
    cd, ct, cms = _encode_time(create_dt)
    md, mt, mms = _encode_time(modify_dt)

    name_utf16 = name.encode('utf-16-le')
    name_chars = len(name)
    name_entries_count = max(1, (name_chars + 14) // 15)

    file_entry = bytearray(32)
    file_entry[0] = 0x85
    file_entry[1] = 1 + name_entries_count
    struct.pack_into('<H', file_entry, 4, 0x20)
    struct.pack_into('<H', file_entry, 0x08, mt)
    struct.pack_into('<H', file_entry, 0x0A, md)
    struct.pack_into('<H', file_entry, 0x0C, ct)
    struct.pack_into('<H', file_entry, 0x0E, cd)
    struct.pack_into('<H', file_entry, 0x10, mt)
    struct.pack_into('<H', file_entry, 0x12, md)
    file_entry[0x14] = mms
    file_entry[0x16] = cms

    stream_entry = bytearray(32)
    stream_entry[0] = 0xC1
    stream_entry[4] = name_chars
    struct.pack_into('<Q', stream_entry, 0x08, data_length)
    struct.pack_into('<I', stream_entry, 0x14, first_cluster)
    struct.pack_into('<Q', stream_entry, 0x18, data_length)

    name_entries = []
    for i in range(name_entries_count):
        ne = bytearray(32)
        ne[0] = 0xC1
        chunk = name_utf16[i * 30:(i + 1) * 30]
        ne[2:2 + len(chunk)] = chunk
        name_entries.append(bytes(ne))

    entries = [bytes(file_entry), bytes(stream_entry)] + name_entries
    crc = _entry_set_crc(entries)
    file_entry[2:4] = struct.pack('<H', crc)
    entries[0] = bytes(file_entry)
    return entries


def create_minimal_exfat_image(
    path: str,
    files: list[tuple[str, bytes, datetime, datetime]] | None = None,
    total_sectors: int = 128,
) -> dict:
    """Create a minimal exFAT image at *path*. Returns boot dict matching
    ``ExfatRawIO.parse_boot()`` output.

    Parameters
    ----------
    path
        Destination file path.
    files
        List of (name, data, create_dt, modify_dt) tuples.
    total_sectors
        Total size of the image in 512-byte sectors (default 128 = 64 KB).

    Returns
    -------
    dict
        Boot sector metadata keys: bytes_per_sector, sec_per_cluster,
        cluster_size, fat_offset, cluster_heap_offset, root_cluster.
    """
    files = files or []
    bps = SECTOR_SIZE
    spc = 1
    cluster_size = bps * spc
    fat_offset_sectors = 1
    fat_length_sectors = 2
    cluster_heap_offset_sectors = fat_offset_sectors + fat_length_sectors
    cluster_count = total_sectors - cluster_heap_offset_sectors
    root_cluster = 2

    root_clusters_needed = max(1, (len(files) * 3 * 32 + bps - 1) // bps)
    root_fat_chain = list(range(root_cluster, root_cluster + root_clusters_needed))

    next_cluster = root_cluster + root_clusters_needed
    cluster_chains = {root_cluster: root_fat_chain}
    file_cluster_map = {}

    for name, data, cd, md in files:
        fc = next_cluster
        next_cluster += 1
        cluster_chains[fc] = 0x0FFFFFFF
        file_cluster_map[name] = fc

    sectors = [None] * total_sectors

    boot = bytearray(SECTOR_SIZE)
    boot[0:3] = b'\xEB\x76\x90'
    boot[3:11] = b'EXFAT   '
    struct.pack_into('<Q', boot, 0x40, 0)
    struct.pack_into('<Q', boot, 0x48, total_sectors)
    struct.pack_into('<I', boot, 0x50, fat_offset_sectors)
    struct.pack_into('<I', boot, 0x54, fat_length_sectors)
    struct.pack_into('<I', boot, 0x58, cluster_heap_offset_sectors)
    struct.pack_into('<I', boot, 0x5C, cluster_count)
    struct.pack_into('<I', boot, 0x60, root_cluster)
    struct.pack_into('<I', boot, 0x64, 0x12345678)
    struct.pack_into('<H', boot, 0x68, 0x0100)
    boot[0x6C] = 9
    boot[0x6D] = 0
    boot[0x6E] = 1
    boot[0x6F] = 0x80
    boot[0x70] = 0xFF
    boot[510:512] = b'\x55\xAA'
    sectors[0] = bytes(boot)

    max_cl = max(
        (c for chain in cluster_chains.values()
         for c in (chain if isinstance(chain, list) else [chain])),
        default=root_cluster,
    )
    fat_entries_count = max_cl + 1
    fat = bytearray(fat_entries_count * 4)
    struct.pack_into('<I', fat, 0, 0xFFFFFFF8)
    struct.pack_into('<I', fat, 4, 0xFFFFFFFF)
    for start, chain in cluster_chains.items():
        if isinstance(chain, list):
            for i, cl in enumerate(chain):
                nxt = chain[i + 1] if i + 1 < len(chain) else 0x0FFFFFFF
                struct.pack_into('<I', fat, cl * 4, nxt)
        else:
            struct.pack_into('<I', fat, start * 4, chain)
    for i in range(fat_length_sectors):
        chunk = fat[i * bps:(i + 1) * bps]
        sectors[fat_offset_sectors + i] = chunk.ljust(bps, b'\x00')

    dir_buf = bytearray()
    for name, data, cd, md in files:
        fc = file_cluster_map[name]
        entries = _build_file_entry_set(name, fc, len(data), cd, md)
        for e in entries:
            dir_buf.extend(e)
    dir_buf = dir_buf.ljust(root_clusters_needed * bps, b'\x00')
    for i, cl in enumerate(root_fat_chain):
        cl_idx = cl - root_cluster
        sec_idx = cluster_heap_offset_sectors + cl_idx
        if sec_idx < total_sectors:
            sectors[sec_idx] = dir_buf[cl_idx * bps:(cl_idx + 1) * bps]

    for name, data, cd, md in files:
        fc = file_cluster_map[name]
        cl_idx = fc - root_cluster
        sec_idx = cluster_heap_offset_sectors + cl_idx
        if sec_idx < total_sectors:
            sectors[sec_idx] = data.ljust(bps, b'\x00')

    with os.fdopen(os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644), 'wb') as f:
        for s in sectors:
            f.write(s if s is not None else b'\x00' * bps)

    return {
        'bytes_per_sector': bps,
        'sec_per_cluster': 1,
        'cluster_size': cluster_size,
        'fat_offset': fat_offset_sectors * bps,
        'cluster_heap_offset': cluster_heap_offset_sectors * bps,
        'root_cluster': root_cluster,
    }


def decode_entry_timestamps(entry: bytes) -> dict:
    """Extract timestamps from a file directory entry (type 0x85).
    Returns {btime, mtime} as datetimes.
    """
    from exfat_raw._pure import _exfat_decode_time

    tw_m = struct.unpack_from('<H', entry, 0x08)[0]
    dw_m = struct.unpack_from('<H', entry, 0x0A)[0]
    ms_m = entry[0x14]
    tw_b = struct.unpack_from('<H', entry, 0x0C)[0]
    dw_b = struct.unpack_from('<H', entry, 0x0E)[0]
    ms_b = entry[0x16]

    return {
        'mtime': _exfat_decode_time(tw_m, dw_m, ms_m),
        'btime': _exfat_decode_time(tw_b, dw_b, ms_b),
    }
