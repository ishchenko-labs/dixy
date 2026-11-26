import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def quick_start() -> str:
    section = (ROOT / "README.md").read_text().split("## Quick start", 1)[1]
    match = re.search(r"```python\n(.*?)```", section, re.DOTALL)
    assert match is not None
    return match.group(1)


def test_quick_start_is_the_tested_quickstart_example() -> None:
    assert quick_start() == (ROOT / "examples" / "quickstart.py").read_text()
