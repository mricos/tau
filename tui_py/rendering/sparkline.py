"""
Sparkline rendering for compact 1-row lane view.
Uses Unicode block characters ▁▂▃▄▅▆▇█ for mini waveforms.
Enhanced version supports two-row sparklines with foreground/background control.
"""

import curses
from typing import List, Tuple
from tui_py.rendering.helpers import safe_addch, safe_addstr


# Unicode block characters for sparkline (9 levels: space + 8 blocks)
# NOTE: If terminal doesn't support Unicode, these may render as ~ or ?
SPARKLINE_CHARS_UNICODE = " ▁▂▃▄▅▆▇█"

# ASCII fallback for terminals that don't support Unicode (9 levels)
SPARKLINE_CHARS_ASCII = " .':|!I#M"

# Use ASCII fallback by default (safer for most terminals)
SPARKLINE_CHARS = SPARKLINE_CHARS_ASCII

# Half-block characters for two-row rendering
UPPER_HALF_BLOCK = "▀"
LOWER_HALF_BLOCK = "▄"
FULL_BLOCK = "█"


def render_sparkline(
    scr,
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float,
    lane_layout,
    channel_id: int,
    color: int,
    gain: float = 1.0,
    label: str = "",
    clip_name: str = ""
):
    """
    Render compact 1-row sparkline waveform.

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        lane_layout: LaneLayout with y, x, h, w
        channel_id: Which data column to render
        color: Curses color pair
        gain: Amplitude multiplier
        label: Lane label to show (e.g., "[1:audio]")
        clip_name: Clip/file name to show (max 16 chars, dimmed)
    """
    y = lane_layout.y
    x_start = lane_layout.x
    width = lane_layout.w

    # Build full label with clip name if provided
    clip_label = ""
    if clip_name:
        # Truncate clip name to 16 chars
        clip_truncated = clip_name[:16]
        clip_label = f" {clip_truncated}"

    full_label = label + clip_label

    # Reserve space for label
    label_width = len(full_label) + 1
    sparkline_start = x_start + label_width
    sparkline_width = width - label_width - 1  # -1 for padding

    if sparkline_width < 10:
        # Not enough space for sparkline
        safe_addstr(scr, y, x_start, label, curses.color_pair(color))
        return

    # Draw label and clip name (both 80% contrast - no DIM)
    safe_addstr(scr, y, x_start, label, curses.color_pair(color))
    if clip_name:
        safe_addstr(scr, y, x_start + len(label), clip_label, curses.color_pair(color))

    # Sample data across time window
    span = max(1e-12, right_t - left_t)

    # Collect samples binned by screen column
    bins = [[] for _ in range(sparkline_width)]

    for t, vals in data_buffer:
        if t < left_t or t > right_t:
            continue
        if channel_id >= len(vals):
            continue

        # Map time to column
        x_frac = (t - left_t) / span
        col = int(x_frac * sparkline_width)
        if 0 <= col < sparkline_width:
            val = vals[channel_id] * gain
            bins[col].append(val)

    # Find global min/max for normalization
    all_vals = [v for bin_vals in bins if bin_vals for v in bin_vals]
    if not all_vals:
        # No data in window
        safe_addstr(scr, y, sparkline_start, "─" * sparkline_width,
                   curses.A_DIM | curses.color_pair(color))
        return

    global_min = min(all_vals)
    global_max = max(all_vals)
    value_range = global_max - global_min

    # Define color attribute BEFORE any rendering (fixes undefined attr bug)
    attr = curses.color_pair(color)

    # Handle case where all values are the same (e.g., silence or constant pulse)
    if value_range < 1e-9:
        # All values are the same
        # For binary pulse data (all 0s or all 1s), show appropriate level
        if abs(global_max) > 0.5:
            # High signal (e.g., constant pulse = 1)
            char = SPARKLINE_CHARS[-1]  # Full height (█)
        elif abs(global_max) < 0.01:
            # Very low signal (e.g., near-zero constant)
            char = SPARKLINE_CHARS[1]  # Minimal (▁) - NOT space!
        else:
            # Mid-level constant
            char = SPARKLINE_CHARS[len(SPARKLINE_CHARS) // 2]  # Medium (▄)

        for col in range(sparkline_width):
            screen_x = sparkline_start + col
            safe_addch(scr, y, screen_x, ord(char), attr)
        return

    value_range = max(1e-9, value_range)  # Prevent division by zero

    # Render sparkline
    for col, bin_vals in enumerate(bins):
        screen_x = sparkline_start + col

        if not bin_vals:
            # No data in this column - draw baseline
            safe_addch(scr, y, screen_x, ord('─'), curses.A_DIM | attr)
            continue

        # Use absolute peak value (furthest from zero) for sparkline visualization
        # This works well for both bipolar audio and unipolar pulse data
        abs_max = max(abs(v) for v in bin_vals)

        # Handle both bipolar and unipolar signals
        # Use the maximum absolute value in the entire window for normalization
        max_abs = max(abs(global_min), abs(global_max))

        if max_abs < 1e-9:
            # No signal - use lowest non-space character to show "low signal"
            level = 1  # Use ▁ instead of space
        else:
            # Normalize to 0-1 range
            normalized = abs_max / max_abs

            # Map to sparkline character range (1 to len-1) - SKIP index 0 (space)
            # Map 0.0 -> 1, 1.0 -> 8 (using indices 1-8 of 9-char array)
            level = 1 + int(normalized * (len(SPARKLINE_CHARS) - 2))
            level = max(1, min(len(SPARKLINE_CHARS) - 1, level))

        char = SPARKLINE_CHARS[level]
        safe_addch(scr, y, screen_x, ord(char), attr)


def render_sparkline_with_stats(
    scr,
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float,
    lane_layout,
    channel_id: int,
    color: int,
    gain: float = 1.0,
    label: str = "",
    show_value: bool = True
):
    """
    Render sparkline with current value indicator.

    Similar to render_sparkline but also shows current value at playhead.

    Args:
        show_value: If True, show current value on right side
    """
    y = lane_layout.y
    x_start = lane_layout.x
    width = lane_layout.w

    # Reserve space for label and value
    label_width = len(label) + 1
    value_width = 12 if show_value else 0  # " val=+0.523 "
    sparkline_width = width - label_width - value_width - 2

    if sparkline_width < 10:
        # Not enough space
        safe_addstr(scr, y, x_start, label, curses.color_pair(color))
        return

    # Draw label
    safe_addstr(scr, y, x_start, label, curses.A_BOLD | curses.color_pair(color))

    sparkline_start = x_start + label_width

    # Render sparkline (same logic as above)
    span = max(1e-12, right_t - left_t)
    bins = [[] for _ in range(sparkline_width)]

    playhead_val = None  # Track value at playhead

    for t, vals in data_buffer:
        if t < left_t or t > right_t:
            continue
        if channel_id >= len(vals):
            continue

        x_frac = (t - left_t) / span
        col = int(x_frac * sparkline_width)
        if 0 <= col < sparkline_width:
            val = vals[channel_id] * gain
            bins[col].append(val)

            # Track value near playhead (middle of window)
            if abs(x_frac - 0.5) < 0.01:  # Within 1% of center
                playhead_val = val

    # Render sparkline
    all_vals = [v for bin_vals in bins if bin_vals for v in bin_vals]
    if all_vals:
        global_min = min(all_vals)
        global_max = max(all_vals)
        value_range = max(1e-9, global_max - global_min)

        attr = curses.color_pair(color)

        for col, bin_vals in enumerate(bins):
            screen_x = sparkline_start + col

            if not bin_vals:
                safe_addch(scr, y, screen_x, ord('─'), curses.A_DIM | attr)
                continue

            # Use max value in bin to show waveform shape (not absolute)
            max_val = max(bin_vals)
            min_val = min(bin_vals)
            # Use the value furthest from zero to represent the bin
            peak_val = max_val if abs(max_val) > abs(min_val) else min_val

            normalized = (peak_val - global_min) / value_range
            level = int(normalized * (len(SPARKLINE_CHARS) - 1))
            level = max(0, min(len(SPARKLINE_CHARS) - 1, level))

            char = SPARKLINE_CHARS[level]
            safe_addch(scr, y, screen_x, ord(char), attr)

    # Draw current value if requested
    if show_value and playhead_val is not None:
        value_str = f" {playhead_val:+.3f} "
        value_x = width - value_width
        safe_addstr(scr, y, value_x, value_str, curses.A_DIM | curses.color_pair(color))


def render_sparkline_two_row(
    scr,
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float,
    lane_layout,
    channel_id: int,
    color: int,
    bg_color: int = None,
    gain: float = 1.0,
    label: str = "",
    clip_name: str = ""
):
    """
    Render two-row sparkline waveform with foreground/background control.
    Uses upper and lower half-block characters for better resolution.

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        lane_layout: LaneLayout with y, x, h, w (should be at least 2 rows)
        channel_id: Which data column to render
        color: Curses color pair for foreground
        bg_color: Curses color pair for background (default: same as color but dimmed)
        gain: Amplitude multiplier
        label: Lane label to show (e.g., "[1:audio]")
        clip_name: Clip/file name to show (max 16 chars, dimmed)
    """
    y = lane_layout.y
    x_start = lane_layout.x
    width = lane_layout.w
    height = lane_layout.h

    if height < 2:
        # Fall back to single-row sparkline
        render_sparkline(scr, data_buffer, left_t, right_t, lane_layout,
                        channel_id, color, gain, label, clip_name)
        return

    # Build full label with clip name
    clip_label = ""
    if clip_name:
        clip_truncated = clip_name[:16]
        clip_label = f" {clip_truncated}"

    full_label = label + clip_label

    # Reserve space for label
    label_width = len(full_label) + 1
    sparkline_start = x_start + label_width
    sparkline_width = width - label_width - 1

    if sparkline_width < 10:
        # Not enough space
        safe_addstr(scr, y, x_start, label, curses.color_pair(color))
        return

    # Draw label and clip name (both 80% contrast - no DIM)
    safe_addstr(scr, y, x_start, label, curses.color_pair(color))
    if clip_name:
        safe_addstr(scr, y, x_start + len(label), clip_label, curses.color_pair(color))

    # Sample data across time window
    span = max(1e-12, right_t - left_t)

    # Collect samples binned by screen column
    bins = [[] for _ in range(sparkline_width)]

    for t, vals in data_buffer:
        if t < left_t or t > right_t:
            continue
        if channel_id >= len(vals):
            continue

        # Map time to column
        x_frac = (t - left_t) / span
        col = int(x_frac * sparkline_width)
        if 0 <= col < sparkline_width:
            val = vals[channel_id] * gain
            bins[col].append(val)

    # Find global min/max for normalization
    all_vals = [v for bin_vals in bins if bin_vals for v in bin_vals]
    if not all_vals:
        # No data in window - draw baseline
        for row in range(2):
            safe_addstr(scr, y + row, sparkline_start, "─" * sparkline_width,
                       curses.A_DIM | curses.color_pair(color))
        return

    global_min = min(all_vals)
    global_max = max(all_vals)
    value_range = max(1e-9, global_max - global_min)

    # Use background color if provided, otherwise use dimmed foreground
    bg_attr = curses.A_DIM | curses.color_pair(bg_color if bg_color else color)
    fg_attr = curses.color_pair(color)

    # Render two-row sparkline
    # Row 0: upper half of waveform
    # Row 1: lower half of waveform
    for col, bin_vals in enumerate(bins):
        screen_x = sparkline_start + col

        if not bin_vals:
            # No data - draw baseline with background
            safe_addch(scr, y, screen_x, ord('─'), bg_attr)
            safe_addch(scr, y + 1, screen_x, ord('─'), bg_attr)
            continue

        # Get peak value in bin to show waveform shape
        max_val = max(bin_vals)
        min_val = min(bin_vals)
        # Use the value furthest from zero to represent the bin
        peak_val = max_val if abs(max_val) > abs(min_val) else min_val

        # Normalize to 0-1 range
        normalized = (peak_val - global_min) / value_range

        # Map to two rows (0-2 range, where 0=bottom, 2=top)
        level = normalized * 2.0

        # Render based on level
        if level >= 1.5:
            # Full top, full bottom
            safe_addch(scr, y, screen_x, ord(FULL_BLOCK), fg_attr)
            safe_addch(scr, y + 1, screen_x, ord(FULL_BLOCK), fg_attr)
        elif level >= 1.0:
            # Partial top, full bottom
            safe_addch(scr, y, screen_x, ord(LOWER_HALF_BLOCK), fg_attr)
            safe_addch(scr, y + 1, screen_x, ord(FULL_BLOCK), fg_attr)
        elif level >= 0.5:
            # Empty top, full bottom
            safe_addch(scr, y, screen_x, ord(' '), bg_attr)
            safe_addch(scr, y + 1, screen_x, ord(FULL_BLOCK), fg_attr)
        else:
            # Empty top, partial bottom
            safe_addch(scr, y, screen_x, ord(' '), bg_attr)
            safe_addch(scr, y + 1, screen_x, ord(LOWER_HALF_BLOCK), fg_attr)
