"""
tau Recording API - Timestamped audio recording with frame-accurate sync

This module provides a high-level Python API for recording audio with tau-engine,
including monotonic timestamp tracking for synchronization with video recordings.

Features:
- Monotonic timestamp capture (nanosecond precision)
- Metadata writing (JSON format)
- Compatible with screentool TRS pattern: db/[epoch].[type].[kind].[format]
- Frame-accurate A/V sync support

Usage:
    recorder = TauRecorder()
    session = recorder.start_recording(
        output_path="db/1234567890.audio.raw.wav",
        t0_monotonic_ns=1234567890123456789
    )
    # ... record ...
    recorder.stop_recording()
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from .tau_playback import TauMultitrack


class TauRecorder:
    """
    High-level recording interface for tau-engine with timestamp sync.

    Handles:
    - Recording start/stop with tau-engine
    - Monotonic timestamp capture and metadata writing
    - Session management
    - Metadata persistence
    """

    def __init__(self, socket_path: str = "~/tau/runtime/tau.sock", auto_start: bool = True):
        """
        Initialize tau recorder.

        Args:
            socket_path: Path to tau-engine socket
            auto_start: Auto-start tau-engine if not running
        """
        self.tau = TauMultitrack(socket_path=socket_path, auto_start=auto_start)
        self.recording_track: Optional[int] = None
        self.output_path: Optional[Path] = None
        self.metadata: Dict[str, Any] = {}

    @staticmethod
    def capture_t0_monotonic_ns() -> int:
        """
        Capture monotonic timestamp in nanoseconds.

        Returns:
            Nanosecond timestamp (monotonic clock)

        Note:
            Monotonic clock is unaffected by system clock adjustments,
            making it ideal for measuring elapsed time and A/V sync.
        """
        return time.monotonic_ns()

    @staticmethod
    def format_iso_timestamp() -> str:
        """
        Get current UTC timestamp in ISO 8601 format.

        Returns:
            ISO 8601 timestamp string (e.g., "2025-01-21T10:30:45.123456Z")
        """
        return datetime.now(timezone.utc).isoformat()

    def start_recording(
        self,
        output_path: Path,
        t0_monotonic_ns: Optional[int] = None,
        sample_rate: int = 48000,
        channels: int = 2,
        track_id: int = 1,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Start audio recording with timestamp tracking.

        Args:
            output_path: Output WAV file path (e.g., db/1234567890.audio.raw.wav)
            t0_monotonic_ns: Monotonic timestamp in nanoseconds (captures now if None)
            sample_rate: Audio sample rate (default: 48000 Hz)
            channels: Number of audio channels (default: 2 = stereo)
            track_id: tau-engine track slot (1-16)
            metadata: Additional metadata to include

        Returns:
            Session metadata dictionary

        Raises:
            RuntimeError: If recording fails to start
        """
        # Convert to Path
        output_path = Path(output_path).expanduser().resolve()

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Capture T0 if not provided
        if t0_monotonic_ns is None:
            t0_monotonic_ns = self.capture_t0_monotonic_ns()

        # Build metadata
        self.metadata = {
            "t0_monotonic_ns": t0_monotonic_ns,
            "recording_start_iso": self.format_iso_timestamp(),
            "sample_rate": sample_rate,
            "channels": channels,
            "bit_depth": 32,  # tau-engine uses float32 (32-bit floating point)
            "sample_format": "float32",
            "format": "wav",
            "track_id": track_id,
            "output_path": str(output_path),
            "engine_socket": str(self.tau.socket_path),
            "engine_version": "1.0",
        }

        # Add custom metadata
        if metadata:
            self.metadata.update(metadata)

        # Write metadata immediately (before recording starts)
        metadata_path = output_path.with_suffix('.wav.json')
        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)

        # Start recording via tau-engine RECORD command
        cmd = f"RECORD START {output_path} {t0_monotonic_ns}"
        response = self.tau._send_command(cmd)

        # Check for success
        if not response.startswith("OK RECORD STARTED"):
            raise RuntimeError(f"Failed to start recording: {response}")

        self.recording_track = track_id
        self.output_path = output_path

        print(f"✓ Recording started via tau-engine")
        print(f"  T0: {t0_monotonic_ns} ns")
        print(f"  Output: {output_path}")
        print(f"  Sample rate: {sample_rate} Hz, Channels: {channels}")
        print(f"  Metadata: {metadata_path}")

        return self.metadata

    def stop_recording(self) -> Dict[str, Any]:
        """
        Stop audio recording and finalize metadata.

        Returns:
            Final session metadata with duration, file size, etc.

        Raises:
            RuntimeError: If no recording is active
        """
        if self.recording_track is None:
            raise RuntimeError("No recording active")

        # Stop recording via tau-engine
        response = self.tau._send_command("RECORD STOP")

        # Check for success and parse stats
        if not response.startswith("OK RECORD STOPPED"):
            raise RuntimeError(f"Failed to stop recording: {response}")

        # Parse frames and duration from response
        # Response format: "OK RECORD STOPPED frames=X duration=Y"
        try:
            parts = response.split()
            frames = int(parts[3].split('=')[1])
            duration_from_engine = float(parts[4].split('=')[1])
        except (IndexError, ValueError):
            frames = 0
            duration_from_engine = 0.0

        # Capture stop time
        t1_monotonic_ns = self.capture_t0_monotonic_ns()

        # Calculate duration from monotonic clock
        duration_ns = t1_monotonic_ns - self.metadata['t0_monotonic_ns']
        duration_sec = duration_ns / 1e9

        # Update metadata
        self.metadata['t1_monotonic_ns'] = t1_monotonic_ns
        self.metadata['recording_stop_iso'] = self.format_iso_timestamp()
        self.metadata['duration_sec'] = duration_sec
        self.metadata['duration_ns'] = duration_ns
        self.metadata['frames_recorded'] = frames
        self.metadata['duration_from_engine'] = duration_from_engine

        # Add file stats if file exists
        if self.output_path and self.output_path.exists():
            self.metadata['file_size_bytes'] = self.output_path.stat().st_size

            # Verify expected size (sample_rate * channels * bytes_per_sample * duration)
            # tau-engine uses float32, so 4 bytes per sample
            expected_size = (
                self.metadata['sample_rate'] *
                self.metadata['channels'] *
                4 *  # float32 = 4 bytes per sample
                duration_from_engine
            ) + 44  # WAV header

            self.metadata['file_size_expected'] = int(expected_size)

        # Write final metadata
        if self.output_path:
            metadata_path = self.output_path.with_suffix('.wav.json')
            with open(metadata_path, 'w') as f:
                json.dump(self.metadata, f, indent=2)

            print(f"✓ Recording stopped")
            print(f"  Duration: {duration_sec:.3f} seconds")
            print(f"  Frames: {frames}")
            print(f"  Metadata updated: {metadata_path}")

        # Reset state
        self.recording_track = None
        final_metadata = self.metadata.copy()
        self.metadata = {}

        return final_metadata

    def get_status(self) -> Dict[str, Any]:
        """
        Get current recording status.

        Returns:
            Status dictionary with recording state and current duration
        """
        if self.recording_track is None:
            return {
                "recording": False,
                "track_id": None
            }

        # Calculate current duration
        t_now_ns = self.capture_t0_monotonic_ns()
        duration_ns = t_now_ns - self.metadata['t0_monotonic_ns']
        duration_sec = duration_ns / 1e9

        return {
            "recording": True,
            "track_id": self.recording_track,
            "output_path": str(self.output_path),
            "duration_sec": duration_sec,
            "duration_ns": duration_ns,
            "t0_monotonic_ns": self.metadata['t0_monotonic_ns'],
            "sample_rate": self.metadata['sample_rate'],
            "channels": self.metadata['channels']
        }


class RecordingSession:
    """
    Context manager for tau recording sessions.

    Usage:
        with RecordingSession(output_path, t0_ns) as session:
            # Recording automatically starts
            time.sleep(5)
            # Recording automatically stops on exit
    """

    def __init__(
        self,
        output_path: Path,
        t0_monotonic_ns: Optional[int] = None,
        **kwargs
    ):
        """
        Initialize recording session context manager.

        Args:
            output_path: Output WAV file path
            t0_monotonic_ns: Monotonic timestamp (captures now if None)
            **kwargs: Additional arguments passed to TauRecorder.start_recording()
        """
        self.recorder = TauRecorder()
        self.output_path = output_path
        self.t0_monotonic_ns = t0_monotonic_ns
        self.kwargs = kwargs
        self.metadata = None

    def __enter__(self):
        """Start recording on context enter."""
        self.metadata = self.recorder.start_recording(
            self.output_path,
            self.t0_monotonic_ns,
            **self.kwargs
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop recording on context exit."""
        if self.recorder.recording_track is not None:
            self.metadata = self.recorder.stop_recording()
        return False


# === Utility Functions ===

def create_session_directory(base_dir: Path, session_id: Optional[int] = None) -> Path:
    """
    Create session directory with TRS structure.

    Args:
        base_dir: Base recordings directory (e.g., ~/recordings)
        session_id: Unix epoch timestamp (uses current time if None)

    Returns:
        Path to session directory with db/ subdirectory created

    Example:
        session_dir = create_session_directory(Path("~/recordings"))
        # Returns: ~/recordings/1705838445/
        #   with:  ~/recordings/1705838445/db/
    """
    if session_id is None:
        session_id = int(time.time())

    base_dir = Path(base_dir).expanduser()
    session_dir = base_dir / str(session_id)
    db_dir = session_dir / "db"

    # Create directories
    db_dir.mkdir(parents=True, exist_ok=True)

    # Create latest symlink
    latest_link = base_dir / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(str(session_id))

    return session_dir


def read_recording_metadata(wav_path: Path) -> Dict[str, Any]:
    """
    Read tau recording metadata from JSON sidecar.

    Args:
        wav_path: Path to WAV file

    Returns:
        Metadata dictionary

    Raises:
        FileNotFoundError: If metadata file doesn't exist
    """
    metadata_path = Path(wav_path).with_suffix('.wav.json')

    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata not found: {metadata_path}")

    with open(metadata_path) as f:
        return json.load(f)


# === Example Usage ===

if __name__ == "__main__":
    # Example 1: Manual control
    print("=== Example 1: Manual Recording ===")

    recorder = TauRecorder()

    # Capture T0 for sync
    t0 = TauRecorder.capture_t0_monotonic_ns()
    print(f"T0: {t0} ns")

    # Start recording
    metadata = recorder.start_recording(
        output_path=Path("test_recording.wav"),
        t0_monotonic_ns=t0,
        metadata={"description": "Test recording"}
    )

    print(f"\nRecording for 3 seconds...")
    time.sleep(3)

    # Stop recording
    final_metadata = recorder.stop_recording()
    print(f"\nFinal metadata:")
    print(json.dumps(final_metadata, indent=2))

    # Example 2: Context manager
    print("\n=== Example 2: Context Manager ===")

    with RecordingSession(Path("test_recording2.wav")) as session:
        print(f"Recording started at T0: {session.metadata['t0_monotonic_ns']}")
        time.sleep(2)

    print("Recording stopped automatically")

    # Example 3: TRS session structure
    print("\n=== Example 3: TRS Session Structure ===")

    session_dir = create_session_directory(Path("~/recordings"))
    print(f"Session directory: {session_dir}")

    session_id = int(session_dir.name)
    audio_path = session_dir / "db" / f"{session_id}.audio.raw.wav"

    print(f"Audio output path: {audio_path}")
