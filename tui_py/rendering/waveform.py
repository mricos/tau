"""
Waveform rendering for expanded lane view.
Consolidates envelope and points rendering for single-lane display.
Uses binary search for efficient visible data lookup.
"""

import curses
from typing import List, Tuple
from tui_py.rendering.helpers import safe_addch, safe_addstr
from tui_py.rendering.data_view import get_visible_slice


def render_waveform_envelope(
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
    Render waveform in envelope mode (min/max bars) for a single lane.

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        lane_layout: LaneLayout with y, x, h, w
        channel_id: Which data column to render
        color: Curses color pair
        gain: Amplitude multiplier
        label: Lane label (e.g., "[1:audio]")
        clip_name: Clip name (max 16 chars)
    """
    y_start = lane_layout.y
    x_start = lane_layout.x
    height = lane_layout.h
    width = lane_layout.w

    # Fill background first to avoid patchy rendering (use default colors, no custom bg)
    for row in range(height):
        for col in range(width):
            safe_addch(scr, lane_layout.y + row, lane_layout.x + col, ord(' '), 0)

    # Add padding: 1 line top/bottom, 1 column left/right
    PADDING_V = 1  # Vertical padding
    PADDING_H = 1  # Horizontal padding

    y_start += PADDING_V
    x_start += PADDING_H
    height = max(1, height - 2 * PADDING_V)
    width = max(2, width - 2 * PADDING_H)

    # Use available width minus additional rendering padding
    cols = max(2, width - 2)
    span = max(1e-12, right_t - left_t)

    attr = curses.color_pair(color)

    # Initialize min/max arrays for each column
    ymin = [None] * cols
    ymax = [None] * cols

    # Center line for zero reference
    mid_row = y_start + height // 2

    # Get visible slice using binary search - O(log n)
    visible = get_visible_slice(data_buffer, left_t, right_t)

    # Collect data points
    for t, vals in visible:
        if channel_id >= len(vals):
            continue

        # Map time to column
        xf = (cols - 1) * (t - left_t) / span
        x = int(round(xf))
        if x < 0 or x >= cols:
            continue

        # Apply gain
        val = vals[channel_id] * gain

        # Map to screen row (centered in lane)
        scale = height * 0.4  # Use 40% of height for scaling
        y = int(mid_row - val * scale)

        # Clamp to lane bounds
        y = max(y_start, min(y_start + height - 1, y))

        # Update min/max
        if ymin[x] is None or y < ymin[x]:
            ymin[x] = y
        if ymax[x] is None or y > ymax[x]:
            ymax[x] = y

    # Draw envelopes
    for x in range(cols):
        y0 = ymin[x]
        if y0 is None:
            continue

        y1 = ymax[x] if ymax[x] is not None else y0
        screen_x = x_start + 1 + x

        if y0 == y1:
            # Single point
            safe_addch(scr, y0, screen_x, ord('*'), attr)
        else:
            # Vertical line from min to max
            step = 1 if y1 >= y0 else -1
            for ry in range(y0, y1 + step, step):
                safe_addch(scr, ry, screen_x, ord('|'), attr)

    # Draw center line (zero reference) - skip for now as it causes rendering issues
    # for x in range(1, cols, 4):  # Draw every 4th character
    #     safe_addch(scr, mid_row, x_start + 1 + x, ord('─'), curses.A_DIM)

    # Superimpose signal name (label) at start and end only
    if label:
        overlay_y = lane_layout.y + PADDING_V  # Top of actual waveform area (after padding)

        # Draw label at start
        safe_addstr(scr, overlay_y, x_start, label,
                   curses.A_BOLD | curses.color_pair(color))

        # Draw label at end (right-aligned)
        overlay_x_end = x_start + width - len(label)
        if overlay_x_end > x_start + len(label) + 5:  # Only if there's enough space
            safe_addstr(scr, overlay_y, overlay_x_end, label,
                       curses.A_BOLD | curses.color_pair(color))

    # Superimpose clip name (file/data reference) - smaller, dimmed, in corner
    if clip_name:
        overlay_y = lane_layout.y  # Very top of lane (before padding)
        overlay_x = width - 20  # Top-right corner
        clip_truncated = clip_name[:16]
        safe_addstr(scr, overlay_y, overlay_x, clip_truncated,
                   curses.A_DIM | curses.color_pair(color))


def render_waveform_points(
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
    Render waveform in points mode (individual points with interpolation).

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        lane_layout: LaneLayout with y, x, h, w
        channel_id: Which data column to render
        color: Curses color pair
        gain: Amplitude multiplier
        label: Lane label (e.g., "[1:audio]")
        clip_name: Clip name (max 16 chars)
    """
    y_start = lane_layout.y
    x_start = lane_layout.x
    height = lane_layout.h
    width = lane_layout.w

    # Fill background first to avoid patchy rendering (use default colors, no custom bg)
    for row in range(height):
        for col in range(width):
            safe_addch(scr, lane_layout.y + row, lane_layout.x + col, ord(' '), 0)

    # Add padding: 1 line top/bottom, 1 column left/right
    PADDING_V = 1  # Vertical padding
    PADDING_H = 1  # Horizontal padding

    y_start += PADDING_V
    x_start += PADDING_H
    height = max(1, height - 2 * PADDING_V)
    width = max(2, width - 2 * PADDING_H)

    span = max(1e-12, right_t - left_t)
    attr = curses.color_pair(color)

    # Center line for zero reference
    mid_row = y_start + height // 2

    # Get visible slice using binary search - O(log n)
    visible = get_visible_slice(data_buffer, left_t, right_t)

    last_x = None
    last_y = None

    for t, vals in visible:
        if channel_id >= len(vals):
            continue

        # Map time to column
        xf = (width - 2) * (t - left_t) / span
        x = int(round(xf))
        if x < 0 or x >= width - 2:
            continue

        # Apply gain
        val = vals[channel_id] * gain

        # Map to screen row (centered in lane)
        scale = height * 0.4
        y = int(mid_row - val * scale)

        # Clamp to lane bounds
        y = max(y_start, min(y_start + height - 1, y))

        screen_x = x_start + 1 + x

        # Draw point
        safe_addch(scr, y, screen_x, ord('*'), attr)

        # Interpolate between points
        if last_x is not None and x > last_x:
            dx = x - last_x
            dy = y - last_y

            for i in range(1, dx):
                xi = x_start + 1 + last_x + i
                yi = last_y + (dy * i) // dx
                safe_addch(scr, yi, xi, ord('.'), attr)

        last_x, last_y = x, y

    # Draw center line (zero reference) - skip for now as it causes rendering issues
    # for x in range(1, width - 2, 4):
    #     safe_addch(scr, mid_row, x_start + 1 + x, ord('─'), curses.A_DIM)

    # Superimpose signal name (label) at start and end only
    if label:
        overlay_y = lane_layout.y + PADDING_V  # Top of actual waveform area (after padding)

        # Draw label at start
        safe_addstr(scr, overlay_y, x_start, label,
                   curses.A_BOLD | curses.color_pair(color))

        # Draw label at end (right-aligned)
        overlay_x_end = x_start + width - len(label)
        if overlay_x_end > x_start + len(label) + 5:  # Only if there's enough space
            safe_addstr(scr, overlay_y, overlay_x_end, label,
                       curses.A_BOLD | curses.color_pair(color))

    # Superimpose clip name (file/data reference) - smaller, dimmed, in corner
    if clip_name:
        overlay_y = lane_layout.y  # Very top of lane (before padding)
        overlay_x = width - 20  # Top-right corner
        clip_truncated = clip_name[:16]
        safe_addstr(scr, overlay_y, overlay_x, clip_truncated,
                   curses.A_DIM | curses.color_pair(color))


def render_waveform(
    scr,
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float,
    lane_layout,
    channel_id: int,
    color: int,
    gain: float = 1.0,
    mode: str = "envelope"
):
    """
    Render waveform in specified mode.

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        lane_layout: LaneLayout
        channel_id: Which data column
        color: Curses color pair
        gain: Amplitude multiplier
        mode: "envelope" or "points"
    """
    if mode == "envelope":
        render_waveform_envelope(scr, data_buffer, left_t, right_t,
                                 lane_layout, channel_id, color, gain)
    else:  # points
        render_waveform_points(scr, data_buffer, left_t, right_t,
                               lane_layout, channel_id, color, gain)
