r"""
Parameter mode (\ mode) for hierarchical parameter navigation and slider control.

The parameter operator (\) opens a sidebar for navigating and adjusting parameters.
- \kernel - shows kernel parameters
- \kernel.tau_a - drills into tau_a, showing slider at value endpoint
- Tab completion for drilling down (e.g., \kernel<tab> shows .tau_a, .tau_r, etc.)
- Arrow left/right in slider mode adjusts the value
- ESC exits slider mode or parameter mode
"""

import curses
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any, Tuple, TYPE_CHECKING
from enum import Enum, auto

if TYPE_CHECKING:
    from tau_lib.core.state import AppState


class ParamModeState(Enum):
    """State machine for parameter mode."""
    HIDDEN = auto()       # Not visible
    BROWSING = auto()     # Navigating parameter tree
    SLIDER = auto()       # Adjusting a value with slider


@dataclass
class ParameterNode:
    """A node in the parameter tree."""
    name: str
    path: str                                    # Full path like "kernel.tau_a"
    value: Optional[float] = None                # Current value (None for branches)
    min_val: float = 0.0                        # Min value for slider
    max_val: float = 1.0                        # Max value for slider
    step: float = 0.001                         # Step size for arrow adjustment
    unit: str = ""                              # Display unit (e.g., "s", "ms")
    children: List['ParameterNode'] = field(default_factory=list)
    getter: Optional[Callable[['AppState'], float]] = None   # Get current value
    setter: Optional[Callable[['AppState', float], None]] = None  # Set value

    def is_leaf(self) -> bool:
        """True if this is a value endpoint (no children)."""
        return len(self.children) == 0

    def get_display_value(self, state: 'AppState') -> str:
        """Get formatted display value."""
        if self.getter:
            val = self.getter(state)
            if self.unit:
                return f"{val:.4f}{self.unit}"
            return f"{val:.4f}"
        return ""


@dataclass
class ParamModeManager:
    """
    Manages the parameter mode state and navigation.

    This is the "mediator" between input and the parameter tree.
    The sidebar is just a view of this state.
    """
    state: ParamModeState = ParamModeState.HIDDEN
    current_path: str = ""                       # e.g., "kernel" or "kernel.tau_a"
    input_buffer: str = ""                       # Partial input for tab completion
    selected_index: int = 0                      # Selected item in current level
    slider_value: float = 0.0                    # Current slider position (0.0-1.0)

    # Long-press tracking for exponential motion
    _key_press_start: float = 0.0                # Timestamp when key was first pressed
    _last_key_time: float = 0.0                  # Timestamp of last key event
    _last_key_direction: int = 0                 # Last direction: -1 (left), +1 (right), 0 (none)
    _long_press_threshold: float = 0.8           # Seconds before exponential kicks in
    _key_gap_threshold: float = 0.15             # Gap indicating key release (curses repeat ~0.03-0.05s)
    _exp_base: float = 1.2                       # Exponential growth base (gentler curve)

    # OSC integration hook (placeholder for future)
    osc_callback: Optional[Callable[[str, float], None]] = None

    # MIDI CC learn mode
    cc_learn_active: bool = False          # True when Return held in slider mode
    cc_learn_start_time: float = 0.0       # When Return was first pressed
    cc_learn_threshold: float = 0.3        # Seconds to hold for CC learn

    # Parameter tree (built on init)
    root: ParameterNode = field(default_factory=lambda: ParameterNode(name="root", path=""))

    def __post_init__(self):
        """Build the parameter tree."""
        self._build_tree()

    def _build_tree(self):
        """Construct the parameter tree from AppState structure."""
        # Kernel parameters
        kernel = ParameterNode(
            name="kernel",
            path="kernel",
            children=[
                ParameterNode(
                    name="tau_a",
                    path="kernel.tau_a",
                    min_val=0.0001,
                    max_val=0.1,
                    step=0.0001,
                    unit="s",
                    getter=lambda s: s.kernel.tau_a,
                    setter=lambda s, v: setattr(s.kernel, 'tau_a', v),
                ),
                ParameterNode(
                    name="tau_r",
                    path="kernel.tau_r",
                    min_val=0.001,
                    max_val=0.5,
                    step=0.001,
                    unit="s",
                    getter=lambda s: s.kernel.tau_r,
                    setter=lambda s, v: setattr(s.kernel, 'tau_r', v),
                ),
                ParameterNode(
                    name="threshold",
                    path="kernel.threshold",
                    min_val=0.1,
                    max_val=10.0,
                    step=0.1,
                    unit="",
                    getter=lambda s: s.kernel.threshold,
                    setter=lambda s, v: setattr(s.kernel, 'threshold', v),
                ),
                ParameterNode(
                    name="refractory",
                    path="kernel.refractory",
                    min_val=0.001,
                    max_val=0.1,
                    step=0.001,
                    unit="s",
                    getter=lambda s: s.kernel.refractory,
                    setter=lambda s, v: setattr(s.kernel, 'refractory', v),
                ),
            ]
        )

        # Transport parameters
        transport = ParameterNode(
            name="transport",
            path="transport",
            children=[
                ParameterNode(
                    name="span",
                    path="transport.span",
                    min_val=0.1,
                    max_val=60.0,
                    step=0.1,
                    unit="s",
                    getter=lambda s: s.transport.span,
                    setter=lambda s, v: setattr(s.transport, 'span', v),
                ),
                ParameterNode(
                    name="position",
                    path="transport.position",
                    min_val=0.0,
                    max_val=1.0,  # Will be dynamically set to duration
                    step=0.1,
                    unit="s",
                    getter=lambda s: s.transport.position,
                    setter=lambda s, v: s.transport.seek(v),
                ),
            ]
        )

        # Display parameters
        display = ParameterNode(
            name="display",
            path="display",
            children=[
                # Mode is special - it's an enum, not a float
                # We could handle this differently or skip it
            ]
        )

        # Layout parameters
        layout = ParameterNode(
            name="layout",
            path="layout",
            children=[
                ParameterNode(
                    name="cli_output_max",
                    path="layout.cli_output_max",
                    min_val=1,
                    max_val=20,
                    step=1,
                    unit="",
                    getter=lambda s: float(s.layout.cli_output_max_height),
                    setter=lambda s, v: setattr(s.layout, 'cli_output_max_height', int(v)),
                ),
            ]
        )

        self.root = ParameterNode(
            name="root",
            path="",
            children=[kernel, transport, layout]
        )

    def toggle(self):
        """Toggle parameter mode visibility."""
        if self.state == ParamModeState.HIDDEN:
            self.state = ParamModeState.BROWSING
            self.current_path = ""
            self.input_buffer = ""
            self.selected_index = 0
        else:
            self.state = ParamModeState.HIDDEN

    def show(self):
        """Show parameter mode."""
        self.state = ParamModeState.BROWSING
        self.current_path = ""
        self.input_buffer = ""
        self.selected_index = 0

    def hide(self):
        """Hide parameter mode."""
        self.state = ParamModeState.HIDDEN

    def is_visible(self) -> bool:
        """Check if parameter mode is visible."""
        return self.state != ParamModeState.HIDDEN

    def is_slider_mode(self) -> bool:
        """Check if in slider adjustment mode."""
        return self.state == ParamModeState.SLIDER

    def get_current_node(self) -> Optional[ParameterNode]:
        """Get the node at current_path."""
        if not self.current_path:
            return self.root
        return self._find_node(self.current_path)

    def _find_node(self, path: str) -> Optional[ParameterNode]:
        """Find a node by its path."""
        if not path:
            return self.root

        parts = path.split('.')
        node = self.root

        for part in parts:
            found = None
            for child in node.children:
                if child.name == part:
                    found = child
                    break
            if found is None:
                return None
            node = found

        return node

    def get_visible_items(self) -> List[ParameterNode]:
        """Get list of items at current level for display."""
        node = self.get_current_node()
        if node is None:
            return []
        return node.children

    def get_completions(self) -> List[str]:
        """Get tab completions for current input_buffer."""
        node = self.get_current_node()
        if node is None:
            return []

        prefix = self.input_buffer
        completions = []

        for child in node.children:
            if child.name.startswith(prefix):
                completions.append(child.name)

        return completions

    def handle_input(self, char: str):
        """Handle character input in browsing mode."""
        if self.state == ParamModeState.SLIDER:
            return  # Slider mode doesn't accept text input

        self.input_buffer += char
        # Filter visible items based on input
        self._update_selection_from_input()

    def _update_selection_from_input(self):
        """Update selection to match input buffer prefix."""
        items = self.get_visible_items()
        for i, item in enumerate(items):
            if item.name.startswith(self.input_buffer):
                self.selected_index = i
                return

    def handle_backspace(self):
        """Handle backspace in browsing mode."""
        if self.input_buffer:
            self.input_buffer = self.input_buffer[:-1]
            self._update_selection_from_input()

    def select_next(self):
        """Move selection down."""
        items = self.get_visible_items()
        if items:
            self.selected_index = (self.selected_index + 1) % len(items)
            self.input_buffer = ""  # Clear filter on arrow nav

    def select_prev(self):
        """Move selection up."""
        items = self.get_visible_items()
        if items:
            self.selected_index = (self.selected_index - 1) % len(items)
            self.input_buffer = ""

    def drill_in(self, app_state: 'AppState') -> bool:
        """
        Drill into selected item (Tab or Enter or Right arrow).

        If at a leaf node (value endpoint), enter slider mode.
        Returns True if action was taken.
        """
        items = self.get_visible_items()
        if not items or self.selected_index >= len(items):
            return False

        selected = items[self.selected_index]

        if selected.is_leaf():
            # Enter slider mode
            self.state = ParamModeState.SLIDER
            self.current_path = selected.path
            # Initialize slider position from current value
            if selected.getter:
                val = selected.getter(app_state)
                # Normalize to 0-1
                range_val = selected.max_val - selected.min_val
                if range_val > 0:
                    self.slider_value = (val - selected.min_val) / range_val
                else:
                    self.slider_value = 0.5
        else:
            # Drill into branch
            self.current_path = selected.path
            self.selected_index = 0
            self.input_buffer = ""

        return True

    def drill_out(self) -> bool:
        """
        Go back up the tree (Left arrow or backspace when buffer empty).

        If in slider mode, exit to browsing.
        Returns True if action was taken.
        """
        if self.state == ParamModeState.SLIDER:
            # Exit slider mode back to browsing
            # Navigate to parent
            if '.' in self.current_path:
                self.current_path = self.current_path.rsplit('.', 1)[0]
            else:
                self.current_path = ""
            self.state = ParamModeState.BROWSING
            return True

        if not self.current_path:
            # At root - hide param mode
            self.hide()
            return True

        # Go up one level
        if '.' in self.current_path:
            self.current_path = self.current_path.rsplit('.', 1)[0]
        else:
            self.current_path = ""

        self.selected_index = 0
        self.input_buffer = ""
        return True

    def adjust_slider(self, delta: int, app_state: 'AppState'):
        """
        Adjust slider value by delta steps.

        Linear motion by default, exponential on long press.
        Long press is detected when the same direction key is held
        beyond _long_press_threshold seconds.

        Args:
            delta: Number of steps (+1 for right, -1 for left)
            app_state: Application state to update
        """
        if self.state != ParamModeState.SLIDER:
            return

        node = self._find_node(self.current_path)
        if node is None or not node.is_leaf():
            return

        now = time.time()
        gap_since_last = now - self._last_key_time if self._last_key_time > 0 else 999

        # Detect if key was released (gap in events) or direction changed
        if gap_since_last > self._key_gap_threshold or delta != self._last_key_direction:
            # Key was released or direction changed - reset
            self._key_press_start = now
            self._last_key_direction = delta
            hold_duration = 0.0
        else:
            # Continuous hold - measure from start
            hold_duration = now - self._key_press_start

        self._last_key_time = now

        # Calculate step multiplier
        if hold_duration > self._long_press_threshold:
            # Exponential: multiplier grows with hold time
            # Gentler curve: 1.2^(t*3) gives ~2x at 2s, ~4x at 4s, ~10x at 6s
            excess_time = hold_duration - self._long_press_threshold
            multiplier = self._exp_base ** (excess_time * 3)
            multiplier = min(multiplier, 20.0)  # Cap at 20x
        else:
            # Linear: single step
            multiplier = 1.0

        # Get current value and adjust
        if node.getter and node.setter:
            current = node.getter(app_state)
            new_val = current + (delta * node.step * multiplier)
            new_val = max(node.min_val, min(node.max_val, new_val))
            node.setter(app_state, new_val)

            # Update slider position
            range_val = node.max_val - node.min_val
            if range_val > 0:
                self.slider_value = (new_val - node.min_val) / range_val

            # Fire OSC callback if registered
            if self.osc_callback:
                self.osc_callback(self.current_path, new_val)

    def reset_long_press(self):
        """Reset long-press tracking (call when key is released or direction changes)."""
        self._key_press_start = 0.0
        self._last_key_time = 0.0
        self._last_key_direction = 0

    def set_osc_callback(self, callback: Callable[[str, float], None]):
        """
        Set callback for OSC message integration.

        Args:
            callback: Function(path: str, value: float) -> None
        """
        self.osc_callback = callback

    def start_cc_learn(self):
        """Start CC learn mode (called when Return pressed in slider mode)."""
        if self.state != ParamModeState.SLIDER:
            return
        self.cc_learn_active = True
        self.cc_learn_start_time = time.time()

    def check_cc_learn(self) -> Optional[str]:
        """
        Check if CC learn should trigger.

        Returns:
            Parameter path if learn triggered, None otherwise
        """
        if not self.cc_learn_active:
            return None

        held_duration = time.time() - self.cc_learn_start_time
        if held_duration >= self.cc_learn_threshold:
            # Learn threshold reached - return current parameter path
            self.cc_learn_active = False
            return self.current_path
        return None

    def cancel_cc_learn(self):
        """Cancel CC learn mode (called when Return released)."""
        self.cc_learn_active = False
        self.cc_learn_start_time = 0.0

    def get_cc_learn_progress(self) -> float:
        """Get CC learn progress (0.0 to 1.0)."""
        if not self.cc_learn_active:
            return 0.0
        held = time.time() - self.cc_learn_start_time
        return min(1.0, held / self.cc_learn_threshold)

    def navigate_to_path(self, path: str, app_state: 'AppState') -> bool:
        """
        Navigate directly to a parameter path.

        Used when user types \\kernel.tau_a directly.

        Args:
            path: Parameter path like "kernel.tau_a"
            app_state: Application state

        Returns:
            True if navigation successful
        """
        node = self._find_node(path)
        if node is None:
            return False

        self.current_path = path
        self.selected_index = 0
        self.input_buffer = ""

        if node.is_leaf():
            # Go to slider mode
            self.state = ParamModeState.SLIDER
            if node.getter:
                val = node.getter(app_state)
                range_val = node.max_val - node.min_val
                if range_val > 0:
                    self.slider_value = (val - node.min_val) / range_val
        else:
            self.state = ParamModeState.BROWSING

        return True


class ParamModeRenderer:
    """Renders the parameter mode sidebar and slider."""

    # Colors
    COLOR_HEADER = 4       # Orange
    COLOR_ITEM = 7         # Gray
    COLOR_SELECTED = 9     # Green
    COLOR_VALUE = 1        # Amber
    COLOR_SLIDER_TRACK = 7 # Gray
    COLOR_SLIDER_THUMB = 9 # Green

    def __init__(self, param_manager: ParamModeManager, app_state: 'AppState'):
        self.pm = param_manager
        self.app_state = app_state

    def render(self, scr, x: int, y: int, width: int, height: int, divider_end_y: int = None):
        """
        Render parameter mode at position.

        Args:
            scr: curses screen
            x: Left edge position
            y: Top position
            width: Available width
            height: Available height
            divider_end_y: Y position where divider should end (bottom of CLI output)
        """
        if not self.pm.is_visible():
            return

        from tui_py.rendering.helpers import safe_addstr

        # Clear the entire sidebar area first (prevents ghosting)
        # Also clear one column to the left of the divider for clean separation
        clear_str = " " * width
        for row in range(y, y + height):
            try:
                scr.addstr(row, x - 1, clear_str)
            except curses.error:
                pass

        # Draw border - only to divider_end_y if specified
        border_end = divider_end_y if divider_end_y else (y + height)
        for row in range(y, border_end):
            safe_addstr(scr, row, x, "|", curses.color_pair(7) | curses.A_DIM)

        content_x = x + 2
        content_w = width - 3
        y_cursor = y

        # Header showing current path
        path_display = "\\" + (self.pm.current_path or "params")
        header_attr = curses.color_pair(self.COLOR_HEADER) | curses.A_BOLD
        safe_addstr(scr, y_cursor, content_x, path_display[:content_w], header_attr)
        y_cursor += 1

        if self.pm.state == ParamModeState.SLIDER:
            # Render slider mode
            self._render_slider(scr, content_x, y_cursor, content_w, height - 1)
        else:
            # Render browsing mode
            self._render_browser(scr, content_x, y_cursor, content_w, height - 1)

    def _render_browser(self, scr, x: int, y: int, width: int, height: int):
        """Render parameter tree browser."""
        from tui_py.rendering.helpers import safe_addstr

        items = self.pm.get_visible_items()

        if not items:
            safe_addstr(scr, y, x, "(empty)", curses.A_DIM)
            return

        # Show input filter if active
        if self.pm.input_buffer:
            filter_line = f">{self.pm.input_buffer}_"
            safe_addstr(scr, y, x, filter_line[:width], curses.A_DIM)
            y += 1
            height -= 1

        for i, item in enumerate(items[:height]):
            is_selected = (i == self.pm.selected_index)

            # Build display line
            prefix = ">" if is_selected else " "
            suffix = "." if not item.is_leaf() else ""

            # Show value for leaf nodes
            if item.is_leaf():
                val_str = item.get_display_value(self.app_state)
                line = f"{prefix}{item.name}: {val_str}"
            else:
                line = f"{prefix}{item.name}{suffix}"

            # Attributes
            if is_selected:
                attr = curses.color_pair(self.COLOR_SELECTED) | curses.A_REVERSE
            else:
                attr = curses.color_pair(self.COLOR_ITEM)

            safe_addstr(scr, y + i, x, line[:width], attr)

    def _render_slider(self, scr, x: int, y: int, width: int, height: int):
        """Render slider mode for value adjustment."""
        from tui_py.rendering.helpers import safe_addstr

        node = self.pm._find_node(self.pm.current_path)
        if node is None:
            return

        # Parameter name
        safe_addstr(scr, y, x, node.name, curses.color_pair(self.COLOR_HEADER))
        y += 1

        # Current value
        val_str = node.get_display_value(self.app_state)
        safe_addstr(scr, y, x, val_str, curses.color_pair(self.COLOR_VALUE) | curses.A_BOLD)
        y += 2

        # Slider track
        track_width = min(width - 4, 20)
        thumb_pos = int(self.pm.slider_value * (track_width - 1))

        # Render slider with colored thumb
        safe_addstr(scr, y, x, '[', curses.color_pair(self.COLOR_SLIDER_TRACK))
        for i in range(track_width):
            char_x = x + 1 + i
            if i == thumb_pos:
                safe_addstr(scr, y, char_x, '|',
                           curses.color_pair(self.COLOR_SLIDER_THUMB) | curses.A_BOLD)
            else:
                safe_addstr(scr, y, char_x, '-',
                           curses.color_pair(self.COLOR_SLIDER_TRACK) | curses.A_DIM)
        safe_addstr(scr, y, x + track_width + 1, ']', curses.color_pair(self.COLOR_SLIDER_TRACK))
        y += 1

        # Min/max labels
        min_str = f"{node.min_val:.3f}"
        max_str = f"{node.max_val:.3f}"
        safe_addstr(scr, y, x, min_str, curses.A_DIM)
        max_x = x + track_width + 2 - len(max_str)
        safe_addstr(scr, y, max_x, max_str, curses.A_DIM)
        y += 2

        # CC learn indicator / CC mapping display
        from tui_py.commands.osc_commands import get_osc_state
        osc = get_osc_state()

        # Show CC learn progress if active
        if self.pm.cc_learn_active:
            progress = self.pm.get_cc_learn_progress()
            bar_len = int(progress * (track_width - 2))
            learn_bar = "[" + "=" * bar_len + " " * (track_width - 2 - bar_len) + "]"
            safe_addstr(scr, y, x, "LEARN:", curses.color_pair(10) | curses.A_BOLD)  # Yellow
            safe_addstr(scr, y + 1, x, learn_bar, curses.color_pair(10))
        else:
            # Show current CC mapping if any
            cc_num = osc.get_cc_mapping(self.pm.current_path)
            if cc_num is not None:
                safe_addstr(scr, y, x, f"CC{cc_num}", curses.color_pair(9))  # Green
            else:
                safe_addstr(scr, y, x, "Hold Ret=learn", curses.A_DIM)


def parse_param_path(input_str: str) -> Tuple[bool, str]:
    """
    Parse input string that starts with backslash.

    Args:
        input_str: Input like "\\kernel.tau_a"

    Returns:
        (is_param_path, path_without_backslash)
    """
    if input_str.startswith('\\'):
        return (True, input_str[1:])
    return (False, "")
