"""Miscellaneous unit tests — pure functions and trivial coverage gaps.

No loop device or sudo required.
"""

import importlib
import logging
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import exfat_raw

from exfat_raw._backing_file import BackingFileStrategy
from exfat_raw._io import ExfatRawIO
from exfat_raw._pure import _require_aware


class TestRequireAware(unittest.TestCase):
    """_require_aware must raise ValueError for naive datetimes."""

    def test_naive_datetime_raises(self):
        with self.assertRaises(ValueError):
            _require_aware(datetime(2026, 1, 1, 0, 0, 0))

    def test_aware_datetime_passes(self):
        try:
            _require_aware(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        except ValueError:
            self.fail("_require_aware raised ValueError for aware datetime")


class TestClearCache(unittest.TestCase):
    """clear_cache methods must not crash (even with empty cache)."""

    def test_backing_file_strategy_clear_cache(self):
        s = BackingFileStrategy()
        s.clear_cache()
        s.clear_cache("/dev/loop0")

    def test_exfat_raw_io_clear_cache(self):
        io = ExfatRawIO()
        io.clear_cache()
        io.clear_cache("/dev/loop0")


class TestLoggingConfig(unittest.TestCase):
    """EXFAT_RAW_VERBOSE=1 must call basicConfig; no-env must not."""

    def test_verbose_env_calls_basic_config(self):
        with patch.dict(os.environ, {'EXFAT_RAW_VERBOSE': '1'}):
            with patch('logging.basicConfig') as mock_basic_config:
                importlib.reload(exfat_raw)
        mock_basic_config.assert_called_once_with(
            level=logging.INFO, format='%(message)s')

    def test_no_env_does_not_call_basic_config(self):
        with patch('logging.basicConfig') as mock_basic_config:
            importlib.reload(exfat_raw)
        mock_basic_config.assert_not_called()


if __name__ == '__main__':
    unittest.main()
