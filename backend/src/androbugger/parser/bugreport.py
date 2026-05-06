"""Bugreport zip splitter and section router."""
import re
import zipfile
from pathlib import Path

_SECTION_RE = re.compile(r"^------\s+(.+?)\s*------\s*$", re.MULTILINE)


def unzip(zip_path: Path) -> Path:
    extracted = zip_path.parent / zip_path.stem
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extracted)
    return extracted


def identify_main_file(extracted_path: Path) -> Path | None:
    for f in extracted_path.rglob("bugreport-*.txt"):
        return f
    for f in extracted_path.rglob("bugreport.txt"):
        return f
    return None


def identify_anr_files(extracted_path: Path) -> list[Path]:
    anr_dir = extracted_path / "FS" / "data" / "anr"
    if not anr_dir.exists():
        return []
    return sorted(anr_dir.rglob("*.txt"))


def identify_tombstone_files(extracted_path: Path) -> list[Path]:
    tombstone_dir = extracted_path / "FS" / "data" / "tombstones"
    if not tombstone_dir.exists():
        return []
    return sorted(tombstone_dir.rglob("tombstone_*"))


def split_sections(main_file_path: Path) -> dict[str, str]:
    """Split bugreport into named sections; returns {section_name: text}."""
    text = main_file_path.read_text(errors="replace")
    sections: dict[str, str] = {}

    matches = list(_SECTION_RE.finditer(text))
    if not matches:
        sections["FULL"] = text
        return sections

    for i, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[name] = text[start:end].strip()

    return sections
