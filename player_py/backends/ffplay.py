"""Ffplay backend — subprocess-based playback for any format ffmpeg supports."""

import subprocess
from pathlib import Path


class FfplayBackend:
    name = "ffplay"

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._path: Path | None = None
        self._volume: int = 80

    def load(self, path: Path) -> bool:
        self._path = path
        return True  # ffplay loads on play

    def play(self) -> bool:
        return self._start(0.0)

    def _start(self, start_pos: float = 0.0) -> bool:
        if self._path is None:
            return False
        self._kill()
        cmd = [
            'ffplay', '-nodisp', '-autoexit',
            '-loglevel', 'quiet',
            '-volume', str(self._volume),
        ]
        if start_pos > 0.1:
            cmd += ['-ss', f'{start_pos:.2f}']
        cmd.append(str(self._path))
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True

    def _kill(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    def pause(self) -> None:
        self._kill()

    def stop(self) -> None:
        self._kill()

    def seek(self, pos: float) -> None:
        self._start(pos)

    def set_volume(self, vol: float) -> None:
        self._volume = max(0, min(100, int(vol * 100)))

    def poll_ended(self) -> bool:
        if self._proc and self._proc.poll() is not None:
            self._proc = None
            return True
        return False

    def cleanup(self) -> None:
        self._kill()


def ffplay_available() -> bool:
    try:
        r = subprocess.run(['ffplay', '-version'], capture_output=True, timeout=2)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
