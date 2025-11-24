"""
Video rendering for tau - compact and expanded modes.
"""

import curses
from typing import List, Optional
from .helpers import safe_addstr


def render_video_compact(scr, video_lane: 'VideoLane', transport: 'Transport', layout, label: str = "", color: int = 5):
    """
    Render video in compact mode (4x4 ASCII thumbnail in lane).

    Args:
        scr: curses screen
        video_lane: VideoLane instance
        transport: Transport for current time
        layout: Layout object with y, x, h, w
        label: Lane label
        color: Color pair
    """
    # Get current frame
    frame = video_lane.get_frame_at_time(transport.position)

    if not frame:
        # No frame available
        safe_addstr(scr, layout.y, layout.x, f"{label} [no video]", curses.A_DIM)
        return

    # Render label on first line
    if label:
        safe_addstr(scr, layout.y, layout.x, label, curses.color_pair(color) | curses.A_BOLD)

    # Render frame (centered if possible)
    frame_width = len(frame[0]) if frame else 0
    frame_height = len(frame)

    # Calculate centering
    available_height = layout.h - 1  # Leave room for label
    start_y = layout.y + 1 + max(0, (available_height - frame_height) // 2)
    start_x = layout.x + max(0, (layout.w - frame_width) // 2)

    # Render each line of ASCII frame
    for i, line in enumerate(frame):
        y = start_y + i
        if y >= layout.y + layout.h:
            break  # Clip to layout bounds
        safe_addstr(scr, y, start_x, line, curses.color_pair(color))

    # Show position indicator
    if video_lane.metadata:
        duration = video_lane.metadata.duration
        pct = (transport.position / duration * 100) if duration > 0 else 0
        time_str = f"{transport.position:.1f}s/{duration:.1f}s ({pct:.0f}%)"
        safe_addstr(scr, layout.y + layout.h - 1, layout.x, time_str, curses.A_DIM)


def render_video_expanded(scr, frame: List[str], y: int, x: int, width: int, height: int, color: int = 5):
    """
    Render expanded video frame (for popup viewer).

    Args:
        scr: curses screen
        frame: ASCII frame (list of lines)
        y: Top position
        x: Left position
        width: Popup width
        height: Popup height
        color: Color pair
    """
    if not frame:
        return

    # Center frame in popup
    frame_width = len(frame[0]) if frame else 0
    frame_height = len(frame)

    start_y = y + max(0, (height - frame_height) // 2)
    start_x = x + max(0, (width - frame_width) // 2)

    # Render each line
    for i, line in enumerate(frame):
        line_y = start_y + i
        if line_y >= y + height:
            break
        safe_addstr(scr, line_y, start_x, line[:width], curses.color_pair(color))


def frame_to_ascii_stippled(frame, width: int, height: int) -> List[str]:
    """
    Convert video frame to stippled ASCII art using dithering.

    Args:
        frame: OpenCV frame (BGR)
        width: Target width
        height: Target height

    Returns:
        List of ASCII lines
    """
    import cv2
    import numpy as np

    # Resize to target resolution
    resized = cv2.resize(frame, (width, height))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    # Extended ASCII character set (dark to light)
    # Using gradual brightness ramp
    chars = " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"

    # Simple Floyd-Steinberg dithering for better quality
    # Clone to float for error diffusion
    img_float = gray.astype(np.float32)

    ascii_art = []
    for y_pos in range(height):
        row = []
        for x_pos in range(width):
            old_val = img_float[y_pos, x_pos]
            # Map to character
            char_idx = int(old_val / 255 * (len(chars) - 1))
            char_idx = max(0, min(len(chars) - 1, char_idx))
            row.append(chars[char_idx])

            # Floyd-Steinberg error diffusion
            new_val = (char_idx / (len(chars) - 1)) * 255
            error = old_val - new_val

            # Diffuse error to neighbors
            if x_pos + 1 < width:
                img_float[y_pos, x_pos + 1] += error * 7 / 16
            if y_pos + 1 < height:
                if x_pos > 0:
                    img_float[y_pos + 1, x_pos - 1] += error * 3 / 16
                img_float[y_pos + 1, x_pos] += error * 5 / 16
                if x_pos + 1 < width:
                    img_float[y_pos + 1, x_pos + 1] += error * 1 / 16

        ascii_art.append(''.join(row))

    return ascii_art
