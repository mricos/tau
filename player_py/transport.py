"""PlayerTransport: thin orchestrator over tau-engine backend."""

import time
from pathlib import Path

from player_py.backends.tau import TauBackend


class PlayerTransport:
    def __init__(self):
        self._playing: bool = False
        self._position: float = 0.0
        self._duration: float = 0.0
        self._last_time: float = 0.0
        self._loaded_path: Path | None = None
        self._volume: float = 0.8
        self._backend: TauBackend | None = None
        self._error: str = ""

        self._init_backend()

    def _init_backend(self):
        try:
            from tau_lib.integration.engine import connect_engine
            result = connect_engine(auto_start=True)
            if result.ok:
                self._backend = TauBackend(result.engine)
                return
            self._error = result.error
        except Exception as e:
            self._error = str(e)

    def load(self, path: Path) -> bool:
        self.stop()
        self._loaded_path = path
        self._position = 0.0
        self._duration = 0.0

        if self._backend is None:
            return False

        from player_py.metadata import probe_duration
        self._duration = probe_duration(path)

        ok = self._backend.load(path)
        if not ok:
            self._error = f"Failed to load: {path.name}"
        return ok

    def play(self) -> bool:
        if self._backend is None or self._loaded_path is None:
            return False
        if self._playing:
            return True
        self._playing = True
        self._last_time = time.monotonic()
        self._backend.play()
        return True

    def pause(self):
        if not self._playing:
            return
        self._playing = False
        if self._backend:
            self._backend.pause()

    def toggle(self):
        if self._playing:
            self.pause()
        else:
            self.play()

    def stop(self):
        self._playing = False
        self._position = 0.0
        if self._backend:
            self._backend.stop()

    def seek(self, pos: float):
        if self._duration > 0:
            pos = max(0.0, min(pos, self._duration))
        else:
            pos = max(0.0, pos)
        self._position = pos
        self._last_time = time.monotonic()
        if self._playing and self._backend:
            self._backend.seek(pos)

    def seek_relative(self, delta: float):
        self.seek(self._position + delta)

    def set_volume(self, vol: float):
        self._volume = max(0.0, min(1.0, vol))
        if self._backend:
            self._backend.set_volume(self._volume)

    def update(self) -> bool:
        """Advance wall-clock position. Returns True if track ended."""
        if not self._playing:
            return False

        if self._backend and self._backend.poll_ended():
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
            if self._backend:
                self._backend.stop()
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
        return "tau" if self._backend else "none"

    @property
    def error(self) -> str:
        return self._error

    def cleanup(self):
        if self._backend:
            self._backend.cleanup()
