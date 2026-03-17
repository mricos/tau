"""PlayerTransport: thin orchestrator over pluggable audio backends."""

import time
from pathlib import Path

from player_py.backends.tau import TauBackend, TAU_FORMATS
from player_py.backends.ffplay import FfplayBackend, ffplay_available


class PlayerTransport:
    def __init__(self):
        self._playing: bool = False
        self._position: float = 0.0
        self._duration: float = 0.0
        self._last_time: float = 0.0
        self._loaded_path: Path | None = None
        self._volume: float = 0.8

        self._tau: TauBackend | None = None
        self._ffplay: FfplayBackend | None = None
        self._active: TauBackend | FfplayBackend | None = None
        self._error: str = ""

        self._init_backends()

    def _init_backends(self):
        try:
            from tau_lib.integration.engine import connect_engine
            result = connect_engine(auto_start=True)
            if result.ok:
                self._tau = TauBackend(result.engine)
        except Exception:
            pass

        if ffplay_available():
            self._ffplay = FfplayBackend()

        if not self._tau and not self._ffplay:
            self._error = "No audio backend available"

    def _pick_backend(self, path: Path) -> TauBackend | FfplayBackend | None:
        ext = path.suffix.lower()
        if ext in TAU_FORMATS and self._tau:
            return self._tau
        if self._ffplay:
            return self._ffplay
        if self._tau:
            return self._tau
        return None

    def load(self, path: Path) -> bool:
        self.stop()
        self._loaded_path = path
        self._position = 0.0
        self._duration = 0.0
        self._active = self._pick_backend(path)

        if self._active is None:
            return False

        # Probe duration via MediaFile (lazy, cached)
        from player_py.scanner import probe_duration
        self._duration = probe_duration(path)

        ok = self._active.load(path)
        if not ok and self._active is self._tau and self._ffplay:
            self._active = self._ffplay
            ok = self._active.load(path)
        if not ok:
            self._active = None
        return ok

    def play(self) -> bool:
        if self._active is None or self._loaded_path is None:
            return False
        if self._playing:
            return True
        self._playing = True
        self._last_time = time.monotonic()
        self._active.play()
        return True

    def pause(self):
        if not self._playing:
            return
        self._playing = False
        if self._active:
            self._active.pause()

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        self._playing = False
        self._position = 0.0
        if self._active:
            self._active.stop()

    def seek(self, pos: float):
        if self._duration > 0:
            pos = max(0.0, min(pos, self._duration))
        else:
            pos = max(0.0, pos)
        self._position = pos
        self._last_time = time.monotonic()
        if self._playing and self._active:
            self._active.seek(pos)

    def seek_relative(self, delta: float):
        self.seek(self._position + delta)

    def set_volume(self, vol: float):
        self._volume = max(0.0, min(1.0, vol))
        if self._active:
            self._active.set_volume(self._volume)

    def update(self) -> bool:
        """Advance wall-clock position. Returns True if track ended."""
        if not self._playing:
            return False

        if self._active and self._active.poll_ended():
            self._playing = False
            if self._duration > 0:
                self._position = self._duration
            return True

        now = time.monotonic()
        self._position += now - self._last_time
        self._last_time = now

        if self._duration > 0 and self._position >= self._duration:
            self._playing = False
            self._position = self._duration
            if self._active:
                self._active.stop()
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
        return self._active.name if self._active else "none"

    @property
    def error(self) -> str:
        return self._error

    def cleanup(self):
        if self._tau:
            self._tau.cleanup()
        if self._ffplay:
            self._ffplay.cleanup()
