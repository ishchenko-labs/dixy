import re
import subprocess
import sys
from pathlib import Path

README = Path(__file__).parents[2] / "README.md"


def quick_start() -> str:
    section = README.read_text().split("## Quick start", 1)[1]
    match = re.search(r"```python\n(.*?)```", section, re.DOTALL)
    assert match is not None
    return match.group(1)


def test_quick_start_runs_and_greets(tmp_path: Path) -> None:
    script = tmp_path / "quick_start.py"
    script.write_text(quick_start())

    result = subprocess.run(  # noqa: S603 - runs this repository's own README code
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert result.stdout == "Hello, Ada!\n"
