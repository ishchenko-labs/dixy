# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.0.0] - 2026-11-26

First public release, on PyPI under the MIT license. The changes below compare it with 1.0.0,
which was published only privately.

### Added

- Support Python 3.12 and 3.13, not only 3.14
- Ship a `py.typed` marker, so type checkers read dixy's type hints

### Changed

- License dixy under MIT
- Publish to PyPI instead of a private package index

### Removed

- Remove the `sanepy` dependency: dixy has no runtime dependencies
- Remove the `dixy.testing` sample classes from the package

[Unreleased]: https://github.com/ishchenko-labs/dixy/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/ishchenko-labs/dixy/releases/tag/v2.0.0
