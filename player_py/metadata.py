"""Metadata extraction and vox annotation detection.

Extends MediaFile with ID3 tags (via mutagen) and vox bundle awareness.
Writes/reads tau_index.tsv for C-portable indexing.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from player_py.scanner import MediaFile, MEDIA_EXTENSIONS

# Pattern: {digits}.vox.audio.{voice}.mp3
_VOX_PATTERN = re.compile(r'^(\d{9,10})\.vox\.audio\.([a-z]+)\.(mp3|wav|flac)$')

# Annotation flag characters
_FLAG_MAP = {
    'phonemes': 'P',
    'spans': 'S',
    'rms': 'R',
    'onsets': 'O',
    'vad': 'V',
}


@dataclass
class TrackMeta:
    """Metadata fields that extend MediaFile."""
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    track_num: int = 0
    year: int = 0
    duration: float = 0.0
    file_size: int = 0
    # vox annotation link
    vox_id: str = ""
    vox_voice: str = ""
    flags: str = ""  # e.g. "PSROV"


def detect_vox(path: Path) -> tuple[str, str]:
    """If path matches vox naming, return (vox_id, voice). Else ("", "")."""
    m = _VOX_PATTERN.match(path.name)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def probe_vox_flags(path: Path, vox_id: str, voice: str) -> str:
    """Check which sibling annotation files exist. Returns flag string."""
    d = path.parent
    flags = ""
    if (d / f"{vox_id}.vox.phonemes.json").exists():
        flags += "P"
    if (d / f"{vox_id}.vox.spans.{voice}.json").exists():
        flags += "S"
    if (d / f"{vox_id}.vox.rms.json").exists():
        flags += "R"
    if (d / f"{vox_id}.vox.onsets.json").exists():
        flags += "O"
    if (d / f"{vox_id}.vox.vad.json").exists():
        flags += "V"
    return flags


def extract_metadata(path: Path) -> TrackMeta:
    """Extract metadata from audio file. Uses mutagen if available."""
    meta = TrackMeta()
    meta.file_size = path.stat().st_size if path.exists() else 0

    # Detect vox bundle membership
    vox_id, vox_voice = detect_vox(path)
    meta.vox_id = vox_id
    meta.vox_voice = vox_voice
    if vox_id:
        meta.flags = probe_vox_flags(path, vox_id, vox_voice)

    # Try mutagen for ID3/Vorbis tags
    try:
        from mutagen import File as MutagenFile
        m = MutagenFile(str(path), easy=True)
        if m is not None:
            meta.title = (m.get("title") or [""])[0]
            meta.artist = (m.get("artist") or [""])[0]
            meta.album = (m.get("album") or [""])[0]
            meta.genre = (m.get("genre") or [""])[0]
            meta.track_num = _parse_int(m.get("tracknumber", ["0"])[0])
            meta.year = _parse_int(m.get("date", ["0"])[0][:4])
            if m.info:
                meta.duration = m.info.length
    except ImportError:
        pass
    except Exception:
        pass

    # Duration fallback via ffprobe
    if meta.duration == 0.0:
        meta.duration = _ffprobe_duration(path)

    return meta


def _parse_int(s: str) -> int:
    try:
        return int(s.split("/")[0])
    except (ValueError, IndexError):
        return 0


def _ffprobe_duration(path: Path) -> float:
    import subprocess
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


# ── TSV Index ──


INDEX_HEADER = "# path\ttitle\tartist\talbum\tgenre\ttrack\tyear\tduration\tsize\tmtime\tvox_id\tvox_voice\tflags"


def save_index(files: list[MediaFile], metas: dict[str, TrackMeta], index_path: Path):
    """Write tau_index.tsv."""
    with open(index_path, 'w') as f:
        f.write(INDEX_HEADER + '\n')
        for mf in files:
            m = metas.get(str(mf.path), TrackMeta())
            try:
                mtime = str(int(mf.path.stat().st_mtime))
            except OSError:
                mtime = "0"
            fields = [
                str(mf.path), m.title, m.artist, m.album,
                m.genre, str(m.track_num), str(m.year),
                f"{m.duration:.1f}", str(m.file_size),
                mtime, m.vox_id, m.vox_voice, m.flags,
            ]
            f.write('\t'.join(fields) + '\n')


def load_index(index_path: Path) -> dict[str, TrackMeta]:
    """Read tau_index.tsv. Returns {path_str: TrackMeta}."""
    result = {}
    if not index_path.exists():
        return result
    with open(index_path) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.rstrip('\n').split('\t')
            if len(parts) < 13:
                continue
            result[parts[0]] = TrackMeta(
                title=parts[1], artist=parts[2], album=parts[3],
                genre=parts[4], track_num=_parse_int(parts[5]),
                year=_parse_int(parts[6]), duration=float(parts[7] or 0),
                file_size=int(parts[8] or 0),
                vox_id=parts[10], vox_voice=parts[11], flags=parts[12],
            )
    return result
