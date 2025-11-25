"""
CLI manager for ASCII Scope SNN.
Manages CLI state (input buffer, history, output).
Supports tab-completion.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any


@dataclass
class CompletionState:
    """
    Encapsulates all completion popup state.

    Separating this makes the completion system testable in isolation
    and clarifies what state is completion-specific vs. CLI-specific.
    """
    items: List[Any] = field(default_factory=list)  # List of CompletionItem objects
    visible: bool = False                            # Whether popup is visible
    selected_index: int = 0                          # Currently selected item
    current_category: Optional[str] = None           # Category filter (hierarchical nav)
    provider: Optional[Callable] = None              # Provider function for completions

    def update(self, buffer: str):
        """
        Update completions based on buffer content.

        Args:
            buffer: Current input buffer up to cursor
        """
        if not self.provider:
            return

        # Get rich completion items (pass category filter)
        self.items = self.provider(buffer, self.current_category)

        # Show popup if we have 1+ completions
        if len(self.items) >= 1:
            self.visible = True
            # Reset selection if out of bounds
            if self.selected_index >= len(self.items):
                self.selected_index = 0
        else:
            self.visible = False

    def select_next(self):
        """Move selection down (wraps)."""
        if not self.items:
            return
        self.selected_index = (self.selected_index + 1) % len(self.items)

    def select_prev(self):
        """Move selection up (wraps)."""
        if not self.items:
            return
        self.selected_index = (self.selected_index - 1) % len(self.items)

    def get_selected(self) -> Optional[Any]:
        """Get currently selected completion item."""
        if not self.items or self.selected_index < 0:
            return None
        if self.selected_index < len(self.items):
            return self.items[self.selected_index]
        return None

    def hide(self):
        """Hide completion popup and reset state."""
        self.visible = False
        self.items = []
        self.selected_index = 0
        self.current_category = None

    def drill_into(self) -> bool:
        """
        Drill into selected category (→ key).

        Returns:
            True if drilled into a category or accepted a command
        """
        item = self.get_selected()
        if not item:
            return False

        if item.type == "category":
            self.current_category = item.text
            self.selected_index = 0
            return True  # Caller should call update() after this
        else:
            return False  # Caller should accept completion

    def drill_out(self) -> bool:
        """
        Go back to category list (← key).

        Returns:
            True if we were in a category and went back
        """
        if self.current_category is not None:
            self.current_category = None
            self.selected_index = 0
            return True  # Caller should call update() after this
        return False


class CLIManager:
    """Manages CLI input/output state."""

    def __init__(self, history_size: int = 100, output_size: int = 100):
        self.mode = False  # True when in CLI input mode
        self.input_buffer = ""
        self.cursor_pos = 0

        self.history = deque(maxlen=history_size)
        self.history_index = -1  # -1 means not browsing history
        self.history_temp = ""  # Temporary storage when browsing history

        self.output = deque(maxlen=output_size)

        # Event/log tracking with timestamps
        self.last_event_time: Optional[float] = None
        self.event_callback: Optional[Callable] = None  # Callback to record events
        self.log_callback: Optional[Callable] = None  # Callback to record logs

        # Completion state (encapsulated for testability)
        self._completion = CompletionState()

    # ========== COMPLETION PROPERTY ACCESSORS (for backwards compat) ==========

    @property
    def completion_items(self) -> List[Any]:
        """Access completion items list."""
        return self._completion.items

    @property
    def completions_visible(self) -> bool:
        """Check if completion popup is visible."""
        return self._completion.visible

    @property
    def selected_index(self) -> int:
        """Get selected completion index."""
        return self._completion.selected_index

    @property
    def current_category(self) -> Optional[str]:
        """Get current category filter."""
        return self._completion.current_category

    def enter_mode(self):
        """Enter CLI input mode."""
        self.mode = True
        self.input_buffer = ""
        self.cursor_pos = 0
        self.history_index = -1

    def exit_mode(self):
        """Exit CLI input mode."""
        self.mode = False
        self.input_buffer = ""
        self.cursor_pos = 0
        self.history_index = -1

    def insert_char(self, ch: str):
        """Insert character at cursor position."""
        self.input_buffer = (
            self.input_buffer[:self.cursor_pos] +
            ch +
            self.input_buffer[self.cursor_pos:]
        )
        self.cursor_pos += 1
        self.history_index = -1  # Reset history browsing

    def backspace(self):
        """Delete character before cursor."""
        if self.cursor_pos > 0:
            self.input_buffer = (
                self.input_buffer[:self.cursor_pos-1] +
                self.input_buffer[self.cursor_pos:]
            )
            self.cursor_pos -= 1
            self.history_index = -1

    def delete(self):
        """Delete character at cursor."""
        if self.cursor_pos < len(self.input_buffer):
            self.input_buffer = (
                self.input_buffer[:self.cursor_pos] +
                self.input_buffer[self.cursor_pos+1:]
            )
            self.history_index = -1

    def move_cursor(self, delta: int):
        """Move cursor by delta (-1 for left, +1 for right)."""
        self.cursor_pos = max(0, min(len(self.input_buffer), self.cursor_pos + delta))

    def cursor_home(self):
        """Move cursor to start."""
        self.cursor_pos = 0

    def cursor_end(self):
        """Move cursor to end."""
        self.cursor_pos = len(self.input_buffer)

    def history_up(self):
        """Navigate history backwards (older)."""
        if not self.history:
            return

        # First time entering history - save current input
        if self.history_index == -1:
            self.history_temp = self.input_buffer
            self.history_index = len(self.history) - 1
        elif self.history_index > 0:
            self.history_index -= 1

        self.input_buffer = self.history[self.history_index]
        self.cursor_pos = len(self.input_buffer)

    def history_down(self):
        """Navigate history forwards (newer)."""
        if self.history_index == -1:
            return

        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.input_buffer = self.history[self.history_index]
        else:
            # Restore temporary input
            self.history_index = -1
            self.input_buffer = self.history_temp

        self.cursor_pos = len(self.input_buffer)

    def submit(self) -> Optional[str]:
        """
        Submit current input as command.

        Returns:
            Command string, or None if empty
        """
        cmd = self.input_buffer.strip()
        if cmd:
            # Add to history
            self.history.append(cmd)

        self.input_buffer = ""
        self.cursor_pos = 0
        self.history_index = -1

        return cmd if cmd else None

    def add_output(self, text: str, is_log: bool = False, log_level: str = "INFO"):
        """
        Add output line and record as event.

        Args:
            text: Output text
            is_log: If True, record as log (less frequent, color coded)
            log_level: Log level for color coding (INFO, WARNING, ERROR, SUCCESS)
        """
        if text:
            self.output.append(text)

            # Record event with deltaTimeMs
            current_time = time.time()
            if self.last_event_time is not None:
                delta_ms = int((current_time - self.last_event_time) * 1000)
            else:
                delta_ms = 0

            self.last_event_time = current_time

            # Record to appropriate lane
            if is_log and self.log_callback:
                # Log entry with color coding
                self.log_callback(text, log_level, delta_ms)
            elif self.event_callback:
                # Event entry with deltaTimeMs
                self.event_callback(text, delta_ms)

    def clear_output(self):
        """Clear output buffer."""
        self.output.clear()

    def get_output_lines(self, count: int = 3) -> list:
        """Get last N output lines."""
        return list(self.output)[-count:]

    def set_event_callback(self, callback: Callable):
        """
        Set callback for recording events to lane 9.

        Args:
            callback: Function(text: str, delta_ms: int) -> None
        """
        self.event_callback = callback

    def set_log_callback(self, callback: Callable):
        """
        Set callback for recording logs to lane 0.

        Args:
            callback: Function(text: str, log_level: str, delta_ms: int) -> None
        """
        self.log_callback = callback

    # ========== RICH COMPLETION METHODS ==========

    def set_completion_rich_provider(self, provider: Callable):
        """Set provider function for rich completions."""
        self._completion.provider = provider

    def update_completions_rich(self):
        """
        Update rich completion items based on current buffer.
        Called on every keystroke for real-time filtering.
        """
        buffer = self.input_buffer[:self.cursor_pos]
        self._completion.update(buffer)

    def select_next_completion(self):
        """Move selection down in completion list (wraps)."""
        self._completion.select_next()

    def select_prev_completion(self):
        """Move selection up in completion list (wraps)."""
        self._completion.select_prev()

    def get_selected_completion(self) -> Optional[Any]:
        """Get currently selected completion item."""
        return self._completion.get_selected()

    def accept_completion(self):
        """Insert selected completion into buffer."""
        item = self._completion.get_selected()
        if not item:
            return

        # Parse buffer to determine what to replace
        buffer = self.input_buffer[:self.cursor_pos]
        parts = buffer.split()

        if not parts or (len(parts) == 1 and not buffer.endswith(' ')):
            # Replacing command name
            self.input_buffer = item.text + ' '
            self.cursor_pos = len(self.input_buffer)
        else:
            # Replacing argument
            last_space = buffer.rfind(' ')
            prefix = buffer[:last_space + 1] if last_space >= 0 else ''
            suffix = self.input_buffer[self.cursor_pos:]
            self.input_buffer = prefix + item.text + ' ' + suffix
            self.cursor_pos = len(prefix + item.text + ' ')

        self._completion.hide()

    def hide_completions(self):
        """Hide completion popup."""
        self._completion.hide()

    def drill_into_category(self) -> bool:
        """
        Drill into selected category (→ key).
        If on a category item, show commands in that category.
        If on a command item, accept it.
        """
        if self._completion.drill_into():
            # Drilled into category - update completions
            self.update_completions_rich()
            return True
        else:
            # Not a category - accept completion
            self.accept_completion()
            return True

    def drill_out_of_category(self) -> bool:
        """
        Go back to category list (← key).
        Returns True if we were in a category and went back.
        """
        if self._completion.drill_out():
            self.update_completions_rich()
            return True
        return False
