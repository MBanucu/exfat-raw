"""Sandbox-safe tests using a pure-Python minimal exFAT image — no sudo, no mount."""

import struct
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from exfat_raw import ExfatRawIO, ExfatRawFilesystem
from exfat_raw._pure import _exfat_decode_time, _exfat_encode_time, _exfat_entry_set_crc

from helpers import create_minimal_exfat_image, decode_entry_timestamps


def _temp_img():
    return Path(tempfile.mkdtemp(prefix='exfat_test_')) / 'test.img'


class TestBootSectorParsing(unittest.TestCase):
    """parse_boot must correctly read a pure-Python exFAT image."""

    def test_parses_valid_boot_sector(self):
        img = _temp_img()
        create_minimal_exfat_image(str(img))
        io = ExfatRawIO()
        boot = io.parse_boot(str(img))
        self.assertIsNotNone(boot)
        self.assertEqual(boot['bytes_per_sector'], 512)
        self.assertEqual(boot['sec_per_cluster'], 1)
        self.assertEqual(boot['cluster_size'], 512)
        self.assertGreater(boot['fat_offset'], 0)
        self.assertGreater(boot['cluster_heap_offset'], 0)
        self.assertEqual(boot['root_cluster'], 2)

    def test_rejects_non_exfat_sector(self):
        io = ExfatRawIO()
        boot = io.parse_boot('/dev/null')
        self.assertIsNone(boot)

    def test_rejects_nonexistent_path(self):
        io = ExfatRawIO()
        boot = io.parse_boot('/nonexistent/exfat.img')
        self.assertIsNone(boot)

    def test_rejects_wrong_oem_label(self):
        boot = bytearray(512)
        boot[510:512] = b'\x55\xAA'
        io = ExfatRawIO()
        self.assertIsNone(io._parse_boot_bytes(bytes(boot)))

    def test_rejects_invalid_bps_shift(self):
        boot = bytearray(512)
        boot[3:11] = b'EXFAT   '
        boot[510:512] = b'\x55\xAA'
        boot[0x6C] = 13
        io = ExfatRawIO()
        self.assertIsNone(io._parse_boot_bytes(bytes(boot)))

    def test_rejects_oversized_cluster(self):
        boot = bytearray(512)
        boot[3:11] = b'EXFAT   '
        boot[510:512] = b'\x55\xAA'
        boot[0x6C] = 9
        boot[0x6D] = 17
        io = ExfatRawIO()
        self.assertIsNone(io._parse_boot_bytes(bytes(boot)))

    def test_accepts_valid_boot_bytes(self):
        boot = bytearray(512)
        boot[3:11] = b'EXFAT   '
        boot[510:512] = b'\x55\xAA'
        boot[0x6C] = 9
        boot[0x6D] = 0
        io = ExfatRawIO()
        result = io._parse_boot_bytes(bytes(boot))
        self.assertIsNotNone(result)
        self.assertEqual(result['bytes_per_sector'], 512)
        self.assertEqual(result['sec_per_cluster'], 1)


class TestRawBlockReadWrite(unittest.TestCase):
    """ExfatRawIO.read/write on a regular file must work without sudo."""

    def setUp(self):
        self.img = _temp_img()
        self.boot = create_minimal_exfat_image(str(self.img))
        self.io = ExfatRawIO()

    def test_read_boot_sector(self):
        data = self.io.read(str(self.img), 0, 512)
        self.assertEqual(len(data), 512)
        self.assertEqual(data[510:512], b'\x55\xAA')

    def test_read_write_fat_entry(self):
        offset = self.boot['fat_offset'] + 2 * 4
        original = self.io.read(str(self.img), offset, 4)
        self.assertEqual(len(original), 4)
        val = struct.unpack_from('<I', original, 0)[0]
        new_val = 0x0FFFFFFF
        self.io.write(str(self.img), offset, struct.pack('<I', new_val))
        reread = self.io.read(str(self.img), offset, 4)
        self.assertEqual(struct.unpack_from('<I', reread, 0)[0], new_val)

    def test_read_root_cluster(self):
        off = self.boot['cluster_heap_offset']
        data = self.io.read(str(self.img), off, 512)
        self.assertEqual(len(data), 512)


class TestFindInDir(unittest.TestCase):
    """ExfatRawFilesystem.find_in_dir must locate entries in the image."""

    def setUp(self):
        self.img = _temp_img()
        self.t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.t1 = datetime(2025, 6, 15, 18, 30, 0, tzinfo=timezone.utc)
        self.boot = create_minimal_exfat_image(str(self.img), files=[
            ('test.txt', b'hello world', self.t0, self.t1),
        ])
        self.io = ExfatRawIO()
        self.fs = ExfatRawFilesystem(self.io)

    def test_finds_file_entry_by_name(self):
        result = self.fs.find_in_dir(self.boot, str(self.img),
                                     self.boot['root_cluster'], 'test.txt')
        self.assertIsNotNone(result)
        chain, ci, off_in_cluster, sc, entries = result
        self.assertEqual(entries[0][0], 0x85)
        self.assertGreaterEqual(entries[1][0], 0xC0)

    def test_returns_none_for_missing_entry(self):
        result = self.fs.find_in_dir(self.boot, str(self.img),
                                     self.boot['root_cluster'], 'nope.txt')
        self.assertIsNone(result)

    def test_entry_has_expected_timestamps(self):
        result = self.fs.find_in_dir(self.boot, str(self.img),
                                     self.boot['root_cluster'], 'test.txt')
        entry = result[4][0]
        decoded = decode_entry_timestamps(entry)
        self.assertEqual(decoded['btime'], self.t0)
        self.assertEqual(decoded['mtime'], self.t1)


class TestTimestampRoundTrip(unittest.TestCase):
    """_exfat_encode_time -> entry bytes -> _exfat_decode_time must round-trip."""

    def test_round_trip_simple(self):
        dt = datetime(2025, 6, 15, 12, 30, 45, tzinfo=timezone.utc)
        dw, tw, ms = _exfat_encode_time(dt)
        decoded = _exfat_decode_time(tw, dw, ms)
        self.assertEqual(decoded, dt.replace(microsecond=0))

    def test_round_trip_milliseconds(self):
        dt = datetime(2025, 6, 15, 12, 30, 45, 123000, tzinfo=timezone.utc)
        dw, tw, ms = _exfat_encode_time(dt)
        decoded = _exfat_decode_time(tw, dw, ms)
        self.assertEqual(decoded.second, 45)
        self.assertEqual(decoded.microsecond, 120000)

    def test_round_trip_odd_seconds(self):
        dt = datetime(2025, 6, 15, 12, 30, 43, tzinfo=timezone.utc)
        dw, tw, ms = _exfat_encode_time(dt)
        self.assertGreaterEqual(ms, 100)
        decoded = _exfat_decode_time(tw, dw, ms)
        self.assertEqual(decoded, dt)

    def test_round_trip_various_years(self):
        for year in [1980, 2000, 2025, 2049, 2107]:
            dt = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            dw, tw, ms = _exfat_encode_time(dt)
            decoded = _exfat_decode_time(tw, dw, ms)
            self.assertEqual(decoded, dt,
                             f'Failed for year {year}: got {decoded}')


class TestCRC(unittest.TestCase):
    """_exfat_entry_set_crc must compute correct checksums."""

    def test_crc_consistency(self):
        entries = [
            b'\x85\x02\x00\x00\x20\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00',
            b'\xC1\x00\x00\x00\x05\x00\x00\x00'
            b'\x05\x00\x00\x00\x00\x00\x00\x00'
            b'\x04\x00\x00\x00\x05\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00',
            b'\xC1\x00\x00\x00h\x00e\x00l\x00l\x00o\x00\x00\x00'
            b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
        ]
        crc1 = _exfat_entry_set_crc(entries)
        crc2 = _exfat_entry_set_crc(entries)
        self.assertEqual(crc1, crc2)

    def test_different_entries_different_crc(self):
        e1 = b'\x85\x02\x00\x00\x20' + b'\x00' * 27
        e2 = b'\x85\x02\x00\x00\x21' + b'\x00' * 27
        crc_a = _exfat_entry_set_crc([e1])
        crc_b = _exfat_entry_set_crc([e2])
        self.assertNotEqual(crc_a, crc_b)


class TestWriteThenReadTimestamp(unittest.TestCase):
    """Write timestamps via ExfatRawIO + _exfat_encode_time, read back."""

    def setUp(self):
        self.img = _temp_img()
        self.t0 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        self.t1 = datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        self.boot = create_minimal_exfat_image(str(self.img), files=[
            ('test.txt', b'data', self.t0, self.t1),
        ])
        self.io = ExfatRawIO()
        self.fs = ExfatRawFilesystem(self.io)

    def test_rewrite_btime_and_readback(self):
        result = self.fs.find_in_dir(self.boot, str(self.img),
                                     self.boot['root_cluster'], 'test.txt')
        chain, ci, off_in_cl, sc, entries = result

        new_btime = datetime(2025, 12, 25, 10, 30, 45, 120000, tzinfo=timezone.utc)
        dw_b, tw_b, ms_b = _exfat_encode_time(new_btime)
        dw_m, tw_m, ms_m = _exfat_encode_time(self.t1)

        entry = bytearray(entries[0])
        struct.pack_into('<H', entry, 0x08, tw_m)
        struct.pack_into('<H', entry, 0x0A, dw_m)
        entry[0x14] = ms_m
        struct.pack_into('<H', entry, 0x0C, tw_b)
        struct.pack_into('<H', entry, 0x0E, dw_b)
        entry[0x16] = ms_b

        modified_entries = [bytes(entry)] + list(entries[1:])
        crc = _exfat_entry_set_crc(modified_entries)
        struct.pack_into('<H', entry, 2, crc)
        modified_entries[0] = bytes(entry)

        cluster_data = self.fs.read_clusters(self.boot, str(self.img), [chain[ci]])[0]
        cluster_buf = bytearray(cluster_data)
        off = off_in_cl
        for e in modified_entries:
            cluster_buf[off:off + 32] = e
            off += 32
        self.fs.write_clusters(self.boot, str(self.img), [chain[ci]], [bytes(cluster_buf)])

        result2 = self.fs.find_in_dir(self.boot, str(self.img),
                                      self.boot['root_cluster'], 'test.txt')
        decoded = decode_entry_timestamps(result2[4][0])
        self.assertEqual(decoded['btime'], new_btime)
        self.assertEqual(decoded['mtime'], self.t1)


if __name__ == '__main__':
    unittest.main()
