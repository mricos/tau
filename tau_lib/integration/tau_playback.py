"""
Tau multitrack audio — pure socket client.

Process management (start/stop engine) lives in engine.py.
This module is only responsible for sending commands over the socket.

Usage:
    from tau_lib.integration.engine import connect_engine
    result = connect_engine()
    if result.ok:
        result.engine.load_track(1, Path("audio.wav"))
        result.engine.play_track(1)
"""

import os
import socket
from pathlib import Path
from typing import Dict


class TauMultitrack:
    """Socket client for tau-engine. Does not manage engine lifecycle."""

    def __init__(self, socket_path: str | None = None, auto_start: bool = False):
        if socket_path is None:
            socket_path = os.environ.get(
                "TAU_SOCKET",
                str(Path.home() / "tau" / "runtime" / "tau.sock"),
            )
        self.socket_path = Path(socket_path)
        self.loaded_tracks: Dict[int, Path] = {}

        # Legacy: callers passing auto_start=True should use connect_engine()
        if auto_start and not self.check_connection():
            from tau_lib.integration.engine import connect_engine
            result = connect_engine(auto_start=True)
            if result.ok:
                self.socket_path = result.engine.socket_path

    def _send_command(self, cmd: str) -> str:
        if not self.socket_path.exists():
            raise ConnectionError(f"Tau socket not found: {self.socket_path}")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        client_path = f"/tmp/tau-client-{os.getpid()}.sock"

        try:
            sock.bind(client_path)
            sock.sendto(cmd.encode(), str(self.socket_path))
            sock.settimeout(0.3)
            response, _ = sock.recvfrom(4096)
            return response.decode().strip()
        except socket.timeout:
            raise ConnectionError(f"Tau command timed out: {cmd}")
        finally:
            sock.close()
            Path(client_path).unlink(missing_ok=True)

    # ── Track/Sample ──

    def load_track(self, track_id: int, audio_path: Path) -> bool:
        audio_path = audio_path.expanduser().resolve()
        if not audio_path.exists():
            return False
        result = self._send_command(f"SAMPLE {track_id} LOAD {audio_path}")
        if result.startswith("OK"):
            self.loaded_tracks[track_id] = audio_path
            return True
        return False

    def play_track(self, track_id: int) -> bool:
        return self._send_command(f"SAMPLE {track_id} TRIG").startswith("OK")

    def stop_track(self, track_id: int) -> bool:
        return self._send_command(f"SAMPLE {track_id} STOP").startswith("OK")

    # ── Seeking & Looping ──

    def seek(self, track_id: int, time_seconds: float) -> bool:
        return self._send_command(f"SAMPLE {track_id} SEEK {time_seconds:.3f}").startswith("OK")

    def set_loop(self, track_id: int, loop: bool) -> bool:
        return self._send_command(f"SAMPLE {track_id} LOOP {1 if loop else 0}").startswith("OK")

    # ── Track Controls ──

    def set_track_gain(self, track_id: int, gain: float) -> bool:
        return self._send_command(f"SAMPLE {track_id} GAIN {gain:.3f}").startswith("OK")

    def assign_track_channel(self, track_id: int, channel: int) -> bool:
        return self._send_command(f"SAMPLE {track_id} CHAN {channel}").startswith("OK")

    # ── Channel/Bus Control ──

    def set_channel_gain(self, channel: int, gain: float) -> bool:
        return self._send_command(f"CH {channel} GAIN {gain:.3f}").startswith("OK")

    def set_channel_pan(self, channel: int, pan: float) -> bool:
        return self._send_command(f"CH {channel} PAN {pan:.3f}").startswith("OK")

    # ── Master Control ──

    def set_master_gain(self, gain: float) -> bool:
        return self._send_command(f"MASTER {gain:.3f}").startswith("OK")

    # ── Bulk Operations ──

    def play_all(self) -> None:
        for track_id in self.loaded_tracks:
            self.play_track(track_id)

    def stop_all(self) -> None:
        for track_id in self.loaded_tracks:
            self.stop_track(track_id)

    def seek_all(self, time_seconds: float) -> None:
        for track_id in self.loaded_tracks:
            self.seek(track_id, time_seconds)

    # ── Status ──

    def check_connection(self) -> bool:
        try:
            return self._send_command("STATUS").startswith("OK")
        except ConnectionError:
            return False
