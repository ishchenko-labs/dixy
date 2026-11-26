# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.1.0] - 2026-11-26

### Added

- Tell a lifespan how its scope ended: an error that ends a scope, an `@inject` call or the
  container's `with` block is passed to the lifespans being closed, so a transaction can commit or
  roll back there. A lifespan cannot suppress the error
- Add runnable examples in `examples/`, each run by the test suite, and guides in `docs/`

### Fixed

- Run every teardown when one fails, instead of stopping at the first failure. A single failure is
  raised as itself, several as one `ExceptionGroup`
- Keep the error that ended a scope or container when a teardown fails too: the teardown failure is
  logged and added to that error as a note instead of replacing it
- Validate what `setup` callbacks and hooks depend on. A missing dependency, a captive dependency or
  a cycle through one is reported by `validate` instead of failing, or hanging, on first use
- Apply the source's lifetime rules to an alias: an alias of a scoped dependency is refused outside
  a scope, and `validate` reports a missing source, a captive dependency and a cycle through an
  alias
- Accept an `@inject` accessor typed as returning `Container | None`

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

[Unreleased]: https://github.com/ishchenko-labs/dixy/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/ishchenko-labs/dixy/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/ishchenko-labs/dixy/releases/tag/v2.0.0
