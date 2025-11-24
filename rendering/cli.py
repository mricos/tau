"""
CLI prompt and status line rendering.
Provides prompt input area and bottom status line for commands and dynamic status.
"""

import curses
from typing import TYPE_CHECKING
from .helpers import safe_addstr

if TYPE_CHECKING:
    from ..state import AppState


# CLI color scheme (curses color pair indices)
# 12-Color System: 1-8 data, 9-12 status (SUCCESS/WARNING/ERROR/INFO)
COLOR_PROMPT = 9         # Prompt color (SUCCESS - green)
COLOR_INPUT = 1          # Input text color (ENV palette - amber)
COLOR_STATUS = 12        # Status line color (INFO - cyan/blue)
COLOR_ERROR = 11         # Error messages (ERROR - red)
BG = 0                   # Consistent background - terminal default


def render_cli_prompt(scr, y: int, width: int, current_lane_id: int, lane_name: str,
                      input_text: str = "", cursor_pos: int = 0, cli_mode: bool = False,
                      lane_color: int = None):
    """
    Render CLI prompt line with current lane indicator.

    Format: [<lane_id>:<lane_name>] > <input_text>
    Example: [1:audio] > load song.wav

    Args:
        scr: curses screen
        y: Row position
        width: Terminal width
        current_lane_id: Current lane ID (0-9)
        lane_name: Current lane name
        input_text: CLI input text
        cursor_pos: Cursor position in input text
        cli_mode: Whether CLI input mode is active
        lane_color: Color pair for the selected lane (used for cursor)
    """
    # Use lane color for prompt if provided, otherwise use default
    prompt_color = lane_color if lane_color is not None else COLOR_PROMPT

    # Build prompt (indented by 1 column for breathing room)
    prompt = f"[{current_lane_id}:{lane_name}] > "

    # Draw prompt in lane color, indented by 1
    x_pos = 1  # Indent by 1 column
    safe_addstr(scr, y, x_pos, prompt, curses.color_pair(prompt_color))
    x_pos += len(prompt)

    # Draw input text
    if input_text:
        input_display = input_text[:width - x_pos - 1]  # Leave space
        safe_addstr(scr, y, x_pos, input_display, curses.color_pair(COLOR_INPUT))
        x_pos += len(input_display)

    # Fill rest of line with consistent background
    remaining = width - x_pos
    if remaining > 0:
        safe_addstr(scr, y, x_pos, " " * remaining, curses.color_pair(BG))

    # Draw hollow cursor if in CLI mode
    if cli_mode:
        cursor_x = 1 + len(prompt) + cursor_pos  # Account for indent
        # Draw hollow cursor (inverse video of the character at cursor position)
        if cursor_pos < len(input_text):
            char_at_cursor = input_text[cursor_pos]
        else:
            char_at_cursor = ' '

        # Use reverse video with lane color to create hollow cursor effect
        safe_addstr(scr, y, cursor_x, char_at_cursor,
                   curses.A_REVERSE | curses.color_pair(prompt_color))


def render_cli_status(scr, y: int, width: int, status_text: str = ""):
    """
    Render CLI status line at bottom of screen.
    Shows available commands and dynamic status messages.

    Args:
        scr: curses screen
        y: Row position (typically last row)
        width: Terminal width
        status_text: Status/help text to display
    """
    # Default status text if none provided
    if not status_text:
        status_text = "Press ':' for CLI, '?' for help, 'Q' to quit"

    # Truncate if too long (account for 2-column indent)
    display_text = status_text[:width - 3]

    # Draw status with dimmed color, indented by 2 columns
    safe_addstr(scr, y, 2, display_text, curses.A_DIM | curses.color_pair(COLOR_STATUS))

    # Fill rest of line with consistent background
    x_after_text = 2 + len(display_text)
    remaining = width - x_after_text
    if remaining > 0:
        safe_addstr(scr, y, x_after_text, " " * remaining, curses.color_pair(BG))


class CLIRenderer:
    """Manages CLI prompt and status line rendering."""

    def __init__(self, state: 'AppState'):
        """
        Initialize CLI renderer.

        Args:
            state: Application state
        """
        self.state = state
        self.status_text = ""

    def render_prompt(self, scr, y: int, width: int):
        """Render CLI prompt line."""
        current_lane = self.state.lanes.get_lane(self.state.lanes.current_lane_id)
        lane_name = current_lane.name if current_lane else "?"
        lane_color = current_lane.color if current_lane else COLOR_PROMPT

        # Get input text and cursor from CLI manager (attached to state)
        cli = self.state.cli
        input_text = cli.input_buffer if cli.mode else ""
        cursor_pos = cli.cursor_pos if cli.mode else 0

        render_cli_prompt(scr, y, width, self.state.lanes.current_lane_id,
                         lane_name, input_text, cursor_pos, cli.mode, lane_color)

    def render_status(self, scr, y: int, width: int):
        """Render CLI status line."""
        render_cli_status(scr, y, width, self.status_text)

    def set_status(self, text: str):
        """Set status line text."""
        self.status_text = text

    def clear_status(self):
        """Clear status line text."""
        self.status_text = ""

    def render_completions(self, scr, y_start: int, width: int):
        """
        Render completion popup above CLI prompt.

        Args:
            scr: curses screen
            y_start: Starting y position for popup
            width: Terminal width

        Returns:
            int: Number of lines rendered
        """
        cli = self.state.cli

        # Only render if completions are visible
        if not cli.completions_visible or not cli.completion_items:
            return 0

        items = cli.completion_items
        selected_idx = cli.selected_index

        # Calculate height: header + items (max 8) + preview (3 lines)
        max_visible_items = 8
        total_items = len(items)
        preview_height = 3
        header_height = 1

        # Calculate scrolling window to show selected item
        if total_items <= max_visible_items:
            # All items fit - show all
            start_idx = 0
            num_items = total_items
        else:
            # Need scrolling - center selected item in window
            half_window = max_visible_items // 2
            start_idx = max(0, min(selected_idx - half_window, total_items - max_visible_items))
            num_items = max_visible_items

        total_height = header_height + num_items + preview_height

        # Render header with scroll indicator
        scr.move(y_start, 0)
        scr.clrtoeol()
        if total_items > max_visible_items:
            header = f" Matching commands ({len(items)}): [{start_idx+1}-{start_idx+num_items} of {total_items}]"
        else:
            header = f" Matching commands ({len(items)}): "
        safe_addstr(scr, y_start, 1, header, curses.A_BOLD | curses.color_pair(COLOR_STATUS))
        y = y_start + 1

        # Render items (windowed view)
        for i in range(start_idx, start_idx + num_items):
            item = items[i]
            is_selected = (i == selected_idx)

            # Clear the line first to prevent ghosting
            scr.move(y, 0)
            scr.clrtoeol()

            # Format completion line (2-column layout)
            from ..completion import format_completion_line
            line_text = format_completion_line(item, width - 2, is_selected)

            # Choose color based on selection and category
            if is_selected:
                # Selected: green with reverse video
                color_attr = curses.A_REVERSE | curses.color_pair(9)  # SUCCESS green
            else:
                # Normal: use category color
                color_attr = curses.color_pair(item.color)

            # Draw line indented by 1 column
            safe_addstr(scr, y, 1, line_text[:width - 2], color_attr)
            y += 1

        # Blank line before preview
        scr.move(y, 0)
        scr.clrtoeol()
        y += 1

        # Render preview of selected item
        if selected_idx < len(items):
            selected_item = items[selected_idx]

            # Show first few lines of full help
            preview_lines = selected_item.full_help[:preview_height]

            for line in preview_lines:
                # Clear the line first to prevent ghosting
                scr.move(y, 0)
                scr.clrtoeol()
                # Truncate and indent
                display_line = line[:width - 4]
                safe_addstr(scr, y, 2, display_line, curses.A_DIM | curses.color_pair(COLOR_INPUT))
                y += 1

        return total_height
