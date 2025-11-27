"""
State management for ASCII Scope SNN.
All application state is managed through these dataclasses.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
import time


# ========== Layout Configuration ==========

@dataclass
class LayoutConfig:
    """
    TUI layout constants - centralized for easy tuning and testing.

    These control the visual structure of the terminal interface.
    """
    # Fixed heights
    header_height: int = 2          # Header rows (transport info)
    cli_prompt_height: int = 1      # CLI input line
    cli_status_height: int = 1      # Bottom status line
    cli_prompt_offset: int = 4      # Lines between prompt and status (feedback area)

    # Dynamic CLI output
    cli_output_min_height: int = 0  # Can collapse when data lanes need space
    cli_output_max_height: int = 8  # Maximum lines for rich output
    cli_float: str = "down"         # "up" = prompt hugs data lanes, "down" = prompt hugs bottom
    cli_completions: str = "below"  # "above" = completions above prompt, "below" = overlay below

    # Completion popup
    completion_max_items: int = 8   # Max visible completion items
    completion_preview_height: int = 3  # Preview pane lines

    # Data viewport
    min_data_viewport: int = 4      # Minimum rows for data lanes

    # Terminal minimums
    min_terminal_width: int = 80
    min_terminal_height: int = 24


# ========== Kernel Parameters ==========

@dataclass
class KernelParams:
    """SNN kernel parameters for tscale.c dual-tau algorithm."""

    tau_a: float = 0.001          # Attack time constant (seconds)
    tau_r: float = 0.005          # Recovery time constant (seconds)
    threshold: float = 3.0         # Threshold in sigma units
    refractory: float = 0.015      # Refractory period (seconds)
    fs: float = 48000              # Sample rate

    def validate(self) -> bool:
        """Validate parameter constraints."""
        return (
            0 < self.tau_a < self.tau_r and
            self.threshold > 0 and
            self.refractory > 0 and
            self.fs > 0
        )

    def to_tscale_args(self) -> List[str]:
        """Convert to tscale command line arguments."""
        return [
            '-ta', str(self.tau_a),
            '-tr', str(self.tau_r),
            '-th', str(self.threshold),
            '-ref', str(self.refractory),
        ]

    def copy(self) -> 'KernelParams':
        """Create a deep copy."""
        return KernelParams(
            tau_a=self.tau_a,
            tau_r=self.tau_r,
            threshold=self.threshold,
            refractory=self.refractory,
            fs=self.fs
        )


# ========== Channel Management ==========

@dataclass
class Channel:
    """Single channel state - uniform across all channels."""

    id: int
    name: str
    visible: bool = True
    gain: float = 1.0
    offset: float = 0.0  # Vertical offset (oscilloscope style)
    color: int = 1       # Curses color pair

    def reset(self):
        """Reset to defaults."""
        self.visible = True
        self.gain = 1.0
        self.offset = 0.0


class ChannelManager:
    """Manages all channels with targeting methods."""

    def __init__(self):
        # Initialize 4 channels with default offsets for oscilloscope layout
        self.channels: List[Channel] = [
            Channel(id=0, name="audio", offset=0.0, color=1),
            Channel(id=1, name="pulse1", offset=1.5, color=2),
            Channel(id=2, name="pulse2", offset=3.0, color=3),
            Channel(id=3, name="env", offset=4.5, color=4),
        ]

    def get(self, channel_id: int) -> Channel:
        """Get channel by ID."""
        if 0 <= channel_id < len(self.channels):
            return self.channels[channel_id]
        raise ValueError(f"Invalid channel ID: {channel_id}")

    def toggle_visibility(self, channel_id: int):
        """Toggle channel visibility."""
        self.get(channel_id).visible = not self.get(channel_id).visible

    def set_gain(self, channel_id: int, gain: float):
        """Set channel gain."""
        self.get(channel_id).gain = gain

    def multiply_gain(self, channel_id: int, factor: float):
        """Multiply channel gain by factor."""
        self.get(channel_id).gain *= factor

    def set_offset(self, channel_id: int, offset: float):
        """Set channel vertical offset."""
        self.get(channel_id).offset = offset

    def adjust_offset(self, channel_id: int, delta: float):
        """Adjust channel offset by delta."""
        self.get(channel_id).offset += delta

    def reset_channel(self, channel_id: int):
        """Reset channel to defaults."""
        self.get(channel_id).reset()

    def all_visible(self) -> List[Channel]:
        """Get list of visible channels."""
        return [ch for ch in self.channels if ch.visible]


# ========== Transport/Playback State ==========

@dataclass
class Transport:
    """Playback transport state with tau audio engine integration."""

    playing: bool = False
    position: float = 0.0       # Current playhead position (seconds)
    span: float = 1.0           # View window size (seconds)
    duration: float = 0.0       # Total duration of loaded data
    last_update: float = field(default_factory=time.time)

    # Tau audio integration
    tau: Optional['TauMultitrack'] = None  # Initialized lazily
    loaded_tracks: Dict[int, int] = field(default_factory=dict)  # {lane_id: track_id}

    def _ensure_tau(self):
        """Lazily initialize tau connection."""
        if self.tau is None:
            try:
                from tau_lib.integration.tau_playback import TauMultitrack
                tau_inst = TauMultitrack()
                # Only set if connection works
                if tau_inst.check_connection():
                    self.tau = tau_inst
            except Exception as e:
                # Tau not available - that's ok, continue without audio
                pass

    def update(self, dt: float = None):
        """Update playhead if playing."""
        if self.playing:
            now = time.time()
            if dt is None:
                dt = now - self.last_update
            self.last_update = now
            self.position += dt

            # Stop at end
            if self.position >= self.duration:
                self.position = self.duration
                self.playing = False

    def toggle_play(self):
        """Toggle play/pause with tau sync."""
        self.playing = not self.playing
        if self.playing:
            self.last_update = time.time()
            # Sync tau audio playback
            self._ensure_tau()
            if self.tau:
                try:
                    self.tau.seek_all(self.position)
                    self.tau.play_all()
                except Exception:
                    pass  # Continue without audio
        else:
            # Stop tau playback
            if self.tau:
                try:
                    self.tau.stop_all()
                except Exception:
                    pass

    def seek(self, position: float):
        """Seek to absolute position with tau sync."""
        self.position = max(0.0, min(position, self.duration))
        # Sync tau audio position
        if self.tau:
            try:
                self.tau.seek_all(self.position)
            except Exception:
                pass

    def scrub(self, delta: float):
        """Scrub by delta (can be negative)."""
        self.seek(self.position + delta)

    def scrub_pct(self, percent: float):
        """Scrub by percentage of duration."""
        self.scrub(self.duration * percent / 100.0)

    def home(self):
        """Jump to start."""
        self.seek(0.0)
        self.playing = False

    def end(self):
        """Jump to end."""
        self.seek(max(0.0, self.duration - self.span))
        self.playing = False

    def zoom(self, new_span: float):
        """Set zoom level."""
        self.span = max(0.01, min(new_span, self.duration))

    def zoom_in(self, factor: float = 1.25):
        """Zoom in by factor."""
        self.zoom(self.span / factor)

    def zoom_out(self, factor: float = 1.25):
        """Zoom out by factor."""
        self.zoom(self.span * factor)

    def compute_window(self) -> tuple[float, float]:
        """Compute visible time window [left, right]."""
        left = self.position
        right = self.position + self.span
        return (left, right)

    def load_audio_for_lane(self, lane_id: int, audio_path: Path) -> bool:
        """
        Load audio file for a lane with tau.

        Args:
            lane_id: Lane number (1-8)
            audio_path: Path to audio file

        Returns:
            True if loaded successfully
        """
        self._ensure_tau()
        if not self.tau:
            return False

        try:
            # Map lane to track (1:1 for simplicity)
            track_id = lane_id
            if self.tau.load_track(track_id, audio_path):
                self.loaded_tracks[lane_id] = track_id
                # Enable looping for DAW-style playback
                self.tau.set_loop(track_id, True)
                # Route to channel (round-robin across 4 channels)
                channel = (lane_id - 1) % 4
                self.tau.assign_track_channel(track_id, channel)
                return True
        except Exception:
            pass
        return False

    def unload_audio_for_lane(self, lane_id: int):
        """Unload audio from lane."""
        if lane_id in self.loaded_tracks:
            track_id = self.loaded_tracks[lane_id]
            if self.tau:
                try:
                    self.tau.stop_track(track_id)
                except Exception:
                    pass
            del self.loaded_tracks[lane_id]

    def set_lane_gain(self, lane_id: int, gain: float):
        """Set lane audio gain."""
        if lane_id in self.loaded_tracks and self.tau:
            track_id = self.loaded_tracks[lane_id]
            try:
                self.tau.set_track_gain(track_id, gain)
            except Exception:
                pass


# ========== Marker System ==========

@dataclass
class Marker:
    """Time bookmark for quick navigation."""

    time: float
    label: str
    color: int = 6  # Default color


class MarkerManager:
    """Manages time bookmarks."""

    def __init__(self):
        self.markers: List[Marker] = []

    def add(self, time: float, label: str, color: int = 6) -> Marker:
        """Add a marker."""
        # Check for duplicate label
        if self.get_by_label(label):
            raise ValueError(f"Marker '{label}' already exists")

        marker = Marker(time=time, label=label, color=color)
        self.markers.append(marker)
        # Keep sorted by time
        self.markers.sort(key=lambda m: m.time)
        return marker

    def remove(self, label: str) -> bool:
        """Remove marker by label. Returns True if found."""
        for i, m in enumerate(self.markers):
            if m.label == label:
                del self.markers[i]
                return True
        return False

    def get_by_label(self, label: str) -> Marker:
        """Get marker by label."""
        for m in self.markers:
            if m.label == label:
                return m
        return None

    def find_nearest(self, time: float) -> Marker:
        """Find nearest marker to given time."""
        if not self.markers:
            return None
        return min(self.markers, key=lambda m: abs(m.time - time))

    def find_next(self, time: float) -> Marker:
        """Find next marker after given time."""
        for m in self.markers:
            if m.time > time:
                return m
        return None

    def find_prev(self, time: float) -> Marker:
        """Find previous marker before given time."""
        for m in reversed(self.markers):
            if m.time < time:
                return m
        return None

    def all(self) -> List[Marker]:
        """Get all markers sorted by time."""
        return self.markers.copy()


# ========== Display State ==========

@dataclass
class DisplayState:
    """Display preferences."""

    mode: str = "envelope"  # "envelope" or "points"
    show_help: bool = False

    def toggle_mode(self):
        """Toggle between envelope and points."""
        self.mode = "points" if self.mode == "envelope" else "envelope"


# ========== Feature Flags ==========

@dataclass
class FeatureFlags:
    """Feature flags for optional functionality."""

    video_available: bool = False       # opencv successfully imported
    video_enabled: bool = True          # User wants video (--no-video to disable)
    video_sampling_interval: float = 1.0  # Frames per second for thumbnail strip
    video_thumbnail_size: int = 4       # NxN thumbnail resolution (default 4x4)
    video_popup_resolution: tuple = (80, 40)  # Popup viewer resolution (w, h)

    # Startup experience
    show_startup_tips: bool = True      # Show "did you know" tips on startup
    startup_tips_count: int = 3         # Number of tips to show before main UI
    require_enter_to_advance: bool = True  # Require Enter (not any key) to advance

    # Runtime tips request (set by 'tips' command)
    show_tips_requested: bool = False   # Request to show tips from main loop

    # Redraw flag (set by background threads like OSC to trigger screen update)
    needs_redraw: bool = False


# ========== Top-Level Application State ==========

@dataclass
class AppState:
    """Top-level container for all application state."""

    kernel: KernelParams = field(default_factory=KernelParams)
    transport: Transport = field(default_factory=Transport)
    markers: MarkerManager = field(default_factory=MarkerManager)
    display: DisplayState = field(default_factory=DisplayState)
    features: FeatureFlags = field(default_factory=FeatureFlags)
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    # File paths
    audio_input: str = None
    data_file: str = None
    context_dir: Path = None  # Context directory (default ~/recordings/)

    # Data buffer (loaded by data_loader)
    data_buffer: List[tuple] = field(default_factory=list)  # [(time, [v1,v2,v3,v4]), ...]

    # Lane management (replaces channels and pages)
    # Note: lanes initialized after data_buffer is loaded to get column count
    lanes: 'LaneManager' = None  # Forward reference, initialized in __post_init__

    # Video popup (initialized when video feature is enabled)
    video_popup: Optional['VideoPopup'] = None

    def __post_init__(self):
        """Initialize lanes after data buffer is available."""
        if self.lanes is None:
            # Import here to avoid circular dependency
            from tui_py.content.lanes import LaneManager
            # Determine column count from data buffer
            num_columns = len(self.data_buffer[0][1]) if self.data_buffer else 4

            self.lanes = LaneManager(
                data_columns=num_columns
            )

        # Set default context directory if not specified
        if self.context_dir is None:
            self.context_dir = Path.home() / "recordings"
