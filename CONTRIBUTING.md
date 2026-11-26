# Contributing

Thanks for helping with dixy. Bug reports, fixes, and documentation improvements are all welcome.
For a new feature, open an issue first so we can agree on the API before you write the code.

## Development setup

You need [uv](https://docs.astral.sh/uv/). [mise](https://mise.jdx.dev/) installs the pinned
version from `mise.toml`, but any recent uv works.

```bash
make install   # create .venv from uv.lock
make verify    # lint, types, and tests: exactly what CI runs
make format    # fix formatting and autofixable lint issues
```

`make` lists every command. Development uses the Python version in `.python-version`; CI also runs
the tests on every older version that `requires-python` allows.

## Pull requests

- Keep a pull request to one change, with tests that cover it. `make verify` must pass.
- Every public name is exported from `src/dixy/__init__.py` and covered by tests.
- dixy has no runtime dependencies, and a change must not add one.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` when the change is visible to users.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`,
  `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.

## Releases

The maintainer releases by bumping `version` in `pyproject.toml` on `main`. The Release workflow
then tags the version, publishes it to PyPI, and creates the GitHub release from the changelog.
