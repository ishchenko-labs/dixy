# CLAUDE.md

`dixy`: a small, mypy-friendly dependency injection container.
Part of the `ishchenko-labs` libraries. Public, MIT-licensed, published on PyPI. English only.

## Commands

`make` lists them. `make verify` is exactly what CI runs and must pass before every push.

## Rules

- Every public name is exported from the package's `__init__.py` and covered by tests.
- No runtime dependencies: anything dixy needs must come from the standard library.
- Supports every Python from `requires-python` up: CI runs the tests on each. Code must not use
  syntax or stdlib APIs newer than the oldest one (ruff and mypy target it).
- The README quick start is a test (`tests/docs/test_readme.py`): keep it runnable on its own.
- Releasing: bump `version` in `pyproject.toml` (semver: major for a breaking change, minor for a
  new feature, patch otherwise). When the bump lands on `main`, the Release workflow tags
  `v<version>`, publishes the wheel and sdist to PyPI through Trusted Publishing (GitHub
  environment `pypi`, no token) and creates the GitHub release from the changelog entry; don't tag
  or upload by hand. Add a `CHANGELOG.md` entry with every release.
- No comments that restate what code or config does; a comment only explains a why the code can't
  show.
- Commits are one-line conventional commits (`feat:`, `fix:`, `docs:`, `chore:`), no mention of
  Claude or AI; a `Co-Authored-By` trailer is fine.
- A cloud session commits, pushes its `claude/…` branch and opens a PR without asking. Merging stays
  with the owner.
