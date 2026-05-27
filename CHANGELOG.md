# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Nix flake packaging for reproducible builds and development shells
- Direct file I/O access with automatic fallback (direct open → sudo dd → error) for image files

### Changed
- Updated README with documentation for direct image file I/O and 3-tier fallback behavior

## [0.1.0] - 2025-01-03

### Added
- Initial release
