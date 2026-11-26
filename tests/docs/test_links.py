import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PAGES = sorted([*ROOT.glob("*.md"), *(ROOT / "docs").glob("*.md")])

LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#+\s+(.*)$", re.MULTILINE)
FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)


def anchors_of(page: Path) -> set[str]:
    """Return the anchors GitHub gives a page's headings."""
    text = FENCED_BLOCK.sub("", page.read_text())
    return {
        re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        for heading in HEADING.findall(text)
    }


def local_links() -> list[tuple[Path, str]]:
    return [
        (page, target)
        for page in PAGES
        for target in LINK.findall(FENCED_BLOCK.sub("", page.read_text()))
        if "://" not in target and not target.startswith("mailto:")
    ]


@pytest.mark.parametrize(
    ("page", "target"),
    local_links(),
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_local_link_leads_somewhere(page: Path, target: str) -> None:
    path, _, anchor = target.partition("#")
    destination = (page.parent / path).resolve() if path else page

    assert destination.exists(), f"{page.name} links to missing {path}"
    if anchor:
        assert anchor in anchors_of(destination), (
            f"{page.name} links to missing #{anchor}"
        )
