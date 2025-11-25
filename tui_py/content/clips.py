"""
Clip system for ASCII Scope SNN.

Clips are content that live inside lanes:
- TimebasedClip: Audio waveforms, moves with transport
- StaticClip: Fixed text, preamble, doesn't move with time
- EventsClip: Timestamped events with filtering and color-coding
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class ClipType(Enum):
    """Type of clip content."""
    TIMEBASED = "timebased"  # Moves with transport
    STATIC = "static"        # Fixed content
    EVENTS = "events"        # Event log with timestamps


class TimeFormat(Enum):
    """Time display format for events."""
    ABSOLUTE = "absolute"    # [12.345s]
    RELATIVE = "relative"    # [+0.123s]
    DELTA = "delta"          # [Δ123ms]
    TIMESTAMP = "timestamp"  # [14:35:12.345]


class EventLevel(Enum):
    """Event severity level."""
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


@dataclass
class Event:
    """A timestamped event with metadata."""
    timestamp: float        # Seconds since session start
    level: EventLevel
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Computed fields (set by EventsClip)
    delta_time_ms: Optional[float] = None  # Time since last event (ms)
    delta_time_sd: Optional[float] = None  # Standard deviation of recent deltas


@dataclass
class EventFilter:
    """Filter configuration for events."""
    levels: List[EventLevel] = field(default_factory=list)  # Empty = all levels
    message_pattern: Optional[str] = None                   # Regex pattern
    time_range: Optional[tuple[float, float]] = None        # (start, end) in seconds

    def matches(self, event: Event) -> bool:
        """Check if event matches filter."""
        # Level filter
        if self.levels and event.level not in self.levels:
            return False

        # Message pattern filter
        if self.message_pattern:
            import re
            if not re.search(self.message_pattern, event.message, re.IGNORECASE):
                return False

        # Time range filter
        if self.time_range:
            start, end = self.time_range
            if not (start <= event.timestamp <= end):
                return False

        return True


class Clip(ABC):
    """Abstract base class for all clips."""

    def __init__(self, clip_type: ClipType, name: str = ""):
        self.clip_type = clip_type
        self.name = name
        self.start_time: Optional[float] = None  # For timebased clips
        self.end_time: Optional[float] = None    # For timebased clips

    @abstractmethod
    def render(self, layout, state) -> List[str]:
        """
        Render clip content to lines of text.

        Args:
            layout: Layout object with y, x, h, w
            state: Application state (for transport position, etc.)

        Returns:
            List of strings to display
        """
        pass

    def is_timebased(self) -> bool:
        """Check if clip moves with transport."""
        return self.clip_type == ClipType.TIMEBASED

    def is_static(self) -> bool:
        """Check if clip is fixed content."""
        return self.clip_type == ClipType.STATIC

    def is_events(self) -> bool:
        """Check if clip is an event log."""
        return self.clip_type == ClipType.EVENTS


class TimebasedClip(Clip):
    """Clip containing time-based waveform data."""

    def __init__(self, name: str, channel_id: int, data_buffer, gain: float = 1.0):
        super().__init__(ClipType.TIMEBASED, name)
        self.channel_id = channel_id
        self.data_buffer = data_buffer
        self.gain = gain

    def render(self, layout, state) -> List[str]:
        """Render waveform data (delegates to existing rendering functions)."""
        # This will be implemented to use existing waveform rendering
        return [f"TimebasedClip: {self.name} ch{self.channel_id}"]


class StaticClip(Clip):
    """Clip containing static text content."""

    def __init__(self, name: str, lines: List[str] = None):
        super().__init__(ClipType.STATIC, name)
        self.lines = lines or []

    def set_content(self, lines: List[str]):
        """Set static content."""
        self.lines = lines

    def append_line(self, line: str):
        """Append line to content."""
        self.lines.append(line)

    def clear(self):
        """Clear all content."""
        self.lines.clear()

    def render(self, layout, state) -> List[str]:
        """Render static text lines."""
        # Take only what fits in layout
        return self.lines[:layout.h]


class EventsClip(Clip):
    """
    Clip containing timestamped events with filtering and color-coding.

    Features:
    - Color-coded by level (info, warn, error, debug)
    - Color-coded by inter-event timing (delta time)
    - Delta time statistics (mean, standard deviation)
    - Filtering by level, message, time range
    - Configurable time format display
    """

    def __init__(self, name: str = "events", max_events: int = 1000):
        super().__init__(ClipType.EVENTS, name)
        self.events: List[Event] = []
        self.max_events = max_events
        self.session_start_time = time.time()
        self.filter = EventFilter()
        self.time_format = TimeFormat.ABSOLUTE

        # Delta time statistics (rolling window)
        self.delta_times: List[float] = []  # Recent delta times in ms
        self.window_size = 20  # Number of events for statistics

    def add_event(self, level: EventLevel, message: str, metadata: Dict[str, Any] = None):
        """Add a new event to the log."""
        timestamp = time.time() - self.session_start_time
        event = Event(
            timestamp=timestamp,
            level=level,
            message=message,
            metadata=metadata or {}
        )

        # Compute delta time
        if self.events:
            delta_ms = (timestamp - self.events[-1].timestamp) * 1000
            event.delta_time_ms = delta_ms

            # Update rolling statistics
            self.delta_times.append(delta_ms)
            if len(self.delta_times) > self.window_size:
                self.delta_times.pop(0)

            # Compute standard deviation
            if len(self.delta_times) > 1:
                import statistics
                event.delta_time_sd = statistics.stdev(self.delta_times)

        self.events.append(event)

        # Trim to max_events
        if len(self.events) > self.max_events:
            self.events.pop(0)

    def set_filter(self, filter: EventFilter):
        """Set event filter."""
        self.filter = filter

    def clear_filter(self):
        """Clear all filters."""
        self.filter = EventFilter()

    def set_time_format(self, format: TimeFormat):
        """Set time display format."""
        self.time_format = format

    def get_filtered_events(self) -> List[Event]:
        """Get events matching current filter."""
        return [e for e in self.events if self.filter.matches(e)]

    def format_time(self, event: Event) -> str:
        """Format timestamp according to current time_format."""
        if self.time_format == TimeFormat.ABSOLUTE:
            return f"[{event.timestamp:7.3f}s]"
        elif self.time_format == TimeFormat.RELATIVE:
            if event.delta_time_ms is not None:
                return f"[+{event.delta_time_ms:6.1f}ms]"
            return "[+0.0ms]"
        elif self.time_format == TimeFormat.DELTA:
            if event.delta_time_ms is not None:
                return f"[Δ{event.delta_time_ms:6.1f}ms]"
            return "[Δ0.0ms]"
        elif self.time_format == TimeFormat.TIMESTAMP:
            import datetime
            dt = datetime.datetime.fromtimestamp(self.session_start_time + event.timestamp)
            return f"[{dt.strftime('%H:%M:%S.%f')[:-3]}]"
        return ""

    def get_level_color(self, level: EventLevel) -> int:
        """Get curses color pair for event level."""
        # Map to existing color pairs (defined in rendering/helpers.py)
        if level == EventLevel.ERROR:
            return 1  # Red
        elif level == EventLevel.WARN:
            return 3  # Yellow
        elif level == EventLevel.INFO:
            return 7  # White
        elif level == EventLevel.DEBUG:
            return 8  # Dim/gray
        return 7

    def get_delta_color(self, delta_ms: Optional[float]) -> int:
        """Get color based on inter-event timing."""
        if delta_ms is None:
            return 7  # White

        # Color code by timing
        if delta_ms < 50:
            return 2   # Green (very fast)
        elif delta_ms < 100:
            return 6   # Cyan (fast)
        elif delta_ms < 500:
            return 3   # Yellow (medium)
        elif delta_ms < 1000:
            return 5   # Magenta (slow)
        else:
            return 1   # Red (very slow)

    def render(self, layout, state) -> List[str]:
        """
        Render filtered events with color coding.

        Returns list of tuples: (text, color_pair, attributes)
        """
        filtered = self.get_filtered_events()

        # Take last N events that fit in layout
        visible_events = filtered[-layout.h:]

        lines = []
        for event in visible_events:
            # Format time
            time_str = self.format_time(event)

            # Format level
            level_str = f"[{event.level.value:5s}]"

            # Format message (truncate if needed)
            max_msg_len = layout.w - len(time_str) - len(level_str) - 2
            message = event.message[:max_msg_len]

            # Build line
            line = f"{time_str} {level_str} {message}"

            # Add color information (for rendering)
            # Format: (line, level_color, delta_color)
            level_color = self.get_level_color(event.level)
            delta_color = self.get_delta_color(event.delta_time_ms)

            lines.append((line, level_color, delta_color, event))

        return lines

    def get_stats(self) -> Dict[str, Any]:
        """Get event statistics."""
        filtered = self.get_filtered_events()

        stats = {
            'total_events': len(self.events),
            'filtered_events': len(filtered),
            'by_level': {},
            'delta_time_mean_ms': 0.0,
            'delta_time_sd_ms': 0.0,
        }

        # Count by level
        for level in EventLevel:
            stats['by_level'][level.value] = len([e for e in filtered if e.level == level])

        # Delta time statistics
        if self.delta_times:
            import statistics
            stats['delta_time_mean_ms'] = statistics.mean(self.delta_times)
            if len(self.delta_times) > 1:
                stats['delta_time_sd_ms'] = statistics.stdev(self.delta_times)

        return stats
