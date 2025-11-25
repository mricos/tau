"""
Input handling for tau TUI.

Centralizes keyboard input handling for normal and CLI modes.
"""

import curses
import time
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tau_lib.core.state import AppState
    from repl_py.cli.manager import CLIManager


# Shift+number key mapping (standard US keyboard)
SHIFT_NUMBER_MAP = {
    ord('!'): 1, ord('@'): 2, ord('#'): 3, ord('$'): 4, ord('%'): 5,
    ord('^'): 6, ord('&'): 7, ord('*'): 8, ord('('): 9, ord(')'): 0
}


class InputHandler:
    """
    Handles keyboard input for the tau TUI.

    Separates input handling logic from the main App class for:
    - Better testability
    - Cleaner separation of concerns
    - Easier key binding customization
    """

    def __init__(
        self,
        state: 'AppState',
        cli: 'CLIManager',
        execute_command: Callable[[str], str],
        show_help: Callable[[], None],
    ):
        """
        Initialize input handler.

        Args:
            state: Application state
            cli: CLI manager instance
            execute_command: Function to execute CLI commands
            show_help: Function to display help
        """
        self.state = state
        self.cli = cli
        self.execute_command = execute_command
        self.show_help = show_help

    def handle_key(self, key: int) -> bool:
        """
        Handle keyboard input.

        Args:
            key: Key code from curses

        Returns:
            True to continue, False to quit
        """
        # Help (only '?', not 'h')
        if key == ord('?'):
            self.show_help()
            return True

        # CLI mode
        if self.cli.mode:
            return self._handle_cli_key(key)

        # Enter CLI mode
        if key == ord(':'):
            self.cli.enter_mode()
            return True

        # Quit (only 'Q' - Shift+Q, not lowercase 'q' to prevent accidental quit)
        if key == ord('Q'):
            return False

        # Video popup toggle
        if key == ord('V'):
            return self._handle_video_toggle()

        # Lane controls
        if key in SHIFT_NUMBER_MAP:
            # Shift+number: cycle display mode
            lane_id = SHIFT_NUMBER_MAP[key]
            msg = self.state.lanes.cycle_display_mode(lane_id)
            self.cli.add_output(msg)
            return True
        elif ord('0') <= key <= ord('9'):
            # Regular number: toggle visibility
            lane_id = key - ord('0')
            msg = self.state.lanes.toggle_visibility(lane_id)
            self.cli.add_output(msg)
            return True

        # Scrolling controls
        if key == curses.KEY_PPAGE:  # Page Up
            self.state.lanes.scroll_up(5)
            return True
        elif key == curses.KEY_NPAGE:  # Page Down
            self.state.lanes.scroll_down(5)
            return True
        elif key == curses.KEY_UP:
            self.state.lanes.scroll_up(1)
            return True
        elif key == curses.KEY_DOWN:
            self.state.lanes.scroll_down(1)
            return True

        # Map other keys to commands
        cmd = self._key_to_command(key)
        if cmd:
            output = self.execute_command(cmd)
            if output:
                self.cli.add_output(output)

        return True

    def _handle_video_toggle(self) -> bool:
        """Handle video popup toggle (Shift+V)."""
        if self.state.features.video_enabled and self.state.video_popup:
            self.state.video_popup.toggle()
            status = "visible" if self.state.video_popup.visible else "hidden"
            self.cli.add_output(f"✓ Video popup: {status}")
        elif not self.state.features.video_enabled:
            self.cli.add_output("Video features disabled (--no-video)")
        else:
            self.cli.add_output("No video loaded (use :video_load <path>)")
        return True

    def _handle_cli_key(self, key: int) -> bool:
        """Handle key when in CLI mode."""
        # ESC key - hide completions if visible, otherwise exit CLI
        if key == 27:  # ESC
            if self.cli.completions_visible:
                self.cli.hide_completions()
            else:
                self.cli.exit_mode()

        # Enter key - accept completion if visible, otherwise submit command
        elif key in (10, curses.KEY_ENTER):
            self._handle_cli_enter()

        # Arrow keys - navigate completions if visible, otherwise history/cursor
        elif key == curses.KEY_UP:
            if self.cli.completions_visible:
                self.cli.select_prev_completion()
            else:
                self.cli.history_up()

        elif key == curses.KEY_DOWN:
            if self.cli.completions_visible:
                self.cli.select_next_completion()
            else:
                self.cli.history_down()

        # Left/Right - hierarchy navigation when completions visible, cursor move otherwise
        elif key == curses.KEY_LEFT:
            if self.cli.completions_visible and self.cli.current_category:
                self.cli.drill_out_of_category()
            else:
                self.cli.move_cursor(-1)
                self.cli.update_completions_rich()

        elif key == curses.KEY_RIGHT:
            if self.cli.completions_visible:
                self.cli.drill_into_category()
            else:
                self.cli.move_cursor(1)
                self.cli.update_completions_rich()

        # Tab key - accept selected completion if popup is visible
        elif key == ord('\t'):
            if self.cli.completions_visible:
                self.cli.accept_completion()
                self.cli.update_completions_rich()

        # Home/End keys
        elif key == curses.KEY_HOME:
            self.cli.cursor_home()
            self.cli.update_completions_rich()

        elif key == curses.KEY_END:
            self.cli.cursor_end()
            self.cli.update_completions_rich()

        # Backspace
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self.cli.backspace()
            self.cli.update_completions_rich()

        # Printable characters
        elif 32 <= key <= 126:
            self._handle_printable_key(key)

        return True

    def _handle_cli_enter(self):
        """Handle Enter key in CLI mode."""
        if self.cli.completions_visible:
            self.cli.accept_completion()
            self.cli.update_completions_rich()
        else:
            cmd = self.cli.submit()
            if cmd:
                output = self.execute_command(cmd)
                if output:
                    for line in output.split('\n'):
                        self.cli.add_output(line)
                    if cmd == "clear":
                        self.cli.clear_output()

    def _handle_printable_key(self, key: int):
        """Handle printable character input in CLI mode."""
        # Special case: if input buffer is empty, handle lane keys
        if len(self.cli.input_buffer) == 0:
            if key in SHIFT_NUMBER_MAP:
                # Shift+number: cycle display mode
                lane_id = SHIFT_NUMBER_MAP[key]
                msg = self.state.lanes.cycle_display_mode(lane_id)
                self.cli.add_output(msg)
                return  # Consumed by lane cycle
            elif ord('0') <= key <= ord('9'):
                # Regular number: toggle visibility
                lane_id = key - ord('0')
                msg = self.state.lanes.toggle_visibility(lane_id)
                self.cli.add_output(msg)
                return  # Consumed by lane toggle

        # Normal character input
        self.cli.insert_char(chr(key))
        self.cli.update_completions_rich()

    def _key_to_command(self, key: int) -> Optional[str]:
        """Map keyboard shortcut to CLI command."""
        mapping = {
            # Transport
            ord(' '): 'toggle_play',
            curses.KEY_LEFT: 'scrub_pct -1',
            curses.KEY_RIGHT: 'scrub_pct 1',
            curses.KEY_SLEFT: 'scrub_pct -10',
            curses.KEY_SRIGHT: 'scrub_pct 10',
            curses.KEY_HOME: 'home',
            curses.KEY_END: 'end',

            # Zoom
            ord('<'): 'zoom_in',
            ord(','): 'zoom_in',
            ord('>'): 'zoom_out',
            ord('.'): 'zoom_out',

            # Display
            ord('o'): 'toggle_mode',

            # Reprocess
            ord('K'): 'reprocess',

            # Markers
            ord('m'): f'mark marker_{int(time.time())}',
            ord('`'): 'next_marker',
            ord('~'): 'prev_marker',

            # Parameters (quick adjust)
            ord('z'): 'tau_a_semitone -1',
            ord('Z'): 'tau_a_semitone 1',
            ord('x'): 'tau_r_semitone -1',
            ord('X'): 'tau_r_semitone 1',
            ord('c'): 'thr ' + str(max(0.5, self.state.kernel.threshold - 0.5)),
            ord('C'): 'thr ' + str(min(20.0, self.state.kernel.threshold + 0.5)),
            ord('v'): 'ref ' + str(max(0.001, self.state.kernel.refractory - 0.005)),
            # Note: 'V' is video toggle, handled separately
        }

        return mapping.get(key)
