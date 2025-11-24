"""
Tau multitrack audio playback integration for the tau TUI DAW.

This module provides synchronized audio playback for the DAW by communicating
with the tau-engine audio engine via Unix domain sockets.

Architecture:
    tau TUI lanes 1-8 → tau-engine samples 1-8 → tau-engine channels 0-3 → master

Usage:
    tau = TauMultitrack()
    tau.load_track(1, Path("audio.wav"))
    tau.set_loop(1, True)
    tau.play_track(1)
    tau.seek(1, 5.0)  # Seek to 5 seconds
    tau.stop_track(1)
"""

import os
import socket
import subprocess
import time
import atexit
from pathlib import Path
from typing import Optional, Dict


class TauMultitrack:
    """Direct socket communication with tau-engine for multitrack playback."""

    def __init__(self, socket_path: str = "~/tau/runtime/tau.sock", auto_start: bool = True):
        """
        Initialize tau multitrack controller.

        Args:
            socket_path: Path to tau Unix socket (default: ~/tau/runtime/tau.sock)
            auto_start: Automatically start tau-engine if not running (default: True)
        """
        self.socket_path = Path(socket_path).expanduser()
        self.loaded_tracks: Dict[int, Path] = {}  # track_id -> audio_path
        self.engine_process: Optional[subprocess.Popen] = None

        # Auto-start tau-engine if requested and not already running
        if auto_start and not self.check_connection():
            self._start_engine()

    def _start_engine(self) -> None:
        """
        Start tau-engine daemon in the background.

        Looks for tau-engine binary in:
        1. ./engine/tau-engine (relative to this file)
        2. ~/tau/engine/tau-engine (absolute path)
        """
        # Find tau-engine binary
        script_dir = Path(__file__).parent
        engine_paths = [
            script_dir / "engine" / "tau-engine",
            Path("~/tau/engine/tau-engine").expanduser()
        ]

        engine_binary = None
        for path in engine_paths:
            if path.exists():
                engine_binary = path
                break

        if not engine_binary:
            raise FileNotFoundError(
                f"tau-engine binary not found. Searched: {[str(p) for p in engine_paths]}"
            )

        # Ensure runtime directory exists
        runtime_dir = self.socket_path.parent
        runtime_dir.mkdir(parents=True, exist_ok=True)

        # Start tau-engine as background daemon
        self.engine_process = subprocess.Popen(
            [str(engine_binary)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Register cleanup handler
        atexit.register(self._cleanup_engine)

        # Wait for socket to appear (up to 2 seconds)
        for _ in range(20):
            time.sleep(0.1)
            if self.socket_path.exists():
                break

        if not self.socket_path.exists():
            raise ConnectionError("tau-engine started but socket not created")

    def _cleanup_engine(self) -> None:
        """Clean up auto-started tau-engine process."""
        if self.engine_process:
            try:
                self.engine_process.terminate()
                self.engine_process.wait(timeout=2)
            except:
                pass

    def _send_command(self, cmd: str) -> str:
        """
        Send command to tau daemon and receive response.

        Args:
            cmd: Command string (e.g., "SAMPLE 1 LOAD /path/to/audio.wav")

        Returns:
            Response string from tau (e.g., "OK SAMPLE 1 LOADED ...")

        Raises:
            ConnectionError: If tau socket not found or connection fails
        """
        if not self.socket_path.exists():
            raise ConnectionError(f"Tau socket not found: {self.socket_path}")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        client_path = f"/tmp/tau-client-{os.getpid()}.sock"

        try:
            # Bind to temporary client socket
            sock.bind(client_path)

            # Send command to tau
            sock.sendto(cmd.encode(), str(self.socket_path))

            # Receive response with timeout
            sock.settimeout(1.0)
            response, _ = sock.recvfrom(4096)
            return response.decode().strip()

        except socket.timeout:
            raise ConnectionError(f"Tau command timed out: {cmd}")
        finally:
            sock.close()
            Path(client_path).unlink(missing_ok=True)

    # === Track/Sample Management ===

    def load_track(self, track_id: int, audio_path: Path) -> bool:
        """
        Load audio file to tau sample slot.

        Args:
            track_id: Track number (1-16, typically 1-8 for lanes)
            audio_path: Path to audio file (.wav, .mp3, etc.)

        Returns:
            True if loaded successfully, False otherwise
        """
        audio_path = audio_path.expanduser().resolve()
        if not audio_path.exists():
            print(f"Audio file not found: {audio_path}")
            return False

        result = self._send_command(f"SAMPLE {track_id} LOAD {audio_path}")

        if result.startswith("OK"):
            self.loaded_tracks[track_id] = audio_path
            return True
        else:
            print(f"Failed to load: {result}")
            return False

    def play_track(self, track_id: int) -> bool:
        """
        Trigger playback of loaded sample.

        Args:
            track_id: Track number (1-16)

        Returns:
            True if triggered successfully
        """
        result = self._send_command(f"SAMPLE {track_id} TRIG")
        return result.startswith("OK")

    def stop_track(self, track_id: int) -> bool:
        """
        Stop sample playback.

        Args:
            track_id: Track number (1-16)

        Returns:
            True if stopped successfully
        """
        result = self._send_command(f"SAMPLE {track_id} STOP")
        return result.startswith("OK")

    # === Seeking & Looping ===

    def seek(self, track_id: int, time_seconds: float) -> bool:
        """
        Seek to position in sample (in seconds).

        Args:
            track_id: Track number (1-16)
            time_seconds: Target time in seconds

        Returns:
            True if seek succeeded
        """
        result = self._send_command(f"SAMPLE {track_id} SEEK {time_seconds:.3f}")
        return result.startswith("OK")

    def set_loop(self, track_id: int, loop: bool) -> bool:
        """
        Enable/disable looping for sample.

        Args:
            track_id: Track number (1-16)
            loop: True to loop, False for one-shot

        Returns:
            True if set successfully
        """
        result = self._send_command(f"SAMPLE {track_id} LOOP {1 if loop else 0}")
        return result.startswith("OK")

    # === Track Controls ===

    def set_track_gain(self, track_id: int, gain: float) -> bool:
        """
        Set track gain/volume.

        Args:
            track_id: Track number (1-16)
            gain: Gain multiplier (0.0-10.0, typically 0.0-1.0)

        Returns:
            True if set successfully
        """
        result = self._send_command(f"SAMPLE {track_id} GAIN {gain:.3f}")
        return result.startswith("OK")

    def assign_track_channel(self, track_id: int, channel: int) -> bool:
        """
        Assign track to mixer channel for submixing.

        Args:
            track_id: Track number (1-16)
            channel: Mixer channel (0-3)

        Returns:
            True if assigned successfully
        """
        result = self._send_command(f"SAMPLE {track_id} CHAN {channel}")
        return result.startswith("OK")

    # === Channel/Bus Control ===

    def set_channel_gain(self, channel: int, gain: float) -> bool:
        """
        Set mixer channel gain (for submixing).

        Args:
            channel: Channel number (1-4, maps to 0-3 internally)
            gain: Gain multiplier (0.0-10.0)

        Returns:
            True if set successfully
        """
        result = self._send_command(f"CH {channel} GAIN {gain:.3f}")
        return result.startswith("OK")

    def set_channel_pan(self, channel: int, pan: float) -> bool:
        """
        Set mixer channel pan.

        Args:
            channel: Channel number (1-4)
            pan: Pan position (-1.0=left, 0.0=center, 1.0=right)

        Returns:
            True if set successfully
        """
        result = self._send_command(f"CH {channel} PAN {pan:.3f}")
        return result.startswith("OK")

    # === Master Control ===

    def set_master_gain(self, gain: float) -> bool:
        """
        Set master output gain.

        Args:
            gain: Master gain (0.0-10.0, typically 0.0-1.0)

        Returns:
            True if set successfully
        """
        result = self._send_command(f"MASTER {gain:.3f}")
        return result.startswith("OK")

    # === Bulk Operations ===

    def play_all(self) -> None:
        """Trigger playback of all loaded tracks."""
        for track_id in self.loaded_tracks.keys():
            self.play_track(track_id)

    def stop_all(self) -> None:
        """Stop playback of all tracks."""
        for track_id in self.loaded_tracks.keys():
            self.stop_track(track_id)

    def seek_all(self, time_seconds: float) -> None:
        """Seek all tracks to the same position."""
        for track_id in self.loaded_tracks.keys():
            self.seek(track_id, time_seconds)

    # === Status ===

    def check_connection(self) -> bool:
        """
        Check if tau daemon is running and responding.

        Returns:
            True if tau is responding
        """
        try:
            result = self._send_command("STATUS")
            return result.startswith("OK")
        except ConnectionError:
            return False


# === Example Usage ===

if __name__ == "__main__":
    # Example: Load and play a track with looping and seeking
    tau = TauMultitrack()

    if not tau.check_connection():
        print("Error: tau-engine daemon not running and could not auto-start")
        print("Try starting manually: ./tau/engine/tau-engine")
        exit(1)

    print("✓ Connected to tau-engine")

    # Load audio file to track 1
    audio_file = Path("~/src/mricos/demos/tscale/audio.wav")
    if tau.load_track(1, audio_file):
        print(f"✓ Loaded: {audio_file}")

    # Configure track
    tau.set_loop(1, True)
    tau.set_track_gain(1, 0.3)
    tau.assign_track_channel(1, 0)

    # Play
    print("▶ Playing track 1...")
    tau.play_track(1)

    # Wait and seek
    import time
    time.sleep(3)
    print("⏩ Seeking to 5.0 seconds...")
    tau.seek(1, 5.0)

    time.sleep(3)
    print("⏹ Stopping...")
    tau.stop_track(1)

    print("Done!")
