"""Tau-engine backend — sends commands over Unix socket.

For formats miniaudio can't decode natively, transcodes to WAV
via ffmpeg before loading into the engine.
"""

import atexit
import shutil
import subprocess
import tempfile
from pathlib import Path

_TRACK_SLOT = 1

# Formats miniaudio decodes natively — no transcode needed
NATIVE_FORMATS = {'.wav', '.mp3', '.flac', '.ogg'}

_tmp_dir: Path | None = None


def _get_tmp_dir() -> Path:
    """Lazy-create a temp directory for transcoded files, cleaned up on exit."""
    global _tmp_dir
    if _tmp_dir is None or not _tmp_dir.exists():
        _tmp_dir = Path(tempfile.mkdtemp(prefix="tau-player-"))
        atexit.register(lambda: shutil.rmtree(_tmp_dir, ignore_errors=True))
    return _tmp_dir


def _transcode_to_wav(src: Path) -> Path | None:
    """Transcode any file to 48kHz mono WAV via ffmpeg. Returns wav path or None."""
    dst = _get_tmp_dir() / f"{src.stem}_{hash(str(src)) & 0xFFFFFFFF:08x}.wav"
    if dst.exists():
        return dst  # already transcoded
    try:
        r = subprocess.run(
            ['ffmpeg', '-y', '-i', str(src),
             '-ac', '1', '-ar', '48000', '-f', 'wav', str(dst)],
            capture_output=True, timeout=30,
        )
        if r.returncode == 0 and dst.exists():
            return dst
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


class TauBackend:
    name = "tau"

    def __init__(self, engine):
        self._engine = engine

    def load(self, path: Path) -> bool:
        ext = path.suffix.lower()
        load_path = path

        if ext not in NATIVE_FORMATS:
            wav = _transcode_to_wav(path)
            if wav is None:
                return False
            load_path = wav

        try:
            return self._engine.load_track(_TRACK_SLOT, load_path)
        except Exception:
            return False

    def play(self) -> bool:
        try:
            return self._engine.play_track(_TRACK_SLOT)
        except Exception:
            return False

    def pause(self) -> None:
        try:
            self._engine.stop_track(_TRACK_SLOT)
        except Exception:
            pass

    def stop(self) -> None:
        try:
            self._engine.stop_track(_TRACK_SLOT)
            self._engine.seek(_TRACK_SLOT, 0.0)
        except Exception:
            pass

    def seek(self, pos: float) -> None:
        try:
            self._engine.seek(_TRACK_SLOT, pos)
        except Exception:
            pass

    def set_volume(self, vol: float) -> None:
        try:
            self._engine.set_track_gain(_TRACK_SLOT, vol)
        except Exception:
            pass

    def poll_ended(self) -> bool:
        return False  # tau-engine doesn't expose end-of-track

    def cleanup(self) -> None:
        try:
            from tau_lib.integration.engine import _cleanup
            _cleanup()
        except Exception:
            pass
