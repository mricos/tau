"""
Rendering for pinned text lanes.
Displays static text content that doesn't scroll with transport.
"""

import curses
from typing import List
from .helpers import safe_addstr


def render_pinned_compact(
    scr,
    content: List[str],
    lane_layout,
    color: int,
    label: str = "",
    clip_name: str = ""
):
    """
    Render pinned content in compact mode (1 line, sparkline-style).

    Args:
        scr: curses screen
        content: Lines of text content
        lane_layout: LaneLayout with y, x, h, w
        color: Curses color pair
        label: Lane label to show
        clip_name: Clip/file name to show (max 16 chars, dimmed)
    """
    y = lane_layout.y
    x_start = lane_layout.x
    width = lane_layout.w

    # Build full label with clip name if provided
    clip_label = ""
    if clip_name:
        clip_truncated = clip_name[:16]
        clip_label = f" {clip_truncated}"

    full_label = label + clip_label

    # Build display line
    label_width = len(full_label) + 1
    content_width = width - label_width - 1

    # Draw label and clip name (both 80% contrast - no DIM)
    safe_addstr(scr, y, x_start, label, curses.color_pair(color))
    if clip_name:
        safe_addstr(scr, y, x_start + len(label), clip_label, curses.color_pair(color))

    # Show first line of content (or preview)
    if content:
        # Join all lines with " | " and truncate
        preview = " | ".join(line.strip() for line in content if line.strip())
        preview = preview[:content_width]
        safe_addstr(scr, y, x_start + label_width, preview, curses.color_pair(color))
    else:
        # No content
        safe_addstr(scr, y, x_start + label_width, "(empty)", curses.A_DIM | curses.color_pair(color))


def render_pinned_expanded(
    scr,
    content: List[str],
    lane_layout,
    color: int,
    label: str = "",
    clip_name: str = "",
    content_colors: List[int] = None
):
    """
    Render pinned content in expanded mode (full height panel).

    Args:
        scr: curses screen
        content: Lines of text content
        lane_layout: LaneLayout with y, x, h, w (and optional content_indent)
        color: Curses color pair (default for label)
        label: Lane label to show
        clip_name: Clip name to show prominently
        content_colors: Optional list of color pairs for each content line
    """
    y_start = lane_layout.y
    x_start = lane_layout.x
    height = lane_layout.h
    width = lane_layout.w

    # Check for content indent (default to 0 if not specified)
    content_indent = getattr(lane_layout, 'content_indent', 0)

    attr = curses.color_pair(color)

    # Draw label and clip name on first line
    safe_addstr(scr, y_start, x_start, label, curses.A_BOLD | attr)
    if clip_name:
        clip_x = x_start + len(label) + 1
        safe_addstr(scr, y_start, clip_x, clip_name[:16], curses.A_BOLD | attr)

    # Draw content lines (skip first row for label)
    if height > 1 and content:
        # Show last N lines that fit in the expanded height
        visible_lines = height - 1  # -1 for label row
        start_idx = max(0, len(content) - visible_lines)

        for i, line in enumerate(content[start_idx:]):
            if i >= visible_lines:
                break
            y = y_start + 1 + i
            # Content x position includes additional indent
            content_x = x_start + content_indent
            # Truncate line to fit width (accounting for content indent)
            display_line = line[:width - content_indent - 1]

            # Use content-specific color if available, otherwise use default
            line_idx = start_idx + i
            if content_colors and line_idx < len(content_colors):
                line_color = content_colors[line_idx]
                line_attr = curses.color_pair(line_color) if line_color > 0 else attr
            else:
                line_attr = attr

            safe_addstr(scr, y, content_x, display_line, line_attr)
    elif height > 1:
        # No content - show message
        content_x = x_start + content_indent
        safe_addstr(scr, y_start + 1, content_x, "(empty)", curses.A_DIM | attr)
