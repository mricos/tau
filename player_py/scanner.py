"""MediaScanner: recursive directory scan for media files."""

from dataclasses import dataclass
from pathlib import Path


MEDIA_EXTENSIONS = {'.webm', '.mp3', '.mp4', '.aac', '.wav', '.ogg', '.flac'}


@dataclass
class MediaFile:
    path: Path
    name: str
    extension: str
    parent_dir: str

    @classmethod
    def from_path(cls, p: Path, base: Path) -> 'MediaFile':
        try:
            rel_parent = str(p.parent.relative_to(base))
        except ValueError:
            rel_parent = str(p.parent)
        return cls(
            path=p,
            name=p.name,
            extension=p.suffix.lower(),
            parent_dir=rel_parent if rel_parent != '.' else '',
        )


def scan_directory(directory: Path) -> list[MediaFile]:
    """Recursively scan directory for media files, sorted by path."""
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        return []

    files = []
    for p in sorted(directory.rglob('*')):
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS:
            files.append(MediaFile.from_path(p, directory))
    return files


def group_by_directory(files: list[MediaFile]) -> dict[str, list[MediaFile]]:
    """Group media files by their parent directory."""
    groups: dict[str, list[MediaFile]] = {}
    for f in files:
        groups.setdefault(f.parent_dir, []).append(f)
    return groups
