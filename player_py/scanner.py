"""MediaScanner: recursive directory scan for media files."""

import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path


MEDIA_EXTENSIONS = {'.webm', '.mp3', '.mp4', '.aac', '.wav', '.ogg', '.flac'}


@dataclass
class MediaFile:
    path: Path
    name: str
    extension: str
    parent_dir: str
    _duration: float | None = field(default=None, repr=False)
    # Metadata (populated by metadata.py)
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    track_num: int = 0
    year: int = 0
    file_size: int = 0
    # Vox annotation link
    vox_id: str = ""
    vox_voice: str = ""
    vox_flags: str = ""  # P=phonemes S=spans R=rms O=onsets V=vad

    @classmethod
    def from_path(cls, p: Path, base: Path) -> 'MediaFile':
        try:
            rel_parent = str(p.parent.relative_to(base))
        except ValueError:
            rel_parent = str(p.parent)
        mf = cls(
            path=p,
            name=p.name,
            extension=p.suffix.lower(),
            parent_dir=rel_parent if rel_parent != '.' else '',
        )
        # Auto-detect vox bundle membership
        from player_py.metadata import detect_vox, probe_vox_flags
        vox_id, vox_voice = detect_vox(p)
        if vox_id:
            mf.vox_id = vox_id
            mf.vox_voice = vox_voice
            mf.vox_flags = probe_vox_flags(p, vox_id, vox_voice)
        return mf

    @property
    def display_label(self) -> str:
        """Best available label: title > name."""
        if self.title:
            if self.artist:
                return f"{self.artist} - {self.title}"
            return self.title
        return self.name

    @property
    def duration(self) -> float:
        if self._duration is None:
            self._duration = probe_duration(self.path)
        return self._duration


def probe_duration(path: Path) -> float:
    """Get audio duration. Tries wave module, then ffprobe, else 0.0."""
    if path.suffix.lower() == '.wav':
        try:
            with wave.open(str(path), 'rb') as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            pass

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    return 0.0


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
