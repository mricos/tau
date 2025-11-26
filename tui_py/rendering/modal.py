"""
Modal dialog system for tau TUI.
Provides stylized overlays with text input, buttons, and content display.
"""

import curses
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Any
from enum import Enum, auto
from tui_py.rendering.helpers import safe_addstr


class ModalType(Enum):
    """Types of modal dialogs."""
    INFO = auto()       # Information display only
    CONFIRM = auto()    # Yes/No confirmation
    INPUT = auto()      # Text input
    SELECT = auto()     # Select from list
    CUSTOM = auto()     # Custom content


@dataclass
class ModalButton:
    """A button in a modal dialog."""
    label: str
    action: str  # Action identifier returned on press
    is_default: bool = False
    is_cancel: bool = False


@dataclass
class ModalState:
    """State for modal dialogs."""
    visible: bool = False
    modal_type: ModalType = ModalType.INFO
    title: str = ""
    content: List[str] = field(default_factory=list)
    buttons: List[ModalButton] = field(default_factory=list)
    selected_button: int = 0

    # For INPUT type
    input_buffer: str = ""
    input_cursor: int = 0
    input_label: str = ""
    input_placeholder: str = ""

    # For SELECT type
    options: List[str] = field(default_factory=list)
    selected_option: int = 0

    # Styling
    width_pct: float = 0.6  # Percentage of screen width
    height_pct: float = 0.5  # Max percentage of screen height
    min_width: int = 40
    min_height: int = 10
    border_style: str = "double"  # "single", "double", "rounded", "heavy"

    # Callback
    on_close: Optional[Callable[[str, Any], None]] = None

    def show(self, modal_type: ModalType, title: str, content: List[str] = None,
             buttons: List[ModalButton] = None, **kwargs):
        """Show the modal with specified content."""
        self.visible = True
        self.modal_type = modal_type
        self.title = title
        self.content = content or []
        self.buttons = buttons or [ModalButton("OK", "ok", is_default=True)]
        self.selected_button = 0

        # Reset input state
        self.input_buffer = kwargs.get('default_value', '')
        self.input_cursor = len(self.input_buffer)
        self.input_label = kwargs.get('input_label', '')
        self.input_placeholder = kwargs.get('placeholder', '')

        # Reset select state
        self.options = kwargs.get('options', [])
        self.selected_option = kwargs.get('default_option', 0)

        # Styling overrides
        if 'width_pct' in kwargs:
            self.width_pct = kwargs['width_pct']
        if 'height_pct' in kwargs:
            self.height_pct = kwargs['height_pct']

        self.on_close = kwargs.get('on_close')

    def hide(self):
        """Hide the modal."""
        self.visible = False

    def close(self, action: str, value: Any = None):
        """Close modal and trigger callback."""
        self.visible = False
        if self.on_close:
            self.on_close(action, value)

    def get_result(self) -> Any:
        """Get the current result value based on modal type."""
        if self.modal_type == ModalType.INPUT:
            return self.input_buffer
        elif self.modal_type == ModalType.SELECT:
            if 0 <= self.selected_option < len(self.options):
                return self.options[self.selected_option]
        return None

    # Input handling
    def handle_char(self, char: str):
        """Handle character input for INPUT type."""
        if self.modal_type != ModalType.INPUT:
            return
        self.input_buffer = (
            self.input_buffer[:self.input_cursor] +
            char +
            self.input_buffer[self.input_cursor:]
        )
        self.input_cursor += 1

    def handle_backspace(self):
        """Handle backspace in input."""
        if self.modal_type != ModalType.INPUT or self.input_cursor == 0:
            return
        self.input_buffer = (
            self.input_buffer[:self.input_cursor - 1] +
            self.input_buffer[self.input_cursor:]
        )
        self.input_cursor -= 1

    def handle_delete(self):
        """Handle delete in input."""
        if self.modal_type != ModalType.INPUT:
            return
        if self.input_cursor < len(self.input_buffer):
            self.input_buffer = (
                self.input_buffer[:self.input_cursor] +
                self.input_buffer[self.input_cursor + 1:]
            )

    def move_cursor_left(self):
        """Move input cursor left."""
        if self.input_cursor > 0:
            self.input_cursor -= 1

    def move_cursor_right(self):
        """Move input cursor right."""
        if self.input_cursor < len(self.input_buffer):
            self.input_cursor += 1

    def move_cursor_home(self):
        """Move cursor to start."""
        self.input_cursor = 0

    def move_cursor_end(self):
        """Move cursor to end."""
        self.input_cursor = len(self.input_buffer)

    # Navigation
    def next_button(self):
        """Select next button."""
        if self.buttons:
            self.selected_button = (self.selected_button + 1) % len(self.buttons)

    def prev_button(self):
        """Select previous button."""
        if self.buttons:
            self.selected_button = (self.selected_button - 1) % len(self.buttons)

    def next_option(self):
        """Select next option (for SELECT type)."""
        if self.options:
            self.selected_option = (self.selected_option + 1) % len(self.options)

    def prev_option(self):
        """Select previous option (for SELECT type)."""
        if self.options:
            self.selected_option = (self.selected_option - 1) % len(self.options)

    def activate_selected(self) -> tuple:
        """Activate the selected button. Returns (action, value)."""
        if self.buttons and 0 <= self.selected_button < len(self.buttons):
            btn = self.buttons[self.selected_button]
            return (btn.action, self.get_result())
        return ("ok", self.get_result())


# Border character sets
BORDERS = {
    "single": {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│"},
    "double": {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"},
    "rounded": {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"},
    "heavy": {"tl": "┏", "tr": "┓", "bl": "┗", "br": "┛", "h": "━", "v": "┃"},
}

# Color scheme
COLOR_BORDER = 4        # Orange
COLOR_TITLE = 9         # Green (success)
COLOR_CONTENT = 7       # Gray
COLOR_INPUT_BG = 0      # Default
COLOR_INPUT_TEXT = 1    # Amber
COLOR_BUTTON = 7        # Gray
COLOR_BUTTON_SEL = 9    # Green when selected
COLOR_OPTION = 7        # Gray
COLOR_OPTION_SEL = 9    # Green when selected


class ModalRenderer:
    """Renders modal dialogs."""

    def __init__(self, modal_state: ModalState):
        self.modal = modal_state

    def render(self, scr, screen_h: int, screen_w: int):
        """Render the modal centered on screen."""
        if not self.modal.visible:
            return

        # Calculate dimensions
        width = max(self.modal.min_width, int(screen_w * self.modal.width_pct))
        width = min(width, screen_w - 4)  # Leave margin

        # Calculate height based on content
        content_height = len(self.modal.content)
        if self.modal.modal_type == ModalType.INPUT:
            content_height += 3  # Label + input + spacing
        elif self.modal.modal_type == ModalType.SELECT:
            content_height += len(self.modal.options) + 1

        height = min(
            max(self.modal.min_height, content_height + 6),  # +6 for border, title, buttons
            int(screen_h * self.modal.height_pct),
            screen_h - 4
        )

        # Center position
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2

        # Get border chars
        b = BORDERS.get(self.modal.border_style, BORDERS["double"])

        # Draw shadow first (offset by 1)
        for row in range(y + 1, y + height + 1):
            if row < screen_h:
                safe_addstr(scr, row, x + 1, " " * min(width, screen_w - x - 1),
                           curses.A_DIM)

        # Draw border and fill
        self._draw_box(scr, x, y, width, height, b)

        # Draw title
        if self.modal.title:
            title_text = f" {self.modal.title} "
            title_x = x + (width - len(title_text)) // 2
            safe_addstr(scr, y, title_x, title_text,
                       curses.color_pair(COLOR_TITLE) | curses.A_BOLD)

        # Content area
        content_y = y + 2
        content_x = x + 2
        content_w = width - 4
        content_h = height - 5  # Reserve space for buttons

        # Draw content lines
        for i, line in enumerate(self.modal.content):
            if i >= content_h - 3:  # Leave room for input/options
                break
            safe_addstr(scr, content_y + i, content_x, line[:content_w],
                       curses.color_pair(COLOR_CONTENT))

        content_y += len(self.modal.content[:content_h - 3]) + 1

        # Draw input field or options
        if self.modal.modal_type == ModalType.INPUT:
            self._render_input(scr, content_x, content_y, content_w)
        elif self.modal.modal_type == ModalType.SELECT:
            self._render_options(scr, content_x, content_y, content_w,
                                content_h - len(self.modal.content) - 1)

        # Draw buttons at bottom
        button_y = y + height - 2
        self._render_buttons(scr, x, button_y, width)

    def _draw_box(self, scr, x: int, y: int, width: int, height: int, b: dict):
        """Draw a box with borders."""
        # Top border
        safe_addstr(scr, y, x, b["tl"] + b["h"] * (width - 2) + b["tr"],
                   curses.color_pair(COLOR_BORDER))

        # Sides and fill
        for row in range(y + 1, y + height - 1):
            safe_addstr(scr, row, x, b["v"], curses.color_pair(COLOR_BORDER))
            safe_addstr(scr, row, x + 1, " " * (width - 2), curses.color_pair(0))
            safe_addstr(scr, row, x + width - 1, b["v"], curses.color_pair(COLOR_BORDER))

        # Bottom border
        safe_addstr(scr, y + height - 1, x,
                   b["bl"] + b["h"] * (width - 2) + b["br"],
                   curses.color_pair(COLOR_BORDER))

    def _render_input(self, scr, x: int, y: int, width: int):
        """Render text input field."""
        # Label
        if self.modal.input_label:
            safe_addstr(scr, y, x, self.modal.input_label,
                       curses.color_pair(COLOR_CONTENT))
            y += 1

        # Input field with border
        field_width = width - 2
        safe_addstr(scr, y, x, "┌" + "─" * field_width + "┐",
                   curses.color_pair(COLOR_BORDER) | curses.A_DIM)
        y += 1

        # Input text or placeholder
        display_text = self.modal.input_buffer or self.modal.input_placeholder
        if not self.modal.input_buffer and self.modal.input_placeholder:
            text_attr = curses.A_DIM | curses.color_pair(COLOR_CONTENT)
        else:
            text_attr = curses.color_pair(COLOR_INPUT_TEXT)

        safe_addstr(scr, y, x, "│", curses.color_pair(COLOR_BORDER) | curses.A_DIM)
        safe_addstr(scr, y, x + 1, display_text[:field_width].ljust(field_width), text_attr)
        safe_addstr(scr, y, x + field_width + 1, "│",
                   curses.color_pair(COLOR_BORDER) | curses.A_DIM)

        # Draw cursor
        cursor_x = x + 1 + min(self.modal.input_cursor, field_width - 1)
        if self.modal.input_cursor < len(self.modal.input_buffer):
            char = self.modal.input_buffer[self.modal.input_cursor]
        else:
            char = " "
        safe_addstr(scr, y, cursor_x, char, curses.A_REVERSE | curses.color_pair(COLOR_INPUT_TEXT))

        y += 1
        safe_addstr(scr, y, x, "└" + "─" * field_width + "┘",
                   curses.color_pair(COLOR_BORDER) | curses.A_DIM)

    def _render_options(self, scr, x: int, y: int, width: int, max_height: int):
        """Render select options."""
        for i, option in enumerate(self.modal.options):
            if i >= max_height:
                break

            is_selected = (i == self.modal.selected_option)
            prefix = "● " if is_selected else "○ "

            if is_selected:
                attr = curses.color_pair(COLOR_OPTION_SEL) | curses.A_BOLD
            else:
                attr = curses.color_pair(COLOR_OPTION)

            line = f"{prefix}{option}"
            safe_addstr(scr, y + i, x, line[:width], attr)

    def _render_buttons(self, scr, box_x: int, y: int, box_width: int):
        """Render buttons centered at bottom."""
        if not self.modal.buttons:
            return

        # Calculate total buttons width
        button_texts = []
        for i, btn in enumerate(self.modal.buttons):
            text = f"[ {btn.label} ]"
            button_texts.append(text)

        total_width = sum(len(t) for t in button_texts) + (len(button_texts) - 1) * 2
        start_x = box_x + (box_width - total_width) // 2

        x = start_x
        for i, (btn, text) in enumerate(zip(self.modal.buttons, button_texts)):
            is_selected = (i == self.modal.selected_button)

            if is_selected:
                attr = curses.color_pair(COLOR_BUTTON_SEL) | curses.A_REVERSE
            else:
                attr = curses.color_pair(COLOR_BUTTON)

            safe_addstr(scr, y, x, text, attr)
            x += len(text) + 2


# Convenience functions for common modal types

def show_info(modal: ModalState, title: str, content: List[str], on_close: Callable = None):
    """Show an info modal."""
    modal.show(
        ModalType.INFO, title, content,
        buttons=[ModalButton("OK", "ok", is_default=True)],
        on_close=on_close
    )


def show_confirm(modal: ModalState, title: str, content: List[str], on_close: Callable = None):
    """Show a confirmation modal."""
    modal.show(
        ModalType.CONFIRM, title, content,
        buttons=[
            ModalButton("Yes", "yes", is_default=True),
            ModalButton("No", "no", is_cancel=True),
        ],
        on_close=on_close
    )


def show_input(modal: ModalState, title: str, label: str = "",
               default_value: str = "", placeholder: str = "",
               on_close: Callable = None):
    """Show an input modal."""
    modal.show(
        ModalType.INPUT, title, [],
        buttons=[
            ModalButton("OK", "ok", is_default=True),
            ModalButton("Cancel", "cancel", is_cancel=True),
        ],
        input_label=label,
        default_value=default_value,
        placeholder=placeholder,
        on_close=on_close
    )


def show_select(modal: ModalState, title: str, options: List[str],
                default_option: int = 0, on_close: Callable = None):
    """Show a select modal."""
    modal.show(
        ModalType.SELECT, title, [],
        buttons=[
            ModalButton("Select", "select", is_default=True),
            ModalButton("Cancel", "cancel", is_cancel=True),
        ],
        options=options,
        default_option=default_option,
        on_close=on_close
    )
