# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-06-13

### Added
- Validate boot sector fields on volume open: reject non-exFAT volumes, enforce valid bytes-per-sector (9–12) and cluster size bounds, and verify the exFAT version field

### Changed
- `BackingFileStrategy` (loop-device backing file I/O) now works on macOS, giving macOS the same 3-tier I/O fallback chain as Linux

### Removed
- Nix flake `coverage-html` app and `coverage` dev shell dependency — coverage is now viewed via Codecov

## [0.2.0] - 2026-06-12

### Added
- macOS support with platform-adaptive device/mount resolution and POSIX-compatible I/O strategies
- Python 3.14 to supported versions
- Nix flake `lib.sitePackages` helper for downstream flake consumers
- Nix flake `coverage-html` app for generating HTML coverage reports

### Changed
- Stricter datetime validation — timezone-aware datetimes are now required; naive datetimes are rejected
- Debug/progress output migrated from `print()` to standard `logging` module, gated by `EXFAT_RAW_VERBOSE=1`

## [0.1.2] - 2026-05-27

### Fixed
- Correct author name and email in package metadata (Michael Banucu)

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

## [0.1.0] - 2025-01-03

### Added
- Initial release

[Unreleased]: https://github.com/MBanucu/exfat-raw/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/MBanucu/exfat-raw/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/MBanucu/exfat-raw/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/MBanucu/exfat-raw/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/MBanucu/exfat-raw/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/MBanucu/exfat-raw/releases/tag/v0.1.0
