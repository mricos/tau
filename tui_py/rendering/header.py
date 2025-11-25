"""
Header rendering module for ASCII Scope SNN.
Provides a clean API for rendering the two-row header with transport and lane status.
Uses color palette for themed rendering.
"""

import curses
from typing import TYPE_CHECKING
from tui_py.rendering.helpers import safe_addstr

if TYPE_CHECKING:
    from tau_lib.core.state import AppState


# Header color scheme (curses color pair indices)
# 12-Color System: 1-8 data, 9-12 status (SUCCESS/WARNING/ERROR/INFO)
COLOR_TRANSPORT = 4         # Transport controls (MODE palette - orange)
COLOR_LANE_VIS = 3          # Visible lane indicator (MODE palette - orange)
COLOR_LANE_HID = 7          # Hidden lane indicator (NOUNS palette - gray)
COLOR_PRESS_FEEDBACK = 10   # Press duration feedback (WARNING - orange/yellow)
COLOR_TEXT_DIM = 7          # Dimmed text (file paths, etc) - gray
COLOR_SUCCESS = 9           # Success/play state - green
BG = 0                      # Consistent background - terminal default


class HeaderRenderer:
    """Renders the application header with transport controls and lane status."""

    def __init__(self, state: 'AppState'):
        """
        Initialize header renderer.

        Args:
            state: Application state
        """
        self.state = state
        self.height = 2  # Fixed 2-row header

    def render(self, scr, width: int):
        """
        Render the complete 2-row header.

        Args:
            scr: curses screen
            width: Terminal width
        """
        self._render_transport_row(scr, width)
        self._render_lanes_row(scr, width)

    def _render_transport_row(self, scr, width: int):
        """
        Render row 0: Transport controls and playback info.

        Args:
            scr: curses screen
            width: Terminal width
        """
        from tui_py.ui.ui_utils import WidthContext

        # Width context for adaptive rendering
        wctx = WidthContext.from_width(width)

        # Build transport info (tightened up - no help/quit/CLI prompts)
        play_s = "▶PLAY" if self.state.transport.playing else "■STOP"
        pos = self.state.transport.position
        dur = self.state.transport.duration
        pct = (pos / dur * 100) if dur > 0 else 0

        if wctx.compact:
            # Ultra-compact for 80 columns
            transport_sec = f"[{play_s}] {pos:.1f}s/{dur:.1f}s z={self.state.transport.span:.2f}s"
        elif wctx.narrow:
            transport_sec = f"[{play_s}] {pos:.2f}s/{dur:.2f}s ({pct:.0f}%) zoom={self.state.transport.span:.2f}s"
        else:
            transport_sec = f"[{play_s}] {pos:.3f}s/{dur:.3f}s ({pct:.0f}%) zoom={self.state.transport.span:.3f}s"

        # Build lane indicators - show only most recent 2 selections
        from tui_py.content.lanes import LaneDisplayMode
        lane_ind = ""
        recent_lane_ids = self.state.lanes.get_recent_selections()

        mode_markers = {
            LaneDisplayMode.HIDDEN: "○",
            LaneDisplayMode.COMPACT: "c",
            LaneDisplayMode.FULL: "●"
        }

        for lane_id in recent_lane_ids:
            lane = self.state.lanes.get_lane(lane_id)
            if lane:
                marker = mode_markers.get(lane.display_mode, "?")
                display_num = lane_id
                lane_ind += f"[{display_num}:{marker}] "

        # Draw with theme colors (consistent background)
        x_pos = 0

        # Transport section (theme accent color) - no help/quit/CLI
        safe_addstr(scr, 0, x_pos, transport_sec, curses.color_pair(COLOR_TRANSPORT))
        x_pos += len(transport_sec)

        # Calculate right-aligned lane indicators position
        lane_ind_len = len(lane_ind.rstrip())
        if lane_ind_len > 0:
            # Fill middle space
            middle_space = width - x_pos - lane_ind_len
            if middle_space > 0:
                safe_addstr(scr, 0, x_pos, " " * middle_space, curses.color_pair(BG))
                x_pos += middle_space

            # Right-aligned: Lane indicators
            safe_addstr(scr, 0, x_pos, lane_ind.rstrip(),
                       curses.A_DIM | curses.color_pair(BG))
            x_pos += lane_ind_len
        else:
            # No lane indicators - fill rest of line
            remaining = width - x_pos
            if remaining > 0:
                safe_addstr(scr, 0, x_pos, " " * remaining, curses.color_pair(BG))

    def _render_lanes_row(self, scr, width: int):
        """
        Render row 1: File info only (lane indicators moved to row 0).

        Args:
            scr: curses screen
            width: Terminal width
        """
        from tui_py.ui.ui_utils import WidthContext, truncate_middle

        # Width context for adaptive rendering
        wctx = WidthContext.from_width(width)

        # File info (left side, more prominent)
        file_info = ""
        if self.state.data_file:
            if wctx.compact:
                filename = truncate_middle(self.state.data_file, 25)
            else:
                filename = truncate_middle(self.state.data_file, 40)
            file_info = filename

        # Draw row 1 - LEFT: file, RIGHT: CLI info
        x_pos = 0

        # File info (left side, dimmed gray)
        if file_info:
            safe_addstr(scr, 1, x_pos, file_info,
                       curses.A_DIM | curses.color_pair(COLOR_TEXT_DIM))
            x_pos += len(file_info) + 2

        # Fill rest of line
        remaining = width - x_pos
        if remaining > 0:
            safe_addstr(scr, 1, x_pos, " " * remaining, curses.color_pair(BG))

    def get_height(self) -> int:
        """Get header height (always 2 rows)."""
        return self.height


def render_header(scr, state: 'AppState', width: int):
    """
    Convenience function for rendering header.

    Args:
        scr: curses screen
        state: Application state
        width: Terminal width
    """
    renderer = HeaderRenderer(state)
    renderer.render(scr, width)
