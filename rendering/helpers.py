"""
Rendering helper functions for ASCII Scope SNN.
"""

import curses
import math


# ========== Constants ==========

SIGNAL_HEIGHT = 8  # Rows per channel


# ========== Value Mapping ==========

def map_to_row(val: float, channel_offset: float, channel_index: int, display_h: int) -> int:
    """
    Map value to screen row with oscilloscope-style offset.

    Args:
        val: Value to map
        channel_offset: Vertical offset for this channel
        channel_index: Channel index (0-3)
        display_h: Total display height

    Returns:
        Screen row (y coordinate)
    """
    gap = 1
    y_start = 1 + channel_index * (SIGNAL_HEIGHT + gap)
    mid = y_start + SIGNAL_HEIGHT // 2

    # Apply channel offset (oscilloscope style)
    adjusted_val = val + channel_offset

    scale = SIGNAL_HEIGHT * 0.4
    y = int(mid - adjusted_val * scale)

    # Clamp to channel bounds
    y = max(y_start, min(y_start + SIGNAL_HEIGHT - 1, y))

    return y


# ========== Formatting ==========

def format_tau(tau_sec: float) -> str:
    """Format tau in ms or μs."""
    if tau_sec >= 0.001:
        return f"{tau_sec*1000:.2f}ms"
    else:
        return f"{tau_sec*1e6:.1f}μs"


def compute_fc(tau_a: float, tau_r: float) -> float:
    """
    Compute pseudo center frequency from tau_a and tau_r.

    f_c ≈ 1 / (2π√(τ_a × τ_r))
    """
    return 1.0 / (2.0 * math.pi * math.sqrt(tau_a * tau_r))


def format_time(seconds: float) -> str:
    """Format time as MM:SS.mmm."""
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins}:{secs:06.3f}"


# ========== Color Management ==========

def init_colors():
    """
    Initialize curses color pairs with TDS theme support.

    12-Color System:
    - Pairs 1-8: Data colors (lanes/waveforms)
    - Pairs 9-12: Status/UI colors (success, warning, error, info)
    - Pair 0: Background (terminal default)
    """
    if not curses.has_colors():
        return

    curses.start_color()
    curses.use_default_colors()

    # Try to load TDS theme
    from ..palette import ColorPalette, find_tds_theme

    palette = ColorPalette()
    theme_path = find_tds_theme("warm")

    if theme_path and palette.load_tds_theme(theme_path):
        # Apply TDS theme colors (12 pairs total)
        palette.apply_to_curses()
    else:
        # Fallback: standard terminal colors with dark-dark-gray background
        # Define dark-dark-gray background if terminal supports color changes
        DARK_GRAY_SLOT = 30

        # Try to set up dark gray background
        if curses.can_change_color():
            # RGB: 26, 26, 26 (very dark gray)
            curses.init_color(DARK_GRAY_SLOT, 102, 102, 102)
            bg_color = DARK_GRAY_SLOT
        else:
            # Terminal can't change colors - use standard COLOR_BLACK
            # This is better than -1 (terminal default) which may be pure black
            bg_color = curses.COLOR_BLACK

        # Data colors (1-8)
        color_map = {
            1: curses.COLOR_YELLOW,   # Lane 1
            2: curses.COLOR_GREEN,    # Lane 2
            3: curses.COLOR_RED,      # Lane 3
            4: curses.COLOR_BLUE,     # Lane 4
            5: curses.COLOR_MAGENTA,  # Lane 5
            6: curses.COLOR_CYAN,     # Lane 6
            7: curses.COLOR_WHITE,    # Lane 7
            8: curses.COLOR_WHITE,    # Lane 8
            # Status colors (9-12)
            9: curses.COLOR_GREEN,    # SUCCESS
            10: curses.COLOR_YELLOW,  # WARNING
            11: curses.COLOR_RED,     # ERROR
            12: curses.COLOR_CYAN,    # INFO
        }

        for pair_num, fg_color in color_map.items():
            curses.init_pair(pair_num, fg_color, bg_color)

    # Background: Pair 0 is reserved by curses (terminal default)
    # All UI sections use color_pair(0) for consistent background


def get_channel_color(channel_id: int) -> int:
    """Get color pair for channel."""
    colors = [
        1,  # ch0: red
        2,  # ch1: green
        3,  # ch2: yellow
        4,  # ch3: blue
    ]
    return colors[channel_id] if channel_id < len(colors) else 1


# ========== Drawing Helpers ==========

def safe_addstr(scr, y: int, x: int, text: str, attr=0, max_width: int = None):
    """Safely add string to screen (handles out-of-bounds)."""
    try:
        h, w = scr.getmaxyx()
        if y < 0 or y >= h or x < 0 or x >= w:
            return

        if max_width:
            text = text[:max_width]

        # Truncate if too long
        available = w - x
        if len(text) > available:
            text = text[:available]

        scr.addnstr(y, x, text, available, attr)
    except curses.error:
        pass


def safe_addch(scr, y: int, x: int, ch, attr=0):
    """Safely add character to screen."""
    try:
        h, w = scr.getmaxyx()
        if 0 <= y < h and 0 <= x < w:
            scr.addch(y, x, ch, attr)
    except curses.error:
        pass


def draw_box(scr, y: int, x: int, height: int, width: int, title: str = "", attr=0):
    """Draw a box with optional title."""
    # Top border
    safe_addch(scr, y, x, ord('┌'), attr)
    for i in range(1, width - 1):
        safe_addch(scr, y, x + i, ord('─'), attr)
    safe_addch(scr, y, x + width - 1, ord('┐'), attr)

    # Title
    if title:
        safe_addstr(scr, y, x + 2, f" {title} ", attr)

    # Sides
    for i in range(1, height - 1):
        safe_addch(scr, y + i, x, ord('│'), attr)
        safe_addch(scr, y + i, x + width - 1, ord('│'), attr)

    # Bottom border
    safe_addch(scr, y + height - 1, x, ord('└'), attr)
    for i in range(1, width - 1):
        safe_addch(scr, y + height - 1, x + i, ord('─'), attr)
    safe_addch(scr, y + height - 1, x + width - 1, ord('┘'), attr)


# ========== Progress Bar ==========

def draw_progress_bar(scr, y: int, x: int, width: int, progress: float, attr=0):
    """
    Draw a progress bar.

    Args:
        scr: curses screen
        y, x: Position
        width: Bar width in characters
        progress: 0.0 to 1.0
        attr: curses attributes
    """
    filled = int(width * progress)
    filled = max(0, min(width, filled))

    bar = '█' * filled + '░' * (width - filled)
    safe_addstr(scr, y, x, bar, attr)
