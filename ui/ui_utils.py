"""
UI utilities for width-aware rendering and string formatting.
Supports 80x24 minimum terminal with adaptive layouts.
"""

from typing import Dict, Optional
from dataclasses import dataclass


# ========== Width Awareness ==========

@dataclass
class WidthContext:
    """Context for width-aware rendering."""
    total: int          # Total terminal width
    narrow: bool        # True if < 100 columns
    compact: bool       # True if < 80 columns (minimum)

    @classmethod
    def from_width(cls, width: int) -> 'WidthContext':
        """Create context from terminal width."""
        return cls(
            total=width,
            narrow=(width < 100),
            compact=(width <= 80)
        )

    def scale(self, full: int, narrow: int, compact: int) -> int:
        """Select value based on width mode."""
        if self.compact:
            return compact
        elif self.narrow:
            return narrow
        else:
            return full


# ========== String Truncation ==========

def truncate_middle(text: str, max_len: int, ellipsis: str = "...") -> str:
    """
    Truncate string in the middle with ellipsis.

    Args:
        text: String to truncate
        max_len: Maximum length
        ellipsis: Ellipsis string (default "...")

    Returns:
        Truncated string with ellipsis in middle

    Examples:
        truncate_middle("/very/long/path/to/file.txt", 20)
        -> "/very/lon...ile.txt"
    """
    if len(text) <= max_len:
        return text

    if max_len < len(ellipsis):
        return ellipsis[:max_len]

    # Calculate how much space for actual text
    available = max_len - len(ellipsis)
    left_len = (available + 1) // 2  # Favor left side
    right_len = available // 2

    return text[:left_len] + ellipsis + text[-right_len:]


def truncate_path(path: str, max_len: int) -> str:
    """
    Truncate filesystem path intelligently.
    Preserves filename and parent directory if possible.

    Args:
        path: File path to truncate
        max_len: Maximum length

    Returns:
        Truncated path

    Examples:
        truncate_path("/Users/name/project/file.txt", 25)
        -> ".../project/file.txt"
    """
    if len(path) <= max_len:
        return path

    # Try to keep filename
    parts = path.split('/')
    filename = parts[-1]

    if len(filename) + 4 >= max_len:  # ".../" + filename
        # Filename too long, truncate it
        return ".../" + truncate_middle(filename, max_len - 4)

    # Build from right, keeping as many parts as fit
    result = filename
    for i in range(len(parts) - 2, -1, -1):
        part = parts[i]
        if len(part) + len(result) + 5 <= max_len:  # ".../" + part + "/" + result
            result = part + "/" + result
        else:
            return ".../" + result

    return result


# ========== Abbreviations ==========

class AbbrevRegistry:
    """Registry of semantic abbreviations for narrow displays."""

    def __init__(self):
        self.abbrevs: Dict[str, tuple[str, str]] = {}  # key -> (abbrev, full_text)
        self._register_defaults()

    def _register_defaults(self):
        """Register default abbreviations."""
        # Transport
        self.register("playing", "▶", "Playing")
        self.register("stopped", "■", "Stopped")
        self.register("position", "pos", "Position")
        self.register("duration", "dur", "Duration")

        # Parameters
        self.register("tau_attack", "τa", "Attack Time Constant")
        self.register("tau_release", "τr", "Release Time Constant")
        self.register("threshold", "thr", "Threshold")
        self.register("refractory", "ref", "Refractory Period")

        # Lanes
        self.register("visible", "●", "Visible")
        self.register("hidden", "○", "Hidden")
        self.register("expanded", "E", "Expanded")
        self.register("collapsed", "c", "Collapsed")

        # Channels
        self.register("audio", "aud", "Audio Signal")
        self.register("pulse1", "p1", "Pulse 1")
        self.register("pulse2", "p2", "Pulse 2")
        self.register("envelope", "env", "Envelope")

        # Display modes
        self.register("envelope_mode", "env", "Envelope Mode")
        self.register("points_mode", "pts", "Points Mode")

        # Commands
        self.register("help", "?", "Help")
        self.register("quit", "q", "Quit")
        self.register("cli", ":", "CLI Mode")
        self.register("zoom", "z", "Zoom Level")

    def register(self, key: str, abbrev: str, full_text: str):
        """Register an abbreviation."""
        self.abbrevs[key] = (abbrev, full_text)

    def get(self, key: str, narrow: bool = False, compact: bool = False) -> str:
        """
        Get text for key, respecting width mode.

        Args:
            key: Registry key
            narrow: Use narrow form
            compact: Use most compact form (abbrev)

        Returns:
            Appropriate text for width mode
        """
        if key not in self.abbrevs:
            return key

        abbrev, full = self.abbrevs[key]

        if compact:
            return abbrev
        elif narrow and len(abbrev) <= 4:
            return abbrev
        else:
            return full

    def get_help(self, key: str) -> Optional[str]:
        """Get help text for abbreviation."""
        if key in self.abbrevs:
            abbrev, full = self.abbrevs[key]
            return f"{abbrev} = {full}"
        return None

    def list_all(self) -> list[tuple[str, str, str]]:
        """List all abbreviations as (key, abbrev, full)."""
        return [(k, v[0], v[1]) for k, v in sorted(self.abbrevs.items())]


# Global registry instance
ABBREV = AbbrevRegistry()


# ========== Semantic Name Mapping ==========

class SemanticNameMapper:
    """Maps semantic names to lane IDs and properties."""

    def __init__(self):
        self.mappings: Dict[str, int] = {}  # semantic_name -> lane_id (0-7)
        self._register_defaults()

    def _register_defaults(self):
        """Register default semantic mappings."""
        # Common audio channel names
        self.register("kick", 0)
        self.register("snare", 1)
        self.register("hihat", 2)
        self.register("bass", 0)
        self.register("melody", 1)
        self.register("drums", 2)
        self.register("vocals", 3)

        # SNN-specific mappings
        self.register("audio", 0)
        self.register("pulse1", 1)
        self.register("pulse2", 2)
        self.register("env", 3)
        self.register("envelope", 3)

    def register(self, semantic_name: str, lane_id: int):
        """
        Register a semantic name mapping.

        Args:
            semantic_name: Semantic name (e.g., "kick", "snare")
            lane_id: Lane ID (0-7)
        """
        self.mappings[semantic_name.lower()] = lane_id

    def get_lane_id(self, semantic_name: str) -> Optional[int]:
        """
        Get lane ID by semantic name.

        Args:
            semantic_name: Semantic name

        Returns:
            Lane ID (0-7) if found, None otherwise
        """
        return self.mappings.get(semantic_name.lower())

    def get_semantic_names(self, lane_id: int) -> list[str]:
        """
        Get all semantic names mapped to a lane.

        Args:
            lane_id: Lane ID (0-7)

        Returns:
            List of semantic names
        """
        return [name for name, lid in self.mappings.items() if lid == lane_id]

    def list_all(self) -> list[tuple[str, int]]:
        """List all mappings as (semantic_name, lane_id)."""
        return [(name, lid) for name, lid in sorted(self.mappings.items())]


# Global semantic name mapper instance
SEMANTIC_MAPPER = SemanticNameMapper()


# ========== Value Formatting ==========

def format_value(value, max_len: int = 10, precision: int = 2) -> str:
    """
    Format numeric value to fit in max_len characters.

    Args:
        value: Value to format
        max_len: Maximum string length
        precision: Decimal precision

    Returns:
        Formatted string
    """
    if isinstance(value, bool):
        return "T" if value else "F"

    if isinstance(value, int):
        s = str(value)
        return s if len(s) <= max_len else f"{value:.1e}"

    if isinstance(value, float):
        # Try regular format first
        s = f"{value:.{precision}f}"
        if len(s) <= max_len:
            return s

        # Try scientific notation
        s = f"{value:.{precision-1}e}"
        if len(s) <= max_len:
            return s

        # Give up, truncate
        return s[:max_len]

    return str(value)[:max_len]


def format_time_compact(seconds: float, width_ctx: WidthContext) -> str:
    """
    Format time value based on width context.

    Args:
        seconds: Time in seconds
        width_ctx: Width context

    Returns:
        Formatted time string
    """
    if width_ctx.compact:
        # Super compact: 12.3s
        return f"{seconds:.1f}s"
    elif width_ctx.narrow:
        # Narrow: 1:23.4
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}:{secs:04.1f}"
    else:
        # Full: 1:23.456
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}:{secs:06.3f}"


# ========== Layout Helpers ==========

def distribute_width(total: int, sections: list[tuple[str, int, int]]) -> Dict[str, int]:
    """
    Distribute available width among sections with min/max constraints.

    Args:
        total: Total available width
        sections: List of (name, min_width, preferred_width)

    Returns:
        Dict mapping section name to allocated width
    """
    result = {}
    remaining = total

    # First pass: allocate minimums
    for name, min_w, pref_w in sections:
        result[name] = min_w
        remaining -= min_w

    if remaining <= 0:
        return result

    # Second pass: distribute remaining proportionally
    total_pref = sum(max(0, pref - min_w) for name, min_w, pref in sections)

    if total_pref > 0:
        for name, min_w, pref_w in sections:
            extra = pref_w - min_w
            if extra > 0:
                allocated = int(remaining * extra / total_pref)
                result[name] += allocated

    return result
