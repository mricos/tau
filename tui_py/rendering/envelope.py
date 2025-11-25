"""
Envelope rendering for ASCII Scope SNN.
Draws min/max envelopes for fast rendering of dense data.
"""

import curses
from typing import List, Tuple
from tui_py.rendering.helpers import map_to_row, safe_addch


DIGITAL_LAST = False  # Treat last channel as digital (binary)


def render_envelope(
    scr,
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float,
    channels,  # ChannelManager
    display_h: int
):
    """
    Render envelope view for all visible channels.

    Args:
        scr: curses screen
        data_buffer: [(time, [values])]
        left_t, right_t: Time window
        channels: ChannelManager instance
        display_h: Display height
    """
    h, w = scr.getmaxyx()
    cols = max(2, w - 2)
    span = max(1e-12, right_t - left_t)

    for ch in channels.all_visible():
        ci = ch.id
        attr = curses.color_pair(ch.color)

        # Initialize min/max arrays for each column
        ymin = [None] * cols
        ymax = [None] * cols

        # Collect data points
        for t, vs in data_buffer:
            if t < left_t or t > right_t:
                continue
            if ci >= len(vs):
                continue

            # Map time to column
            xf = (cols - 1) * (t - left_t) / span
            x = int(round(xf))
            if x < 0 or x >= cols:
                continue

            # Apply channel gain and offset
            yv = ch.gain * vs[ci] + ch.offset

            # Digital mode for last channel (optional)
            if DIGITAL_LAST and ci == 3:
                yv = 0.8 if yv >= 0.5 else -0.8

            # Map to row
            y = map_to_row(yv, 0, ci, display_h)  # offset already in yv

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
            screen_x = 1 + x

            if y0 == y1:
                # Single point
                safe_addch(scr, y0, screen_x, ord('*'), attr)
            else:
                # Vertical line
                step = 1 if y1 >= y0 else -1
                for ry in range(y0, y1 + step, step):
                    safe_addch(scr, ry, screen_x, ord('|'), attr)
