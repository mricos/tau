"""
Simplified lane management for scrollable multi-track view.
Each lane is a data channel with independent display mode.
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional
from enum import IntEnum, Enum


class LaneDisplayMode(IntEnum):
    """Display mode for a lane - determines height."""
    HIDDEN = 0      # Not visible
    COMPACT = 1     # 1-line sparkline (default)
    FULL = 8        # Multi-line waveform (configurable per lane)


class LaneState(Enum):
    """State machine states for lane interaction."""
    NORMAL = "normal"          # Default state
    SELECTED = "selected"      # Recently selected (highlighted)
    EDITING = "editing"        # Content being edited
    PLAYING = "playing"        # Actively playing/rendering (timebased)
    HIDDEN = "hidden"          # Not visible
    PINNED = "pinned"          # Locked in position


class LaneStateMachine:
    """
    State machine for lane keyboard interactions.

    Handles transitions like:
    - DOWN → SELECTED (on double-click)
    - UP-QUICK → toggle visibility
    - UP-MEDIUM → toggle expanded
    """

    def __init__(self, lane_id: int):
        self.lane_id = lane_id
        self.state = LaneState.NORMAL
        self.last_action_time = 0.0
        self.double_click_threshold = 0.3  # seconds

    def on_down(self, current_time: float):
        """Handle mouse/key down event."""
        delta = current_time - self.last_action_time
        if delta < self.double_click_threshold:
            # Double-click detected
            self.state = LaneState.SELECTED
        self.last_action_time = current_time

    def on_up_quick(self):
        """Handle quick up event (toggle visibility)."""
        if self.state == LaneState.NORMAL:
            self.state = LaneState.HIDDEN
        elif self.state == LaneState.HIDDEN:
            self.state = LaneState.NORMAL

    def on_up_medium(self):
        """Handle medium up event (toggle expanded)."""
        # Toggle between COMPACT and FULL modes
        pass  # Handled by Lane.toggle_mode()

    def is_selected(self) -> bool:
        """Check if lane is in selected state."""
        return self.state == LaneState.SELECTED

    def reset(self):
        """Reset to normal state."""
        self.state = LaneState.NORMAL


@dataclass
class Lane:
    """A single data lane (track) in the view."""

    id: int                         # Lane number (0-9)
    name: str                       # Display name: "audio", "pulse1", etc.
    lane_type: str = "timebased"    # "timebased" or "pinned"
    channel_id: int = 0             # Which data column (for timebased lanes)

    display_mode: LaneDisplayMode = LaneDisplayMode.COMPACT  # Display mode (default: 1-line)
    full_height: int = 8            # Height when in FULL mode (configurable, default 8)
    _saved_mode: LaneDisplayMode = None  # Previous mode before hiding (for restore)
    gain: float = 1.0               # Amplitude multiplier (for timebased)
    color: int = 1                  # Curses color pair
    clip_name: str = ""             # Clip/file name (max 16 chars, shown in lane)

    # Clip-based architecture (new)
    clip_stack: List = field(default_factory=list)  # List[Clip] - multiple clips can be layered
    state_machine: LaneStateMachine = None          # State machine for interactions

    # Pinned content (for pinned lanes - legacy, will be replaced by clips)
    content: List[str] = None       # Text lines to display
    content_colors: List[int] = None  # Color pair for each content line

    # Fixed heights for special lanes
    HEIGHT_SPECIAL = 4  # Fixed height for special lanes (logs, events)

    def __post_init__(self):
        """Initialize mutable defaults."""
        if self.content is None:
            self.content = []
        if self.content_colors is None:
            self.content_colors = []
        if self.state_machine is None:
            self.state_machine = LaneStateMachine(self.id)

    def get_height(self) -> int:
        """Get current height based on display mode."""
        # Special lanes (logs, events) always use fixed 4-row height when visible
        if self.is_pinned() and self.name in ("logs", "events"):
            return self.HEIGHT_SPECIAL if self.is_visible() else 0
        # Hidden lanes have 0 height
        if self.display_mode == LaneDisplayMode.HIDDEN:
            return 0
        # COMPACT uses 1 line
        if self.display_mode == LaneDisplayMode.COMPACT:
            return 1
        # FULL uses configurable height
        return self.full_height

    def is_visible(self) -> bool:
        """Check if lane is visible."""
        return self.display_mode != LaneDisplayMode.HIDDEN

    def is_timebased(self) -> bool:
        """Check if lane shows time-based waveform data."""
        return self.lane_type == "timebased"

    def is_pinned(self) -> bool:
        """Check if lane shows pinned text content."""
        return self.lane_type == "pinned"

    def set_content(self, lines: List[str]):
        """Set pinned content (for pinned lanes)."""
        self.content = lines if lines else []

    def append_content(self, line: str, color: int = 0):
        """Append line to pinned content with optional color."""
        if self.content is None:
            self.content = []
        if self.content_colors is None:
            self.content_colors = []
        self.content.append(line)
        self.content_colors.append(color)

    def clear_content(self):
        """Clear pinned content."""
        self.content = []
        self.content_colors = []


class LaneManager:
    """Manages data lanes with scrolling support."""

    def __init__(self, data_columns: int = 4):
        """
        Initialize lane manager with 10 lanes:
        - Lane 0: Logs (pinned, 4 rows, bottom-most special lane)
        - Lanes 1-8: Data tracks (timebased, scrollable)
        - Lane 9: Events (pinned, 4 rows, above logs)

        Key bindings:
        - 1-9: Toggle visibility (HIDDEN ↔ NORMAL)
        - Shift+1-9: Cycle display mode (COMPACT → NORMAL → FULL → COMPACT)

        Args:
            data_columns: Number of data columns in tscale output
        """
        # Default names for data lanes 1-8
        default_names = [
            "",         # Lane 0 (logs) - set separately
            "audio",    # Lane 1: audio signal
            "pulse1",   # Lane 2: beat detection
            "pulse2",   # Lane 3: subdivision detection
            "env",      # Lane 4: envelope
            "ch5",      # Lane 5: extra
            "ch6",      # Lane 6: extra
            "ch7",      # Lane 7: extra
            "ch8",      # Lane 8: extra
            ""          # Lane 9 (events) - set separately
        ]

        colors = [7, 1, 2, 3, 4, 5, 6, 7, 8, 8]  # Lane 0=gray, 1-8=colors, 9=gray

        # Create 10 lanes total
        self.lanes: List[Lane] = []

        # Lane 0: Logs (pinned, 4 rows fixed, bottom-most)
        self.lanes.append(Lane(
            id=0,
            name="logs",
            lane_type="pinned",
            channel_id=-1,
            display_mode=LaneDisplayMode.FULL,  # Visible by default
            gain=1.0,
            color=colors[0],
            clip_name=""
        ))

        # Lanes 1-8: Time-based data lanes
        for i in range(1, 9):
            # First 4 lanes visible (COMPACT - 1 line), rest hidden
            mode = LaneDisplayMode.COMPACT if i <= 4 else LaneDisplayMode.HIDDEN
            lane = Lane(
                id=i,
                name=default_names[i],
                lane_type="timebased",
                channel_id=(i-1) if (i-1) < data_columns else 0,
                display_mode=mode,
                gain=1.0,
                color=colors[i],
                clip_name=""
            )
            self.lanes.append(lane)

        # Lane 9: Events (pinned, 4 rows fixed, above logs)
        self.lanes.append(Lane(
            id=9,
            name="events",
            lane_type="pinned",
            channel_id=-1,
            display_mode=LaneDisplayMode.HIDDEN,  # Hidden by default
            gain=1.0,
            color=colors[9],
            clip_name=""
        ))

        # Scrolling state (for data lanes 1-8 only)
        self.scroll_offset: int = 0  # Index of first visible lane

        # Track last 2 lane selections for header display
        self.recent_selections = []  # List of (lane_id, timestamp) tuples

        # Current lane for CLI prompt
        self.current_lane_id: int = 1  # Default to lane 1 (audio)

    def get_lane(self, lane_id: int) -> Optional[Lane]:
        """Get lane by ID (0-9)."""
        if 0 <= lane_id < len(self.lanes):
            return self.lanes[lane_id]
        return None

    def get_data_lanes(self) -> List[Lane]:
        """Get only data lanes (1-8), excluding special lanes (0, 9)."""
        return [self.lanes[i] for i in range(1, 9)]

    def get_special_lanes(self) -> List[Lane]:
        """Get special lanes (9=events, 0=logs) in display order."""
        return [self.lanes[9], self.lanes[0]]  # Events above logs

    def get_visible_lanes(self) -> List[Lane]:
        """Get only visible lanes in order."""
        return [lane for lane in self.lanes if lane.is_visible()]

    def toggle_visibility(self, lane_id: int) -> str:
        """
        Toggle lane visibility (keys 1-9).
        HIDDEN → restore previous mode (or COMPACT if never shown)
        COMPACT/FULL → HIDDEN (saves current mode)

        Returns:
            Status message
        """
        lane = self.get_lane(lane_id)
        if not lane:
            return f"Invalid lane: {lane_id}"

        if lane.display_mode == LaneDisplayMode.HIDDEN:
            # Restore previous mode, or default to COMPACT
            if lane._saved_mode and lane._saved_mode != LaneDisplayMode.HIDDEN:
                lane.display_mode = lane._saved_mode
                if lane._saved_mode == LaneDisplayMode.COMPACT:
                    status = "visible (1 line)"
                else:
                    status = f"visible ({lane.full_height} lines)"
            else:
                lane.display_mode = LaneDisplayMode.COMPACT
                status = "visible (1 line)"
        else:
            # Hide and save current mode
            lane._saved_mode = lane.display_mode
            lane.display_mode = LaneDisplayMode.HIDDEN
            status = "hidden"

        # Record selection
        self._record_selection(lane_id)

        # Set as current lane (data lanes only)
        if 1 <= lane_id <= 8:
            self.current_lane_id = lane_id

        return f"Lane {lane_id} ({lane.name}): {status}"

    def cycle_display_mode(self, lane_id: int) -> str:
        """
        Toggle between COMPACT and FULL modes (Shift+1-9).
        COMPACT (1 line) ↔ FULL (configurable, default 8 lines)

        Special lanes (0, 9) are not affected.

        Returns:
            Status message
        """
        lane = self.get_lane(lane_id)
        if not lane:
            return f"Invalid lane: {lane_id}"

        # Special lanes don't cycle
        if lane.id in [0, 9]:
            return f"Lane {lane_id} ({lane.name}): special lane (no size modes)"

        # Toggle between COMPACT and FULL
        if lane.display_mode == LaneDisplayMode.FULL:
            lane.display_mode = LaneDisplayMode.COMPACT
            status = "compact (1 line)"
        else:
            # From HIDDEN or COMPACT → FULL
            lane.display_mode = LaneDisplayMode.FULL
            status = f"full ({lane.full_height} lines)"

        # Record selection
        self._record_selection(lane_id)

        return f"Lane {lane_id} ({lane.name}): {status}"

    def set_full_height(self, lane_id: int, height: int) -> str:
        """
        Set the height for FULL mode (CLI command).

        Args:
            lane_id: Lane ID (0-9)
            height: Height in lines (1-30)

        Returns:
            Status message
        """
        lane = self.get_lane(lane_id)
        if not lane:
            return f"Invalid lane: {lane_id}"

        if not 1 <= height <= 30:
            return f"✗ Height must be 1-30, got {height}"

        lane.full_height = height
        return f"✓ Lane {lane_id} ({lane.name}) full height set to {height} lines"

    def set_gain(self, lane_id: int, gain: float):
        """Set gain for lane."""
        lane = self.get_lane(lane_id)
        if lane:
            lane.gain = gain

    def multiply_gain(self, lane_id: int, factor: float):
        """Multiply lane gain by factor."""
        lane = self.get_lane(lane_id)
        if lane:
            lane.gain *= factor

    def compute_total_height(self) -> int:
        """Compute total height needed for all visible lanes."""
        return sum(lane.get_height() for lane in self.get_visible_lanes())

    def scroll_up(self, amount: int = 1):
        """Scroll viewport up (show earlier lanes)."""
        self.scroll_offset = max(0, self.scroll_offset - amount)

    def scroll_down(self, amount: int = 1):
        """Scroll viewport down (show later lanes)."""
        visible = self.get_visible_lanes()
        if visible:
            max_offset = len(visible) - 1
            self.scroll_offset = min(max_offset, self.scroll_offset + amount)

    def scroll_to_top(self):
        """Scroll to top of lane list."""
        self.scroll_offset = 0

    def scroll_to_bottom(self):
        """Scroll to bottom of lane list."""
        visible = self.get_visible_lanes()
        if visible:
            self.scroll_offset = len(visible) - 1

    def _record_selection(self, lane_id: int):
        """Record a lane selection in recent history (keep last 2)."""
        # Remove any existing entry for this lane
        self.recent_selections = [(lid, ts) for lid, ts in self.recent_selections if lid != lane_id]
        # Add new entry at end
        self.recent_selections.append((lane_id, time.time()))
        # Keep only last 2
        if len(self.recent_selections) > 2:
            self.recent_selections.pop(0)

    def get_recent_selections(self) -> list[int]:
        """Get list of recently selected lane IDs (most recent last)."""
        return [lane_id for lane_id, _ in self.recent_selections]

    def add_log(self, text: str, log_level: str = "INFO", delta_ms: int = 0):
        """
        Add a log line to lane 0 (logs) with color coding.

        Args:
            text: Log message
            log_level: Log level (INFO, WARNING, ERROR, SUCCESS)
            delta_ms: Time since last event in milliseconds
        """
        logs_lane = self.get_lane(0)
        if logs_lane:
            # Map log level to color pair
            level_colors = {
                "INFO": 12,     # Cyan - info
                "WARNING": 10,  # Yellow - warning
                "ERROR": 11,    # Red - error
                "SUCCESS": 9,   # Green - success
            }
            color = level_colors.get(log_level, 12)  # Default to INFO color

            # Format: [+deltaMs] LEVEL: message
            formatted = f"[+{delta_ms:4d}ms] {log_level:7s}: {text}"
            logs_lane.append_content(formatted, color)

    def add_event(self, text: str, delta_ms: int = 0):
        """
        Add an event line to lane 9 (events) with deltaTimeMs.

        Args:
            text: Event message
            delta_ms: Time since last event in milliseconds
        """
        events_lane = self.get_lane(9)
        if events_lane:
            # Format: [+deltaMs] message (plain text)
            formatted = f"[+{delta_ms:4d}ms] {text}"
            events_lane.append_content(formatted, 0)  # Default color

    def clear_logs(self):
        """Clear all log content from lane 0."""
        logs_lane = self.get_lane(0)
        if logs_lane:
            logs_lane.clear_content()

    def clear_events(self):
        """Clear all event content from lane 9."""
        events_lane = self.get_lane(9)
        if events_lane:
            events_lane.clear_content()

