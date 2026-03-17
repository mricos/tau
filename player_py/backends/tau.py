"""Tau-engine backend — sends commands over Unix socket."""

from pathlib import Path

_TRACK_SLOT = 1

# Formats miniaudio decodes natively
TAU_FORMATS = {'.wav', '.mp3', '.flac', '.ogg'}


class TauBackend:
    name = "tau"

    def __init__(self, engine):
        self._engine = engine

    def load(self, path: Path) -> bool:
        try:
            return self._engine.load_track(_TRACK_SLOT, path)
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
