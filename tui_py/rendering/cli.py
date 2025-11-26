"""
CLI prompt and status line rendering.
Provides prompt input area and bottom status line for commands and dynamic status.
"""

import curses
from typing import TYPE_CHECKING
from tui_py.rendering.helpers import safe_addstr

if TYPE_CHECKING:
    from tau_lib.core.state import AppState


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

    def render_completions(self, scr, prompt_y: int, width: int):
        """
        Render completion items ABOVE CLI prompt.

        Args:
            scr: curses screen
            prompt_y: Y position of the CLI prompt (items render above this)
            width: Terminal width

        Returns:
            int: Number of lines rendered above prompt
        """
        cli = self.state.cli

        # Only render if completions are visible
        if not cli.completions_visible or not cli.completion_items:
            return 0

        items = cli.completion_items
        selected_idx = cli.selected_index

        # Calculate height: header + items (max 8) - NO preview above
        max_visible_items = 8
        total_items = len(items)
        header_height = 1

        # Calculate scrolling window to show selected item
        if total_items <= max_visible_items:
            start_idx = 0
            num_items = total_items
        else:
            half_window = max_visible_items // 2
            start_idx = max(0, min(selected_idx - half_window, total_items - max_visible_items))
            num_items = max_visible_items

        items_height = header_height + num_items

        # Calculate starting y position (renders upward from prompt)
        y_start = prompt_y - items_height
        if y_start < 2:  # Don't overlap header
            y_start = 2
            available = prompt_y - 2 - header_height
            if available < num_items:
                num_items = max(1, available)
                items_height = header_height + num_items
                y_start = prompt_y - items_height

        # Clear the area above prompt
        max_clear = header_height + max_visible_items
        clear_start = max(2, prompt_y - max_clear)
        for clear_y in range(clear_start, prompt_y):
            scr.move(clear_y, 0)
            scr.clrtoeol()

        y = y_start

        # Render header
        scr.move(y, 0)
        scr.clrtoeol()

        current_cat = cli.current_category
        first_item = items[0] if items else None
        item_type = first_item.type if first_item else "command"

        if item_type == "argument":
            cmd_name = cli.input_buffer.split()[0] if cli.input_buffer.strip() else ""
            header = f" {cmd_name}: arguments"
        elif current_cat:
            if total_items > max_visible_items:
                header = f" ← {current_cat.upper()} ({len(items)}): [{start_idx+1}-{start_idx+num_items} of {total_items}]"
            else:
                header = f" ← {current_cat.upper()} ({len(items)} commands)"
        elif item_type == "category":
            if total_items > max_visible_items:
                header = f" Categories ({len(items)}): [{start_idx+1}-{start_idx+num_items} of {total_items}]"
            else:
                header = f" Categories ({len(items)}): [↑↓ nav, Tab expand]"
        else:
            if total_items > max_visible_items:
                header = f" Commands ({len(items)}): [{start_idx+1}-{start_idx+num_items} of {total_items}]"
            else:
                header = f" Commands ({len(items)})"
        safe_addstr(scr, y, 1, header, curses.A_BOLD | curses.color_pair(COLOR_STATUS))
        y += 1

        # Render items
        for i in range(start_idx, start_idx + num_items):
            item = items[i]
            is_selected = (i == selected_idx)

            scr.move(y, 0)
            scr.clrtoeol()

            from tui_py.ui.completion import format_completion_line
            line_text = format_completion_line(item, width - 2, is_selected)

            if is_selected:
                color_attr = curses.A_REVERSE | curses.color_pair(9)
            else:
                color_attr = curses.color_pair(item.color)

            safe_addstr(scr, y, 1, line_text[:width - 2], color_attr)
            y += 1

        return items_height

    def render_completion_preview(self, scr, y_start: int, width: int):
        """
        Render one-line status for selected completion BELOW the prompt.

        Args:
            scr: curses screen
            y_start: Y position to render
            width: Terminal width

        Returns:
            int: Number of lines rendered (always 1 or 0)
        """
        cli = self.state.cli

        if not cli.completions_visible or not cli.completion_items:
            return 0

        selected_idx = cli.selected_index
        if selected_idx >= len(cli.completion_items):
            return 0

        item = cli.completion_items[selected_idx]

        # Build one-liner based on item type
        if item.type == "category":
            status = f"{item.text}: {item.command_count} commands"
        elif item.type == "command":
            # Show usage or description
            status = item.description
        else:
            # Arguments - show the description
            status = item.description

        scr.move(y_start, 0)
        scr.clrtoeol()
        safe_addstr(scr, y_start, 2, status[:width - 4], curses.A_DIM | curses.color_pair(COLOR_STATUS))

        return 1
