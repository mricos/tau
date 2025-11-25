"""
Points rendering for ASCII Scope SNN.
Draws individual points with interpolation for detailed view.
"""

import curses
from typing import List, Tuple
from tui_py.rendering.helpers import map_to_row, safe_addch


DIGITAL_LAST = False  # Treat last channel as digital


def render_points(
    scr,
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float,
    channels,  # ChannelManager
    display_h: int
):
    """
    Render points view with interpolation.

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        channels: ChannelManager instance
        display_h: Display height
    """
    h, w = scr.getmaxyx()
    span = max(1e-12, right_t - left_t)

    for ch in channels.all_visible():
        ci = ch.id
        attr = curses.color_pair(ch.color)

        last_x = None
        last_y = None

        for t, vs in data_buffer:
            if t < left_t or t > right_t:
                continue
            if ci >= len(vs):
                continue

            # Map time to column
            xf = 1 + (w - 2) * (t - left_t) / span
            x = int(round(xf))
            if x < 1 or x >= w - 1:
                continue

            # Apply channel gain and offset
            yv = ch.gain * vs[ci] + ch.offset

            # Digital mode for last channel (optional)
            if DIGITAL_LAST and ci == 3:
                yv = 0.8 if yv >= 0.5 else -0.8

            # Map to row
            y = map_to_row(yv, 0, ci, display_h)  # offset already in yv

            # Draw point
            safe_addch(scr, y, x, ord('*'), attr)

            # Interpolate between points
            if last_x is not None and x > last_x:
                dx = x - last_x
                dy = y - last_y

                for i in range(1, dx):
                    xi = last_x + i
                    yi = last_y + (dy * i) // dx
                    safe_addch(scr, yi, xi, ord('.'), attr)

            last_x, last_y = x, y
