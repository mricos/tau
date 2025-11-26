"""
Video rendering for tau - compact and expanded modes with palette support.
"""

import curses
from typing import List, Optional
from tui_py.rendering.helpers import safe_addstr
from tui_py.rendering.video_palettes import frame_to_ascii, PALETTES


def render_video_compact(
    scr,
    video_lane: 'VideoLane',
    transport: 'Transport',
    layout,
    label: str = "",
    color: int = 5,
    palette: str = "simple",
    brightness: float = 0.0,
    contrast: float = 1.0
):
    """
    Render video in compact mode (ASCII thumbnail in lane).

    Args:
        scr: curses screen
        video_lane: VideoLane instance
        transport: Transport for current time
        layout: Layout object with y, x, h, w
        label: Lane label
        color: Color pair
        palette: ASCII palette (simple, extended, braille, blocks)
        brightness: Brightness adjustment (-1.0 to 1.0)
        contrast: Contrast multiplier (0.1 to 3.0)
    """
    # Get current frame from cache
    frame = video_lane.get_frame_at_time(transport.position, palette, brightness, contrast)

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
    available_height = layout.h - 2  # Leave room for label and info
    start_y = layout.y + 1 + max(0, (available_height - frame_height) // 2)
    start_x = layout.x + max(0, (layout.w - frame_width) // 2)

    # Render each line of ASCII frame
    for i, line in enumerate(frame):
        y = start_y + i
        if y >= layout.y + layout.h - 1:
            break  # Clip to layout bounds (leave room for info row)
        safe_addstr(scr, y, start_x, line, curses.color_pair(color))

    # Show compact info in single row (gray/dim)
    _render_compact_info(scr, layout, transport, video_lane, palette, brightness, contrast)


def _render_compact_info(scr, layout, transport, video_lane, palette: str, brightness: float, contrast: float):
    """Render single-row compact video info in gray."""
    if not video_lane.metadata:
        return

    meta = video_lane.metadata
    duration = meta.duration
    pos = transport.position
    pct = (pos / duration * 100) if duration > 0 else 0

    # Compact info: time + palette + adjustments (if non-default)
    info_parts = [f"{pos:.1f}s/{duration:.1f}s ({pct:.0f}%)"]

    # Add palette if not simple
    if palette != "simple":
        info_parts.append(f"[{palette}]")

    # Add adjustments if non-default
    if brightness != 0.0:
        info_parts.append(f"br:{brightness:+.1f}")
    if contrast != 1.0:
        info_parts.append(f"ct:{contrast:.1f}")

    info_str = " ".join(info_parts)

    # Render in dim gray on last row of lane
    info_y = layout.y + layout.h - 1
    safe_addstr(scr, info_y, layout.x, info_str[:layout.w-1], curses.A_DIM)


def render_video_expanded(
    scr,
    frame: List[str],
    y: int,
    x: int,
    width: int,
    height: int,
    color: int = 5
):
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


def render_popup_info(
    scr,
    y: int,
    x: int,
    w: int,
    transport: 'Transport',
    video_lane: 'VideoLane',
    palette: str,
    brightness: float,
    contrast: float
):
    """
    Render single-row video info in popup header (gray).

    Args:
        scr: curses screen
        y: Row for info
        x: Column start
        w: Available width
        transport: Transport state
        video_lane: Video lane
        palette: Current palette name
        brightness: Brightness adjustment
        contrast: Contrast adjustment
    """
    if not video_lane or not video_lane.metadata:
        return

    meta = video_lane.metadata
    duration = meta.duration
    pos = transport.position
    pct = (pos / duration * 100) if duration > 0 else 0

    # Compact info string
    info_parts = [
        f"{meta.path.name}",
        f"{pos:.1f}s/{duration:.1f}s",
        f"({pct:.0f}%)",
        f"{meta.width}x{meta.height}",
        f"{meta.fps:.0f}fps",
        f"[{palette}]"
    ]

    # Add adjustments if non-default
    if brightness != 0.0:
        info_parts.append(f"br:{brightness:+.1f}")
    if contrast != 1.0:
        info_parts.append(f"ct:{contrast:.1f}")

    info_str = " ".join(info_parts)
    info_str = info_str[:w-4]  # Truncate to fit

    # Render centered in dim gray
    info_x = x + (w - len(info_str)) // 2
    safe_addstr(scr, y, info_x, info_str, curses.A_DIM)


def render_popup_controls_hint(scr, y: int, x: int, w: int):
    """Render controls hint in popup footer (single row, gray)."""
    hint = "[V]close [space]play [←→]scrub [+/-]brightness [</>]contrast [p]palette"
    hint = hint[:w-4]
    hint_x = x + (w - len(hint)) // 2
    safe_addstr(scr, y, hint_x, hint, curses.A_DIM)


# Legacy function for compatibility
def frame_to_ascii_stippled(frame, width: int, height: int) -> List[str]:
    """
    Convert video frame to stippled ASCII art using dithering.

    DEPRECATED: Use frame_to_ascii with palette="extended" and dither=True instead.

    Args:
        frame: OpenCV frame (BGR)
        width: Target width
        height: Target height

    Returns:
        List of ASCII lines
    """
    return frame_to_ascii(
        frame,
        width,
        height,
        palette="extended",
        brightness=0.0,
        contrast=1.0,
        dither=True
    )
