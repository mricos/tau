r"""
Input handling for tau TUI.

Unified input mode: always ready for typing, no mode switching required.
- Double-space triggers play/pause
- Tab triggers completion (explicit, not auto)
- Shortcuts work when buffer is empty
- Cursor always visible
- Backslash (\) opens parameter mode for hierarchical parameter navigation
"""

import curses
import time
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tau_lib.core.state import AppState
    from repl_py.cli.manager import CLIManager
    from tui_py.rendering.sidebar import SidebarState
    from tui_py.rendering.modal import ModalState
    from tui_py.rendering.param_mode import ParamModeManager


# Shift+number key mapping (standard US keyboard)
SHIFT_NUMBER_MAP = {
    ord('!'): 1, ord('@'): 2, ord('#'): 3, ord('$'): 4, ord('%'): 5,
    ord('^'): 6, ord('&'): 7, ord('*'): 8, ord('('): 9, ord(')'): 0
}

# Keys that are always shortcuts (even with buffer content)
ALWAYS_SHORTCUT_KEYS = {
    curses.KEY_PPAGE,   # Page Up - scroll
    curses.KEY_NPAGE,   # Page Down - scroll
}


class InputHandler:
    """
    Handles keyboard input for the tau TUI.

    Unified input mode:
    - Always ready for text input (no : required)
    - Double-space triggers play/pause
    - Tab shows completions (explicit, not on every keystroke)
    - Shortcuts work when buffer is empty
    - ESC clears buffer (doesn't exit mode)
    """

    def __init__(
        self,
        state: 'AppState',
        cli: 'CLIManager',
        execute_command: Callable[[str], str],
        show_help: Callable[[], None],
        sidebar: 'SidebarState' = None,
        modal: 'ModalState' = None,
        param_mode: 'ParamModeManager' = None,
    ):
        """
        Initialize input handler.

        Args:
            state: Application state
            cli: CLI manager instance
            execute_command: Function to execute CLI commands
            show_help: Function to display help
            sidebar: Optional sidebar state for toggle/navigation
            modal: Optional modal state for dialog input handling
            param_mode: Optional parameter mode manager for backslash navigation
        """
        self.state = state
        self.cli = cli
        self.execute_command = execute_command
        self.show_help = show_help
        self.sidebar = sidebar
        self.modal = modal
        self.param_mode = param_mode

    def handle_key(self, key: int) -> bool:
        """
        Handle keyboard input in unified mode.

        Input priority:
        1. Modal dialogs (highest)
        2. Parameter mode (backslash mode) when active
        3. Always-shortcut keys (page up/down)
        4. Completion navigation (when visible)
        5. Text input / shortcuts (based on buffer state)

        Args:
            key: Key code from curses

        Returns:
            True to continue, False to quit
        """
        # Modal takes priority when visible
        if self.modal and self.modal.visible:
            return self._handle_modal_key(key)

        # Parameter mode takes priority when active
        if self.param_mode and self.param_mode.is_visible():
            return self._handle_param_mode_key(key)

        # Help (always available)
        if key == ord('?'):
            self.show_help()
            return True

        # Quit (only 'Q' - Shift+Q)
        if key == ord('Q'):
            return False

        # Always-shortcut keys (work regardless of buffer)
        if key in ALWAYS_SHORTCUT_KEYS:
            return self._handle_always_shortcut(key)

        # Unified input handling
        return self._handle_unified_input(key)

    def _handle_always_shortcut(self, key: int) -> bool:
        """Handle keys that are always shortcuts."""
        if key == curses.KEY_PPAGE:
            self.state.lanes.scroll_up(5)
        elif key == curses.KEY_NPAGE:
            self.state.lanes.scroll_down(5)
        return True

    def _handle_unified_input(self, key: int) -> bool:
        """
        Handle input in unified mode.

        When buffer is empty, most keys act as shortcuts.
        When buffer has content, keys go to input buffer.
        Double-space always triggers play/pause.
        """
        buffer_empty = self.cli.is_buffer_empty()
        completions_visible = self.cli.completions_visible

        # ESC - hide completions or clear buffer
        if key == 27:  # ESC
            if completions_visible:
                self.cli.hide_completions()
            else:
                self.cli.exit_mode()  # Just clears buffer now
            return True

        # Enter - submit command or accept completion
        if key in (10, curses.KEY_ENTER):
            return self._handle_enter()

        # Tab - show/navigate completions (explicit trigger)
        if key == ord('\t'):
            return self._handle_tab()

        # Arrow keys - different behavior based on context
        if key in (curses.KEY_UP, curses.KEY_DOWN, curses.KEY_LEFT, curses.KEY_RIGHT):
            return self._handle_arrow_key(key, buffer_empty, completions_visible)

        # Space - check for double-space play trigger
        if key == ord(' '):
            result = self.cli.handle_space()
            if result == "double":
                # Double-space: toggle play
                output = self.execute_command('toggle_play')
                if output:
                    self.cli.add_output(output)
            # Single space was already inserted by handle_space()
            return True

        # Backspace
        if key in (curses.KEY_BACKSPACE, 127, 8):
            self.cli.backspace()
            # Don't auto-update completions
            return True

        # Delete
        if key == curses.KEY_DC:
            self.cli.delete()
            return True

        # Home/End
        if key == curses.KEY_HOME:
            if buffer_empty:
                # Shortcut: go to start of audio
                output = self.execute_command('home')
                if output:
                    self.cli.add_output(output)
            else:
                self.cli.cursor_home()
            return True

        if key == curses.KEY_END:
            if buffer_empty:
                # Shortcut: go to end of audio
                output = self.execute_command('end')
                if output:
                    self.cli.add_output(output)
            else:
                self.cli.cursor_end()
            return True

        # Printable characters
        if 32 <= key <= 126:
            return self._handle_printable(key, buffer_empty)

        return True

    def _handle_enter(self) -> bool:
        """Handle Enter key - submit or accept completion."""
        buffer = self.cli.input_buffer.strip()

        if self.cli.completions_visible:
            # Check if we should submit or accept completion
            should_submit = False
            if ' ' in buffer:
                # Has arguments - submit
                should_submit = True
            elif buffer:
                # Check if buffer exactly matches a registered command
                from tau_lib.core.commands_api import COMMAND_REGISTRY
                if COMMAND_REGISTRY.get(buffer):
                    should_submit = True

            if not should_submit:
                # Accept completion
                self.cli.accept_completion()
                return True

        # Submit command
        self.cli.hide_completions()
        cmd = self.cli.submit()
        if cmd:
            # Check for quit/exit commands (resolve aliases first)
            from tau_lib.core.aliases import get_alias_manager
            resolved = get_alias_manager().resolve(cmd)
            cmd_name = resolved.split()[0]
            if cmd_name in ("quit", "exit", "q"):
                return False  # Signal main loop to exit

            self.cli.add_output(f":{cmd}", record_event=True)
            output = self.execute_command(cmd)
            if output:
                for line in output.split('\n'):
                    self.cli.add_output(line, record_event=False)
                if cmd_name == "clear":
                    self.cli.clear_output()

        return True

    def _handle_tab(self) -> bool:
        """Handle Tab key - explicit completion trigger."""
        if self.cli.completions_visible:
            # Navigate/accept completions
            buffer = self.cli.input_buffer.strip()
            in_category_browse = (len(buffer) <= 1 and self.cli.current_category is None)

            if in_category_browse:
                # Get selected category name and populate buffer
                selected = self.cli.get_selected_completion()
                if selected:
                    self.cli.input_buffer = selected.text
                    self.cli.cursor_pos = len(selected.text)
                # Drill into category
                self.cli.drill_into_category()
            else:
                # Accept completion
                self.cli.accept_completion()
                # Update to show next level completions
                self.cli.update_completions_rich()
        else:
            # Show completions (explicit trigger)
            self.cli.update_completions_rich()

        return True

    def _handle_arrow_key(self, key: int, buffer_empty: bool, completions_visible: bool) -> bool:
        """Handle arrow keys based on context."""
        if key == curses.KEY_UP:
            if completions_visible:
                self.cli.select_prev_completion()
            elif buffer_empty:
                # Shortcut: scroll lanes up
                self.state.lanes.scroll_up(1)
            else:
                # History navigation
                self.cli.history_up()

        elif key == curses.KEY_DOWN:
            if completions_visible:
                self.cli.select_next_completion()
            elif buffer_empty:
                # Shortcut: scroll lanes down
                self.state.lanes.scroll_down(1)
            else:
                # History navigation
                self.cli.history_down()

        elif key == curses.KEY_LEFT:
            if completions_visible and self.cli.current_category:
                self.cli.drill_out_of_category()
            elif buffer_empty:
                # Shortcut: scrub left
                output = self.execute_command('scrub_pct -1')
                if output:
                    self.cli.add_output(output)
            else:
                self.cli.move_cursor(-1)

        elif key == curses.KEY_RIGHT:
            if completions_visible:
                self.cli.drill_into_category()
            elif buffer_empty:
                # Shortcut: scrub right
                output = self.execute_command('scrub_pct 1')
                if output:
                    self.cli.add_output(output)
            else:
                self.cli.move_cursor(1)

        return True

    def _handle_printable(self, key: int, buffer_empty: bool) -> bool:
        """Handle printable character input."""
        char = chr(key)

        # When buffer is empty, only non-alphanumeric keys act as shortcuts
        # Letters always go to input so user can type freely
        if buffer_empty:
            # Lane controls (numbers and shift+numbers) - only when empty
            if key in SHIFT_NUMBER_MAP:
                lane_id = SHIFT_NUMBER_MAP[key]
                msg = self.state.lanes.cycle_display_mode(lane_id)
                self.cli.add_output(msg)
                return True

            if ord('0') <= key <= ord('9'):
                lane_id = key - ord('0')
                msg = self.state.lanes.toggle_visibility(lane_id)
                self.cli.add_output(msg)
                return True

            # Non-letter shortcuts (punctuation only)
            shortcut_cmd = self._empty_buffer_shortcut(key)
            if shortcut_cmd:
                output = self.execute_command(shortcut_cmd)
                if output:
                    self.cli.add_output(output)
                return True

        # Normal character input - all letters go here
        self.cli.insert_char(char)
        # Don't auto-update completions (explicit Tab required)
        return True

    def _empty_buffer_shortcut(self, key: int) -> Optional[str]:
        """
        Map key to command when buffer is empty.

        Only non-alphanumeric keys are shortcuts so users can type freely.
        Letters go to input buffer.
        """
        # Only punctuation/symbol shortcuts - no letters!
        mapping = {
            # Zoom (punctuation)
            ord('<'): 'zoom_in',
            ord(','): 'zoom_in',
            ord('>'): 'zoom_out',
            ord('.'): 'zoom_out',

            # Markers (punctuation)
            ord('`'): 'next_marker',
            ord('~'): 'prev_marker',

            # Sidebar toggle
            ord('\\'): '_sidebar_toggle',
        }

        cmd = mapping.get(key)

        # Handle special internal commands
        if cmd == '_sidebar_toggle':
            self._handle_sidebar_toggle()
            return None

        return cmd

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

    def _handle_sidebar_toggle(self) -> bool:
        """
        Handle backslash key - opens parameter mode.

        The backslash key now opens parameter mode instead of just toggling the sidebar.
        Parameter mode is a hierarchical browser for adjusting values.
        """
        if self.param_mode:
            self.param_mode.toggle()
            if self.param_mode.is_visible():
                self.cli.add_output("\\params - Tab:drill  Esc:close")
            return True

        # Fallback to old sidebar toggle if param_mode not available
        if self.sidebar:
            self.sidebar.toggle_visibility()
            status = "visible" if self.sidebar.visible else "hidden"
            self.cli.add_output(f"Sidebar: {status}")
        return True

    def _handle_param_mode_key(self, key: int) -> bool:
        """
        Handle key input when parameter mode is active.

        In browsing mode:
        - Up/Down: navigate items
        - Tab/Enter/Right: drill into selection
        - Left/Backspace: go back up tree
        - ESC: close parameter mode
        - Letters: filter items

        In slider mode:
        - Left/Right: adjust value
        - ESC/Backspace: exit slider mode
        """
        if not self.param_mode:
            return True

        pm = self.param_mode

        # ESC - exit slider or close param mode
        if key == 27:  # ESC
            if pm.is_slider_mode():
                pm.reset_long_press()
                pm.drill_out()
            else:
                pm.hide()
            return True

        # In slider mode, arrow keys, ESC, and Return (for CC learn) work
        if pm.is_slider_mode():
            if key == curses.KEY_LEFT:
                pm.adjust_slider(-1, self.state)
                return True
            elif key == curses.KEY_RIGHT:
                pm.adjust_slider(1, self.state)
                return True
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                pm.reset_long_press()
                pm.cancel_cc_learn()
                pm.drill_out()
                return True
            elif key in (10, curses.KEY_ENTER):
                # Return key - start or continue CC learn
                if not pm.cc_learn_active:
                    pm.start_cc_learn()
                # Check if learn threshold reached
                param_path = pm.check_cc_learn()
                if param_path:
                    # Trigger CC learn
                    from tui_py.commands.osc_commands import get_osc_state
                    osc = get_osc_state()
                    result = osc.learn_cc(param_path)
                    self.cli.add_output(result)
                return True
            else:
                # Any other key resets long-press tracking and cancels CC learn
                pm.reset_long_press()
                pm.cancel_cc_learn()
            return True

        # Browsing mode keys
        if key == curses.KEY_UP:
            pm.select_prev()
            return True

        if key == curses.KEY_DOWN:
            pm.select_next()
            return True

        if key == curses.KEY_RIGHT or key == ord('\t') or key in (10, curses.KEY_ENTER):
            pm.drill_in(self.state)
            return True

        if key == curses.KEY_LEFT:
            pm.drill_out()
            return True

        if key in (curses.KEY_BACKSPACE, 127, 8):
            if pm.input_buffer:
                pm.handle_backspace()
            else:
                pm.drill_out()
            return True

        # Printable characters for filtering
        if 32 <= key <= 126:
            pm.handle_input(chr(key))
            return True

        return True

    def _handle_modal_key(self, key: int) -> bool:
        """
        Handle key input when modal is visible.

        Modal takes priority over all other input modes.
        """
        if not self.modal:
            return True

        # ESC - close modal (cancel action)
        if key == 27:
            self.modal.close("cancel", None)
            return True

        # Enter - activate selected button
        if key in (10, curses.KEY_ENTER):
            action, value = self.modal.activate_selected()
            self.modal.close(action, value)
            return True

        # Tab or arrow keys - navigate buttons
        if key == ord('\t') or key == curses.KEY_RIGHT:
            self.modal.next_button()
            return True

        if key == curses.KEY_LEFT:
            self.modal.prev_button()
            return True

        # Up/Down - for SELECT type, navigate options
        if key == curses.KEY_UP:
            from tui_py.rendering.modal import ModalType
            if self.modal.modal_type == ModalType.SELECT:
                self.modal.prev_option()
            return True

        if key == curses.KEY_DOWN:
            from tui_py.rendering.modal import ModalType
            if self.modal.modal_type == ModalType.SELECT:
                self.modal.next_option()
            return True

        # For INPUT type modals, handle text input
        from tui_py.rendering.modal import ModalType
        if self.modal.modal_type == ModalType.INPUT:
            # Backspace
            if key in (curses.KEY_BACKSPACE, 127, 8):
                self.modal.handle_backspace()
                return True

            # Delete
            if key == curses.KEY_DC:
                self.modal.handle_delete()
                return True

            # Home/End
            if key == curses.KEY_HOME:
                self.modal.move_cursor_home()
                return True

            if key == curses.KEY_END:
                self.modal.move_cursor_end()
                return True

            # Printable characters
            if 32 <= key <= 126:
                self.modal.handle_char(chr(key))
                return True

        return True
