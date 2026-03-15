"""PlayerTransport: audio playback via tau-engine with ffplay fallback per-track."""

import subprocess
import time
import wave
from pathlib import Path

_TRACK_SLOT = 1

# Formats miniaudio decodes natively
_TAU_FORMATS = {'.wav', '.mp3', '.flac', '.ogg'}


class PlayerTransport:
    def __init__(self):
        self._playing: bool = False
        self._paused: bool = False
        self._position: float = 0.0
        self._duration: float = 0.0
        self._last_time: float = 0.0
        self._loaded_path: Path | None = None
        self._volume: float = 0.8
        self._engine = None
        self._has_engine: bool = False
        self._has_ffplay: bool = False
        self._ffplay_proc: subprocess.Popen | None = None
        self._error: str = ""
        # Per-track: which backend is active for the current track
        self._active: str = "none"  # "tau", "ffplay", "none"

        self._init_backends()

    def _init_backends(self):
        """Discover available backends (both can coexist)."""
        try:
            from tau_lib.integration.engine import connect_engine
            result = connect_engine(auto_start=True)
            if result.ok:
                self._engine = result.engine
                self._has_engine = True
        except Exception:
            pass

        try:
            r = subprocess.run(['ffplay', '-version'], capture_output=True, timeout=2)
            self._has_ffplay = r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if not self._has_engine and not self._has_ffplay:
            self._error = "No audio backend available"

    def _pick_backend(self, path: Path) -> str:
        """Choose backend for a given file."""
        ext = path.suffix.lower()
        if ext in _TAU_FORMATS and self._has_engine:
            return "tau"
        if self._has_ffplay:
            return "ffplay"
        if self._has_engine:
            return "tau"  # let it try and fail visibly
        return "none"

    def load(self, path: Path) -> bool:
        self.stop()
        self._loaded_path = path
        self._position = 0.0
        self._duration = _get_duration(path)
        self._active = self._pick_backend(path)

        if self._active == "tau":
            try:
                ok = self._engine.load_track(_TRACK_SLOT, path)
                if not ok:
                    # Engine rejected it — try ffplay
                    if self._has_ffplay:
                        self._active = "ffplay"
                        return True
                    self._error = "tau-engine: unsupported format"
                    self._active = "none"
                    return False
                return True
            except Exception:
                if self._has_ffplay:
                    self._active = "ffplay"
                    return True
                self._error = "tau-engine: load failed"
                self._active = "none"
                return False

        return self._active != "none"

    def play(self) -> bool:
        if self._loaded_path is None or self._active == "none":
            return False
        if self._playing:
            return True

        self._playing = True
        self._paused = False
        self._last_time = time.monotonic()

        if self._active == "tau":
            try:
                self._engine.play_track(_TRACK_SLOT)
            except Exception:
                self._error = "tau-engine: play failed"
        elif self._active == "ffplay":
            self._start_ffplay(self._position)

        return True

    def _start_ffplay(self, start_pos: float = 0.0):
        self._kill_ffplay()
        cmd = [
            'ffplay', '-nodisp', '-autoexit',
            '-loglevel', 'quiet',
            '-volume', str(int(self._volume * 100)),
        ]
        if start_pos > 0.1:
            cmd += ['-ss', f'{start_pos:.2f}']
        cmd.append(str(self._loaded_path))
        self._ffplay_proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _kill_ffplay(self):
        if self._ffplay_proc and self._ffplay_proc.poll() is None:
            self._ffplay_proc.terminate()
            try:
                self._ffplay_proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._ffplay_proc.kill()
        self._ffplay_proc = None

    def pause(self):
        if not self._playing:
            return
        self._playing = False
        self._paused = True

        if self._active == "tau":
            try:
                self._engine.stop_track(_TRACK_SLOT)
            except Exception:
                pass
        elif self._active == "ffplay":
            self._kill_ffplay()

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        self._playing = False
        self._paused = False
        self._position = 0.0

        if self._active == "tau":
            try:
                self._engine.stop_track(_TRACK_SLOT)
                self._engine.seek(_TRACK_SLOT, 0.0)
            except Exception:
                pass
        elif self._active == "ffplay":
            self._kill_ffplay()

    def seek(self, pos: float):
        if self._duration > 0:
            pos = max(0.0, min(pos, self._duration))
        else:
            pos = max(0.0, pos)
        self._position = pos
        self._last_time = time.monotonic()

        if not self._playing:
            return
        if self._active == "tau":
            try:
                self._engine.seek(_TRACK_SLOT, pos)
            except Exception:
                pass
        elif self._active == "ffplay":
            self._start_ffplay(pos)

    def seek_relative(self, delta: float):
        self.seek(self._position + delta)

    def set_volume(self, vol: float):
        self._volume = max(0.0, min(1.0, vol))
        if self._active == "tau":
            try:
                self._engine.set_track_gain(_TRACK_SLOT, self._volume)
            except Exception:
                pass

    def update(self) -> bool:
        """Advance wall-clock position. Returns True if track ended."""
        if not self._playing:
            return False

        if self._active == "ffplay" and self._ffplay_proc:
            if self._ffplay_proc.poll() is not None:
                self._playing = False
                self._ffplay_proc = None
                if self._duration > 0:
                    self._position = self._duration
                return True

        now = time.monotonic()
        dt = now - self._last_time
        self._last_time = now
        self._position += dt

        if self._duration > 0 and self._position >= self._duration:
            self._playing = False
            self._position = self._duration
            if self._active == "ffplay":
                self._kill_ffplay()
            return True
        return False

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def position(self) -> float:
        return self._position

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def progress(self) -> float:
        if self._duration <= 0:
            return 0.0
        return min(1.0, self._position / self._duration)

    @property
    def volume(self) -> float:
        return self._volume

    @property
    def has_track(self) -> bool:
        return self._loaded_path is not None

    @property
    def backend(self) -> str:
        return self._active

    @property
    def error(self) -> str:
        return self._error

    def cleanup(self):
        self._kill_ffplay()
        if self._engine:
            try:
                from tau_lib.integration.engine import _cleanup
                _cleanup()
            except Exception:
                pass


def _get_duration(path: Path) -> float:
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
