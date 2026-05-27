# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-05-27

### Added
- Nix flake packaging for reproducible builds and development shells
- Direct file I/O access with automatic fallback (direct open → sudo dd → error) for image files
- Pure-Python exFAT image builder in `tests/helpers.py` for sandbox-safe testing
- 16 sandbox-safe tests covering boot parsing, FAT I/O, directory traversal, timestamp round-trips, CRC, and write-readback
- `IOStrategy` ABC with three implementations: `DirectIOStrategy`, `BackingFileStrategy`, `DDStrategy`
- CI coverage check with 80% threshold

### Changed
- Updated README with documentation for direct image file I/O and 3-tier fallback behavior
- Refactored `ExfatRawIO` to delegate I/O to a pluggable strategy chain

## [0.1.2] - 2026-05-27

### Fixed
- Correct author name and email in package metadata (Michael Banucu)

## [Unreleased]

### Changed
- Stricter datetime validation — timezone-aware datetimes are now required; naive datetimes are rejected

## [0.1.0] - 2025-01-03

### Added
- Initial release

[0.1.2]: https://github.com/MBanucu/exfat-raw/releases/tag/v0.1.2
[0.1.1]: https://github.com/MBanucu/exfat-raw/releases/tag/v0.1.1
[0.1.0]: https://github.com/MBanucu/exfat-raw/releases/tag/v0.1.0
