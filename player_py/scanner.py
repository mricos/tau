"""MediaScanner: flat directory scan for media files with metadata."""

from dataclasses import dataclass, field
from pathlib import Path


MEDIA_EXTENSIONS = {'.webm', '.mp3', '.mp4', '.aac', '.wav', '.ogg', '.flac'}


@dataclass
class MediaFile:
    path: Path
    name: str
    extension: str
    # Metadata (populated at scan time via metadata.py)
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    track_num: int = 0
    year: int = 0
    file_size: int = 0
    _duration: float | None = field(default=None, repr=False)
    # Vox annotation link
    vox_id: str = ""
    vox_voice: str = ""
    vox_flags: str = ""  # P=phonemes S=spans R=rms O=onsets V=vad

    @classmethod
    def from_path(cls, p: Path) -> 'MediaFile':
        mf = cls(
            path=p,
            name=p.name,
            extension=p.suffix.lower(),
        )
        # Vox detection (filesystem-only, fast)
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
            from player_py.metadata import probe_duration
            self._duration = probe_duration(self.path)
        return self._duration

    def apply_meta(self, meta: 'player_py.metadata.TrackMeta'):
        """Stamp metadata from TrackMeta onto this file."""
        self.title = meta.title
        self.artist = meta.artist
        self.album = meta.album
        self.genre = meta.genre
        self.track_num = meta.track_num
        self.year = meta.year
        self.file_size = meta.file_size
        if meta.duration > 0:
            self._duration = meta.duration
        if meta.vox_id:
            self.vox_id = meta.vox_id
            self.vox_voice = meta.vox_voice
            self.vox_flags = meta.flags


def scan_directory(directory: Path) -> list[MediaFile]:
    """Scan a single directory (non-recursive) for media files, sorted by name.

    Loads cached metadata from tau_index.tsv if present, otherwise
    extracts metadata and writes the index for next time.
    """
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        return []

    files = []
    for p in sorted(directory.iterdir()):
        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS:
            files.append(MediaFile.from_path(p))

    if not files:
        return files

    # Load or build metadata index
    from player_py.metadata import load_index, extract_metadata, save_index

    index_path = directory / "tau_index.tsv"
    cached = load_index(index_path)

    metas = {}
    dirty = False
    for mf in files:
        key = str(mf.path)
        if key in cached:
            meta = cached[key]
        else:
            meta = extract_metadata(mf.path)
            dirty = True
        metas[key] = meta
        mf.apply_meta(meta)

    if dirty:
        save_index(files, metas, index_path)

    return files
