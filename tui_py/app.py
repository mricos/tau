#!/usr/bin/env python3
"""
tau - Terminal Audio Workstation

Multi-track digital audio workstation with neural network kernel parameter tuning.
Entry point and main event loop.
"""

import sys
import os
import time
import curses
import signal

from tau_lib.core.state import AppState
from tau_lib.core.config import load_config, save_config, get_default_config_path
from tau_lib.data.data_loader import load_data_file, compute_duration
from repl_py.cli.manager import CLIManager
from tau_lib.core.commands_api import COMMAND_REGISTRY
from tui_py.commands import register_all_commands
from tui_py.rendering.helpers import init_colors, safe_addstr
from tui_py.rendering.sparkline import render_sparkline
from tui_py.rendering.waveform import render_waveform_envelope, render_waveform_points
from tui_py.rendering.pinned import render_pinned_compact, render_pinned_expanded
from tui_py.rendering.header import render_header
from tui_py.rendering.cli import CLIRenderer
from tui_py.rendering.splash import SplashState, SplashRenderer
from tui_py.rendering.sidebar import SidebarState, SidebarRenderer, create_default_panels
from tui_py.rendering.modal import ModalState, ModalRenderer
from tui_py.layout import compute_layout, get_special_lanes_info, get_max_special_lanes_height
from tui_py.input_handler import InputHandler
from tau_lib.core.project import TauProject
from tau_lib.integration.tscale_runner import TscaleRunner


REFRESH_HZ = 30  # Display refresh rate
# Timing constants
CLI_POLL_MS = 16      # CLI input polling when active (~60fps max)
IDLE_POLL_MS = 100    # Idle polling when nothing happening (~10fps)


class App:
    """Main application."""

    def __init__(self, audio_path: str = None, project_dir: str = None, context_dir: str = None, no_video: bool = False):
        """
        Minimal initialization - just store args. Heavy init happens in TUI with splash.

        Args:
            audio_path: Optional audio file to load (auto-runs tscale if needed)
            project_dir: Optional project directory (default: search for .snn/)
            context_dir: Optional context directory (default: ~/recordings/)
            no_video: Disable video features
        """
        # Store args for deferred initialization
        self._init_args = {
            'audio_path': audio_path,
            'project_dir': project_dir,
            'context_dir': context_dir,
            'no_video': no_video,
        }

        # Minimal state - will be fully initialized in _deferred_init
        self.state = None
        self.project = None
        self.cli = None
        self.cli_renderer = None
        self.input_handler = None

        # UI state objects (available immediately)
        self.splash = SplashState(visible=True)
        self.sidebar = SidebarState(visible=False)
        self.modal = ModalState(visible=False)

        # Track initialization state
        self._initialized = False
        self._last_saved_hash = None  # For dirty checking

    def _deferred_init(self, scr):
        """
        Heavy initialization with splash screen updates.
        Called from run() after TUI is displayed.
        """
        args = self._init_args
        h, w = scr.getmaxyx()

        # Reuse single renderer for all updates
        splash_renderer = SplashRenderer(self.splash)

        def update_splash(msg, progress):
            nonlocal h, w
            h, w = scr.getmaxyx()  # Update size in case terminal resized
            self.splash.set_step(msg, progress)
            self.splash.tick()
            splash_renderer.render(scr, h, w)
            scr.refresh()
            # Quick key check to allow early dismiss (but continue loading)
            scr.nodelay(True)
            scr.getch()

        try:
            # Step 1: Initialize project
            update_splash("Initializing project...", 0.1)
            self.project = TauProject(args['project_dir'])

            # Step 2: Initialize state
            update_splash("Creating application state...", 0.2)
            self.state = AppState()

            # Set context directory
            if args['context_dir']:
                from pathlib import Path
                self.state.context_dir = Path(args['context_dir']).expanduser().resolve()
            self.state.context_dir.mkdir(parents=True, exist_ok=True)

            # Step 3: Video detection
            update_splash("Detecting video features...", 0.25)
            if not args['no_video']:
                self._detect_video_features()
            else:
                self.state.features.video_enabled = False

            # Step 4: Initialize CLI
            update_splash("Setting up CLI...", 0.3)
            self.cli = CLIManager()
            self.cli.set_event_callback(lambda text, delta_ms: self.state.lanes.add_event(text, delta_ms))
            self.cli.set_log_callback(lambda text, level, delta_ms: self.state.lanes.add_log(text, level, delta_ms))

            # Step 5: Register commands
            update_splash("Registering commands...", 0.4)
            register_all_commands(self.state)
            self.state.project = self.project
            self.state.cli = self.cli

            # Set up rich completion provider
            from tui_py.ui.completion import get_completions_rich
            self.cli.set_completion_rich_provider(get_completions_rich)

            # Step 6: Initialize input handler
            update_splash("Setting up input handler...", 0.5)
            self.input_handler = InputHandler(
                state=self.state,
                cli=self.cli,
                execute_command=self._execute_command,
                show_help=self._show_help,
                sidebar=self.sidebar,
                modal=self.modal,
            )

            # Step 7: Load config
            update_splash("Loading configuration...", 0.55)
            local_config = self.project.load_local_config()

            # Step 8: Load audio/data
            audio_path = args['audio_path']
            if audio_path:
                update_splash(f"Loading audio: {audio_path}...", 0.6)
                self._load_audio(audio_path)
            else:
                # Try to load from last session
                update_splash("Checking for saved session...", 0.6)
                session = self.project.load_session_state()
                audio_file = session.get('audio_file') if session else None

                if audio_file:
                    update_splash(f"Restoring session: {audio_file}...", 0.7)
                    try:
                        self._load_audio(audio_file)
                        if 'position' in session:
                            self.state.transport.position = session['position']
                        if 'markers' in session:
                            for m in session['markers']:
                                self.state.markers.add(m['time'], m['label'])
                    except (FileNotFoundError, Exception):
                        audio_file = None  # Failed, try latest data

                if not audio_file or not self.state.data_buffer or len(self.state.data_buffer) <= 1:
                    update_splash("Looking for data files...", 0.8)
                    latest = self.project.trs.query_latest(type="data", kind="raw")
                    if latest:
                        update_splash(f"Loading: {latest.filepath.name}...", 0.85)
                        self.state.data_buffer = load_data_file(str(latest.filepath))
                        self.state.transport.duration = compute_duration(self.state.data_buffer)
                    else:
                        # Create minimal empty data
                        self.state.data_buffer = [(0.0, [0.0, 0.0, 0.0, 0.0])]
                        self.state.transport.duration = 0.0

            # Step 9: Initialize sidebar panels
            update_splash("Setting up UI panels...", 0.9)
            self.sidebar.panels = create_default_panels(self.state)

            # Step 10: Finalize
            update_splash("Finalizing...", 0.95)
            self.cli_renderer = CLIRenderer(self.state)

            # Add welcome message
            info = self.project.get_info()
            self.cli.add_output("tau - Terminal Audio Workstation - Type 'quickstart' for tutorial, 'help' for commands")
            self.cli.add_output(f"Session: {info['current_session']} | Lane 0=logs, Lane 9=events", is_log=True, log_level="INFO")

            # Done!
            self.splash.set_ready()
            SplashRenderer(self.splash).render(scr, h, w)
            scr.refresh()

            self._initialized = True

            # Set initial hash for dirty checking (so we only save if changed)
            self._last_saved_hash = self._get_session_hash({
                'audio_file': self.state.audio_input,
                'data_file': self.state.data_file,
                'position': round(self.state.transport.position, 3),
                'markers': [{'time': m.time, 'label': m.label} for m in self.state.markers.all()],
                'kernel_params': {
                    'tau_a': self.state.kernel.tau_a,
                    'tau_r': self.state.kernel.tau_r,
                    'threshold': self.state.kernel.threshold,
                    'refractory': self.state.kernel.refractory,
                },
                'display_mode': self.state.display.mode,
            })

        except Exception as e:
            self.splash.set_error(str(e))
            SplashRenderer(self.splash).render(scr, h, w)
            scr.refresh()
            raise

    def _detect_video_features(self):
        """Detect video feature availability (non-blocking, graceful degradation)."""
        try:
            import cv2
            self.state.features.video_available = True
            self.state.features.video_enabled = True
            # Note: cv2.__version__ available if needed for logging
        except ImportError:
            self.state.features.video_available = False
            self.state.features.video_enabled = False

    def _load_audio(self, audio_path: str):
        """Load audio file (auto-runs tscale if needed)."""
        from pathlib import Path

        # Try to resolve audio path relative to project directory first
        audio_file = Path(audio_path)
        if not audio_file.is_absolute():
            # Try relative to project directory
            project_relative = self.project.project_dir / audio_path
            if project_relative.exists():
                audio_file = project_relative
            else:
                # Fall back to cwd resolution
                audio_file = self.project.cwd_mgr.resolve_path(audio_path)

        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        # Check for existing data or generate
        runner = TscaleRunner(self.project.trs)

        try:
            data_path = runner.find_or_generate(audio_file, self.state.kernel)

            # Load data
            self.state.data_buffer = load_data_file(str(data_path))
            self.state.transport.duration = compute_duration(self.state.data_buffer)
            self.state.audio_input = str(audio_file)
            self.state.data_file = str(data_path)

            # Load audio to tau-engine for playback (lane 1 by default)
            self.state.transport.load_audio_for_lane(1, audio_file)

        except Exception as e:
            raise

    def _render_fade_in_interface(self, scr, h: int, w: int, fade_progress: float):
        """Render main interface elements fading in during transition."""
        # Only show elements based on fade progress (0.3 to 1.0 maps to 0.0 to 1.0)
        normalized = (fade_progress - 0.3) / 0.7

        # Apply dim attribute for early fade stages
        attr = curses.A_DIM if normalized < 0.7 else 0

        # Header bar fades in first
        if normalized > 0.2:
            header_text = " tau - Terminal Audio Workstation "
            header_attr = curses.color_pair(4) | attr
            x = (w - len(header_text)) // 2
            safe_addstr(scr, 0, max(0, x), header_text, header_attr)

        # Status line at bottom fades in mid
        if normalized > 0.4:
            status = " Ready | Press ':' for CLI | '?' for help "
            status_attr = curses.color_pair(7) | attr
            x = (w - len(status)) // 2
            safe_addstr(scr, h - 1, max(0, x), status, status_attr)

        # Waveform area outline fades in later
        if normalized > 0.6:
            # Draw a simple border hint
            border_char = "─"
            border_attr = curses.color_pair(7) | curses.A_DIM
            border_y = h // 3
            border_line = border_char * (w - 4)
            safe_addstr(scr, border_y, 2, border_line, border_attr)

    def run(self, stdscr):
        """Main curses loop."""
        # Initialize colors first (needed for splash)
        init_colors()

        # Create splash renderer once (reuse to avoid object churn)
        splash_renderer = SplashRenderer(self.splash)

        # Show splash immediately
        stdscr.nodelay(True)
        stdscr.timeout(50)  # Fast updates during splash
        h, w = stdscr.getmaxyx()
        splash_renderer.render(stdscr, h, w)
        stdscr.refresh()

        # Do heavy initialization with splash updates
        self._deferred_init(stdscr)

        # Initialize startup tips system from config (after state is initialized)
        if self.state:
            self.splash.init_startup_tips(
                show_tips=self.state.features.show_startup_tips,
                tips_count=self.state.features.startup_tips_count,
                require_enter=self.state.features.require_enter_to_advance
            )
            # Set video feature flag for tip filtering
            if self.splash.startup:
                self.splash.startup.set_feature('video', self.state.features.video_enabled)

        # Wait for Enter key to dismiss splash (if ready)
        if self.splash.ready:
            stdscr.timeout(100)
            while True:
                self.splash.tick()
                h, w = stdscr.getmaxyx()
                splash_renderer.render(stdscr, h, w)
                stdscr.refresh()
                key = stdscr.getch()

                # Check for dismiss key
                if self.splash.require_enter:
                    # Only Enter key (10 = newline, 13 = carriage return)
                    if key == 10 or key == 13 or key == curses.KEY_ENTER:
                        break
                else:
                    # Any key
                    if key != -1:
                        break

                # Auto-dismiss after delay (disabled when require_enter is True)
                if not self.splash.require_enter and self.splash.should_dismiss():
                    break

        # Show tips pages if enabled
        if self.splash.should_show_tips():
            self.splash.enter_tips_page()
            stdscr.timeout(100)

            while self.splash.should_show_tips():
                h, w = stdscr.getmaxyx()
                splash_renderer.render_tips_page(stdscr, h, w)
                key = stdscr.getch()

                # Enter advances to next tip
                if key == 10 or key == 13 or key == curses.KEY_ENTER:
                    self.splash.advance_tip_page()
                # Escape skips all tips
                elif key == 27:  # Escape
                    break

        # Fade out splash and fade in interface
        self.splash.start_fade()
        stdscr.timeout(16)  # ~60fps for smooth fade
        while not self.splash.is_fade_complete():
            self.splash.update_fade()
            h, w = stdscr.getmaxyx()

            # Render splash (fading out)
            splash_renderer.render(stdscr, h, w)

            # As splash fades, start showing interface elements with increasing opacity
            fade_in = self.splash.fade_progress
            if fade_in > 0.3:
                # Start rendering main interface behind (it will show through as splash fades)
                self._render_fade_in_interface(stdscr, h, w, fade_in)

            stdscr.refresh()
            stdscr.getch()  # consume any keys during fade

        # Hide splash completely
        self.splash.hide()

        # Switch to CLI-optimized timeout
        stdscr.timeout(CLI_POLL_MS)

        self.state.transport.last_update = time.time()

        # Log audio file if loaded
        if self.state.audio_input:
            self.cli.add_output(f"Audio loaded: {self.state.audio_input}", is_log=True, log_level="SUCCESS")
            self.cli.add_output(f"Duration: {self.state.transport.duration:.3f}s, Samples: {len(self.state.data_buffer)}", is_log=True, log_level="INFO")

        # Layout config reference for terminal size checks
        lc = self.state.layout

        # Dirty flags for selective rendering
        need_full_redraw = True
        last_cli_buffer = ""
        last_h, last_w = 0, 0

        # Performance monitor
        from tui_py.rendering.perf_monitor import get_monitor
        perf = get_monitor()

        while True:
            perf.frame_start()

            # Check terminal size
            h, w = stdscr.getmaxyx()
            if w < lc.min_terminal_width or h < lc.min_terminal_height:
                stdscr.erase()
                msg = f"Terminal too small! Need {lc.min_terminal_width}x{lc.min_terminal_height}, got {w}x{h}"
                stdscr.addstr(0, 0, msg[:w-1])
                stdscr.refresh()
                time.sleep(0.1)
                continue

            # Check if terminal resized
            if h != last_h or w != last_w:
                need_full_redraw = True
                last_h, last_w = h, w

            # Update transport
            is_playing = self.state.transport.playing
            if is_playing:
                self.state.transport.update()
                need_full_redraw = True  # Waveform position changed

            # Check if CLI buffer changed (for CLI-only updates)
            cli_buffer_changed = (last_cli_buffer != self.cli.input_buffer)
            if cli_buffer_changed:
                last_cli_buffer = self.cli.input_buffer
                need_full_redraw = True  # Redraw on any input

            # Adjust timeout based on activity
            if is_playing or self.cli.mode:
                stdscr.timeout(CLI_POLL_MS)  # Fast polling when active
            else:
                stdscr.timeout(IDLE_POLL_MS)  # Slow polling when idle

            # Skip rendering if nothing changed (idle optimization)
            if not need_full_redraw and not cli_buffer_changed:
                # Just wait for input, don't render
                perf.frame_end()
                key = stdscr.getch()
                if key == -1:
                    continue
                # Got input - trigger redraw and process
                need_full_redraw = True
                if not self.input_handler.handle_key(key):
                    break
                continue

            # Full screen redraw
            perf.section_start('erase')
            stdscr.erase()
            perf.section_end()
            need_full_redraw = False

            # === LAYOUT (CLI OUTPUT GROWS UPWARD) ===
            # Layout from top to bottom:
            # 1. HEADER (2 rows)
            # 2. DATA LANES (scrollable viewport - shrinks when CLI output grows)
            # 3. CLI OUTPUT (grows upward, max lines configurable)
            # 4. CLI PROMPT (1 row)
            # 5. EVENTS LANE (if visible)
            # 6. LOGS LANE (if visible)
            # 7. CLI STATUS (1 row at bottom)

            # Use layout config from state (allows runtime adjustment)
            lc = self.state.layout

            # Calculate special lanes height (events + logs, or 0 if hidden)
            events_lane = self.state.lanes.get_lane(9)
            logs_lane = self.state.lanes.get_lane(0)
            special_lanes_height = 0
            if events_lane and events_lane.is_visible():
                special_lanes_height += events_lane.get_height()
            if logs_lane and logs_lane.is_visible():
                special_lanes_height += logs_lane.get_height()

            # Calculate available space
            fixed_height = lc.header_height + lc.cli_prompt_height + special_lanes_height + lc.cli_status_height
            available_for_data_and_cli = h - fixed_height

            # Calculate CLI output height - either completions or normal output
            if self.cli.completions_visible:
                # Show completion popup instead of CLI output
                # Height: header (1) + items + blank (1) + preview
                num_items = min(len(self.cli.completion_items), lc.completion_max_items)
                cli_output_height = 1 + num_items + 1 + lc.completion_preview_height
                cli_output_lines = []
            else:
                # Normal CLI output - dynamic sizing
                cli_output_lines = list(self.cli.output)
                num_output_lines = len(cli_output_lines)

                # Calculate max CLI height based on available space
                max_cli_for_this_screen = max(lc.cli_output_min_height,
                                              available_for_data_and_cli - lc.min_data_viewport)
                desired_cli_height = min(num_output_lines, lc.cli_output_max_height)
                cli_output_height = min(desired_cli_height, max_cli_for_this_screen)

                # Truncate lines to what we'll actually display
                if cli_output_height > 0:
                    cli_output_lines = cli_output_lines[-cli_output_height:]
                else:
                    cli_output_lines = []

            # Calculate data lanes viewport height (uses remaining space)
            data_viewport_h = max(lc.min_data_viewport, available_for_data_and_cli - cli_output_height)

            # Render sections
            y_cursor = 0

            # 1. HEADER
            perf.section_start('header')
            render_header(stdscr, self.state, w)
            perf.section_end()
            y_cursor += lc.header_height

            # 2. DATA LANES 1-8 (scrollable viewport)
            perf.section_start('lanes')
            self._render_data_lanes(stdscr, y_cursor, data_viewport_h, w)
            perf.section_end()
            y_cursor += data_viewport_h

            # Calculate fixed positions from bottom up
            status_line_y = h - 1
            cli_prompt_y = status_line_y - special_lanes_height - lc.cli_prompt_offset

            # 3. CLI OUTPUT or COMPLETIONS
            perf.section_start('cli')
            cli_output_y = lc.header_height + data_viewport_h

            # Clear CLI output area to prevent ghosting (especially in CLI-only update mode)
            if cli_buffer_changed:
                # Clear from MINIMUM possible cli_output_y (when popup is at max height)
                # to the bottom of the CLI area to handle moving position
                min_cli_output_y = lc.header_height + lc.min_data_viewport
                max_clear_height = available_for_data_and_cli - lc.min_data_viewport
                for clear_y in range(min_cli_output_y, min(min_cli_output_y + max_clear_height, h)):
                    stdscr.move(clear_y, 0)
                    stdscr.clrtoeol()

            if self.cli.completions_visible:
                # Render completion popup ABOVE the prompt line
                completion_height = self.cli_renderer.render_completions(stdscr, cli_prompt_y, w)
                y_cursor = cli_prompt_y
            else:
                # Render normal CLI output
                self._render_cli_output(stdscr, cli_output_y, cli_output_height, w, cli_output_lines)
                y_cursor = cli_output_y + cli_output_height

            # Calculate the maximum possible special lanes area (when both visible)
            max_special_lanes_height = 0
            if events_lane:
                max_special_lanes_height += events_lane.HEIGHT_SPECIAL
            if logs_lane:
                max_special_lanes_height += logs_lane.HEIGHT_SPECIAL

            # Clear the entire special lanes area (to remove old content when toggled off)
            # But don't clear the prompt line
            if max_special_lanes_height > 0:
                clear_start_y = status_line_y - max_special_lanes_height
                for clear_y in range(clear_start_y, status_line_y):
                    if clear_y > cli_prompt_y:  # Don't clear prompt or above
                        stdscr.move(clear_y, 0)
                        stdscr.clrtoeol()

            # 4. CLI PROMPT (1 row) - render AFTER clearing to ensure it's visible
            self.cli_renderer.render_prompt(stdscr, cli_prompt_y, w)

            # 5. COMPLETION STATUS - one-liner BELOW prompt when completions visible
            if self.cli.completions_visible:
                self.cli_renderer.render_completion_preview(stdscr, cli_prompt_y + 1, w)

            # Render visible special lanes
            if special_lanes_height > 0:
                special_lanes_start_y = status_line_y - special_lanes_height
                if special_lanes_start_y >= y_cursor:
                    y_special = special_lanes_start_y
                    if events_lane and events_lane.is_visible():
                        self._render_special_lane(stdscr, y_special, events_lane, w)
                        y_special += events_lane.get_height()

                    if logs_lane and logs_lane.is_visible():
                        self._render_special_lane(stdscr, y_special, logs_lane, w)
                        y_special += logs_lane.get_height()

            # 6. CLI STATUS LINE (1 row at bottom)
            self.cli_renderer.render_status(stdscr, status_line_y, w)
            perf.section_end()  # end 'cli' section

            # 7. SIDEBAR (renders on right side of CLI output area)
            if self.sidebar.visible:
                sidebar_x = w - self.sidebar.width
                sidebar_y = lc.header_height + data_viewport_h
                sidebar_h = cli_output_height
                SidebarRenderer(self.state, self.sidebar).render(
                    stdscr, sidebar_x, sidebar_y, sidebar_h
                )

            # 8. VIDEO POPUP (overlay on top of everything)
            if self.state.video_popup and self.state.video_popup.visible:
                self.state.video_popup.render(stdscr, self.state.transport, h, w)

            # 9. MODAL DIALOG (overlay on top of everything, highest priority)
            if self.modal.visible:
                ModalRenderer(self.modal).render(stdscr, h, w)

            # Cursor visibility (hide cursor when modal visible)
            try:
                if self.modal.visible:
                    curses.curs_set(1)  # Show cursor for modal input
                else:
                    curses.curs_set(1 if self.cli.mode else 0)
            except:
                pass

            # Refresh
            perf.section_start('refresh')
            stdscr.refresh()
            perf.section_end()

            # End frame timing (after render, before input wait)
            perf.frame_end()

            # Handle input
            key = stdscr.getch()

            # No key - wait for next frame
            if key == -1:
                continue

            # Got input - will need redraw after processing
            need_full_redraw = True
            if not self.input_handler.handle_key(key):
                break  # Quit

    def _render_track_viewport(self, scr, y_start: int, viewport_h: int, width: int):
        """Render scrollable track viewport with visible lanes."""
        if viewport_h < 1:
            return

        visible_lanes = self.state.lanes.get_visible_lanes()
        if not visible_lanes:
            safe_addstr(scr, y_start, 0, "No visible lanes (press 1-4 to show)", curses.A_DIM)
            return

        # Get time window
        left_t, right_t = self.state.transport.compute_window()

        # Start from scroll offset
        scroll_offset = self.state.lanes.scroll_offset
        y_cursor = y_start

        for i, lane in enumerate(visible_lanes[scroll_offset:]):
            lane_h = lane.get_height()

            # Check if we have room for this lane
            if y_cursor + lane_h > y_start + viewport_h:
                # Partial rendering - clip to remaining space
                lane_h = max(0, y_start + viewport_h - y_cursor)
                if lane_h == 0:
                    break

            # Prepare label
            from tui_py.content.lanes import LaneDisplayMode
            mode_markers = {
                LaneDisplayMode.HIDDEN: "○",
                LaneDisplayMode.COMPACT: "c",
                LaneDisplayMode.FULL: "●"
            }
            marker = mode_markers.get(lane.display_mode, "?")
            label = f"[{lane.id+1}:{marker}:{lane.name}]"

            # Create layout dict for rendering functions
            layout = type('obj', (object,), {
                'y': y_cursor,
                'x': 0,
                'h': lane_h,
                'w': width
            })()

            # Render based on lane type
            if lane.is_timebased():
                # Time-based waveform data
                if lane.display_mode == LaneDisplayMode.FULL and lane_h >= 3:
                    # Expanded: full waveform
                    if self.state.display.mode == "envelope":
                        render_waveform_envelope(
                            scr, self.state.data_buffer,
                            left_t, right_t, layout,
                            lane.channel_id, lane.color, lane.gain,
                            label, lane.clip_name
                        )
                    else:
                        render_waveform_points(
                            scr, self.state.data_buffer,
                            left_t, right_t, layout,
                            lane.channel_id, lane.color, lane.gain,
                            label, lane.clip_name
                        )
                else:
                    # Compact: sparkline
                    render_sparkline(
                        scr, self.state.data_buffer,
                        left_t, right_t, layout,
                        lane.channel_id, lane.color, lane.gain, label, lane.clip_name
                    )
            elif lane.is_pinned():
                # Pinned text content
                if lane.display_mode == LaneDisplayMode.FULL and lane_h >= 3:
                    # Expanded: full text panel
                    render_pinned_expanded(
                        scr, lane.content, layout,
                        lane.color, label, lane.clip_name,
                        lane.content_colors
                    )
                else:
                    # Compact: single line preview
                    render_pinned_compact(
                        scr, lane.content, layout,
                        lane.color, label, lane.clip_name
                    )

            y_cursor += lane_h

    def _render_data_lanes(self, scr, y_start: int, viewport_h: int, width: int):
        """Render scrollable data lanes 1-8 in viewport."""
        if viewport_h < 1:
            return

        # Get only data lanes (1-8), filter for visible
        data_lanes = self.state.lanes.get_data_lanes()
        visible_data_lanes = [lane for lane in data_lanes if lane.is_visible()]

        if not visible_data_lanes:
            safe_addstr(scr, y_start, 0, "No visible lanes (press 1-8 to show)", curses.A_DIM)
            return

        # Get time window
        left_t, right_t = self.state.transport.compute_window()

        # Start from scroll offset
        scroll_offset = self.state.lanes.scroll_offset
        y_cursor = y_start

        for i, lane in enumerate(visible_data_lanes[scroll_offset:]):
            lane_h = lane.get_height()

            # Check if we have room for this lane
            if y_cursor + lane_h > y_start + viewport_h:
                # Partial rendering - clip to remaining space
                lane_h = max(0, y_start + viewport_h - y_cursor)
                if lane_h == 0:
                    break

            # Prepare label
            from tui_py.content.lanes import LaneDisplayMode
            mode_markers = {
                LaneDisplayMode.HIDDEN: "○",
                LaneDisplayMode.COMPACT: "c",
                LaneDisplayMode.FULL: "●"
            }
            marker = mode_markers.get(lane.display_mode, "?")
            label = f"[{lane.id}:{marker}:{lane.name}]"

            # Create layout dict for rendering functions
            layout = type('obj', (object,), {
                'y': y_cursor,
                'x': 0,
                'h': lane_h,
                'w': width
            })()

            # Render time-based waveform data
            if lane.display_mode == LaneDisplayMode.FULL and lane_h >= 3:
                # Expanded: full waveform
                if self.state.display.mode == "envelope":
                    render_waveform_envelope(
                        scr, self.state.data_buffer,
                        left_t, right_t, layout,
                        lane.channel_id, lane.color, lane.gain,
                        label, lane.clip_name
                    )
                else:
                    render_waveform_points(
                        scr, self.state.data_buffer,
                        left_t, right_t, layout,
                        lane.channel_id, lane.color, lane.gain,
                        label, lane.clip_name
                    )
            else:
                # Compact: sparkline
                render_sparkline(
                    scr, self.state.data_buffer,
                    left_t, right_t, layout,
                    lane.channel_id, lane.color, lane.gain, label, lane.clip_name
                )

            y_cursor += lane_h

    def _render_special_lane(self, scr, y_start: int, lane, width: int):
        """Render a special lane (events or logs) at fixed position with indentation."""
        lane_h = lane.get_height()

        # Prepare label (indented by 1 column to align with CLI prompt)
        label = f"[{lane.id}:{lane.name}]"

        # Create layout dict with 1-column indent for label, 2-column indent for content
        # The render function will handle the content indent internally
        layout = type('obj', (object,), {
            'y': y_start,
            'x': 1,  # Indent by 1 column to align with CLI prompt
            'h': lane_h,
            'w': width - 1,  # Adjust width for indent
            'content_indent': 2  # Content should be indented by 2 columns
        })()

        # Render pinned content (always expanded for special lanes)
        render_pinned_expanded(
            scr, lane.content, layout,
            lane.color, label, lane.clip_name,
            lane.content_colors
        )

    def _render_cli_output(self, scr, y_start: int, height: int, width: int, output_lines: list):
        """
        Render dynamic CLI output area - the ephemeral stage.

        Features:
        - Centers single-line messages
        - Highlights success/error messages
        - Adds visual breathing room
        - Smart truncation and formatting

        Args:
            scr: curses screen
            y_start: Starting y position
            height: Number of lines to render
            width: Terminal width
            output_lines: Lines to display (already truncated to max height)
        """
        if height == 0:
            return

        # Render output lines
        for i, line in enumerate(output_lines):
            y = y_start + i

            # Detect message types for highlighting
            is_success = line.startswith("✓") or "success" in line.lower()
            is_error = line.startswith("✗") or "error" in line.lower()
            is_warning = "warning" in line.lower()
            is_heading = line.startswith("===") or line.startswith("---")

            # Choose color attribute
            if is_success:
                attr = curses.color_pair(9)  # Green
            elif is_error:
                attr = curses.color_pair(11)  # Red
            elif is_warning:
                attr = curses.color_pair(10)  # Yellow
            elif is_heading:
                attr = curses.A_BOLD | curses.color_pair(7)
            else:
                attr = curses.A_DIM

            # Clear line first, then write
            scr.move(y, 0)
            scr.clrtoeol()

            # Center single-line messages if it's the only line and not too long
            if height == 1 and len(line) < width - 4:
                padding = (width - len(line)) // 2
                x_pos = max(0, padding)
                safe_addstr(scr, y, x_pos, line[:width-1], attr)
            else:
                # Multi-line or long messages: left-aligned with indent
                safe_addstr(scr, y, 2, line[:width-4], attr)

    def _draw_header(self, scr, width):
        """Draw 2-line header with transport and lane status."""
        from tui_py.ui.ui_utils import WidthContext, truncate_middle

        # Width context for adaptive rendering
        wctx = WidthContext.from_width(width)

        # Line 1: Commands and transport
        play_s = "▶PLAY" if self.state.transport.playing else "■STOP"
        pos = self.state.transport.position
        dur = self.state.transport.duration
        pct = (pos / dur * 100) if dur > 0 else 0

        if wctx.compact:
            # Ultra-compact for 80 columns
            line1 = f"[?]help [Q]quit [:CLI] [{play_s}] {pos:.1f}s/{dur:.1f}s z={self.state.transport.span:.2f}s"
        elif wctx.narrow:
            line1 = f"[?]help [Q]quit [:CLI] [{play_s}] {pos:.2f}s/{dur:.2f}s ({pct:.0f}%) zoom={self.state.transport.span:.2f}s"
        else:
            line1 = f"[?]help [Q]quit [:CLI] [{play_s}] {pos:.3f}s/{dur:.3f}s ({pct:.0f}%) zoom={self.state.transport.span:.3f}s"

        safe_addstr(scr, 0, 0, line1[:width-1], curses.A_REVERSE)

        # Line 2: Lane indicators
        from tui_py.content.lanes import LaneDisplayMode
        lane_ind = ""
        num_lanes_to_show = 6 if wctx.compact else 6

        mode_markers = {
            LaneDisplayMode.HIDDEN: "○",
            LaneDisplayMode.COMPACT: "c",
            LaneDisplayMode.FULL: "●"
        }

        for i in range(min(num_lanes_to_show, len(self.state.lanes.lanes))):
            lane = self.state.lanes.get_lane(i)
            if lane:
                marker = mode_markers.get(lane.display_mode, "?")
                if wctx.compact:
                    # Ultra-compact: just [1:●]
                    lane_ind += f"[{i+1}:{marker}]"
                else:
                    # Show shift indicator for cycling modes
                    lane_ind += f"[{i+1}(Shift):{marker}] "

        # Add file info if space available
        if not wctx.compact and self.state.data_file:
            filename = truncate_middle(self.state.data_file, 30)
            lane_ind += f" │ {filename}"

        safe_addstr(scr, 1, 0, lane_ind[:width-1], curses.A_REVERSE)

    def _execute_command(self, cmd_str: str) -> str:
        """
        Execute a command string using the new command system.

        Args:
            cmd_str: Command string (e.g., "zoom 2.0" or "play")

        Returns:
            Output message
        """
        # Parse command and arguments
        parts = cmd_str.strip().split()
        if not parts:
            return ""

        cmd_name = parts[0]
        args = parts[1:]

        # Get command from registry
        cmd_def = COMMAND_REGISTRY.get(cmd_name)
        if not cmd_def:
            return f"✗ Unknown command: {cmd_name} (type 'help' for commands)"

        try:
            # Invoke command
            result = cmd_def.invoke(args)

            # Log successful command execution
            if result and isinstance(result, str):
                # Determine log level from result prefix
                if result.startswith("✓"):
                    self.cli.add_output(f"Command '{cmd_name}' succeeded", is_log=True, log_level="SUCCESS")
                elif result.startswith("✗"):
                    self.cli.add_output(f"Command '{cmd_name}' failed", is_log=True, log_level="ERROR")

            # Return result if it's a string, otherwise empty
            return str(result) if result is not None else ""
        except ValueError as e:
            # Log validation errors
            self.cli.add_output(f"Command '{cmd_name}' validation error: {str(e)}", is_log=True, log_level="WARNING")
            return f"✗ {str(e)}"
        except Exception as e:
            # Log execution errors
            self.cli.add_output(f"Command '{cmd_name}' error: {str(e)}", is_log=True, log_level="ERROR")
            return f"✗ Error: {str(e)}"

    def _show_help(self):
        """Show compact help summary."""
        # Show compact help - most common commands
        help_lines = [
            "=== QUICK HELP ===",
            "",
            "KEYBOARD SHORTCUTS:",
            "  0-9        Toggle lanes (hold to expand)",
            "  Space      Play/pause",
            "  < >        Zoom in/out",
            "  ← →        Scrub left/right",
            "  Home/End   Jump to start/end",
            "  :          Enter CLI mode",
            "  ?          This help",
            "  Q          Quit (Shift+Q)",
            "",
            "CLI COMMANDS (type ':' then command):",
            "  help              Full command reference (pushed to lane 7)",
            "  help <command>    Detailed help for specific command",
            "  list_commands     List all commands by category",
            "",
            "COMMON COMMANDS:",
            "  Transport:  play, stop, seek <t>, home, end",
            "  Zoom:       zoom <sec>, zoom_in (zi), zoom_out (zo)",
            "  Params:     tau_a <t>, tau_r <t>, thr <sigma>, ref <t>",
            "  Markers:    mark <label>, goto <label>, list_markers",
            "  Lanes:      lane <1-8> [on/off/expand/collapse]",
            "  Info:       status, info [params|markers|lanes]",
            "",
            "TIP: Tab completion works for all commands and arguments!"
        ]
        for line in help_lines:
            self.cli.add_output(line)

    def _get_session_hash(self, session_data: dict) -> str:
        """Get hash of session data for dirty checking (excludes timestamp)."""
        import hashlib
        import json
        # Exclude timestamp from hash comparison
        data_for_hash = {k: v for k, v in session_data.items() if k != 'timestamp'}
        return hashlib.md5(json.dumps(data_for_hash, sort_keys=True).encode()).hexdigest()

    def save_state(self):
        """Save session state to data/sessions/{name}.json (only if changed)."""
        # Skip if not fully initialized
        if not self._initialized or not self.state or not self.project:
            return

        try:
            # Convert absolute paths to relative (relative to project directory)
            from pathlib import Path

            audio_file = self.state.audio_input
            if audio_file:
                audio_path = Path(audio_file)
                if audio_path.is_absolute():
                    try:
                        audio_file = str(audio_path.relative_to(self.project.project_dir))
                    except ValueError:
                        # Path is not relative to project, keep absolute
                        pass

            data_file = self.state.data_file
            if data_file:
                data_path = Path(data_file)
                if data_path.is_absolute():
                    try:
                        data_file = str(data_path.relative_to(self.project.project_dir))
                    except ValueError:
                        # Path is not relative to project, keep absolute
                        pass

            # Build session state
            session_data = {
                'timestamp': int(time.time()),
                'audio_file': audio_file,
                'data_file': data_file,
                'position': round(self.state.transport.position, 3),  # Round for stable hash
                'markers': [
                    {'time': m.time, 'label': m.label}
                    for m in self.state.markers.all()
                ],
                'kernel_params': {
                    'tau_a': self.state.kernel.tau_a,
                    'tau_r': self.state.kernel.tau_r,
                    'threshold': self.state.kernel.threshold,
                    'refractory': self.state.kernel.refractory,
                },
                'display_mode': self.state.display.mode,
            }

            # Check if anything changed
            current_hash = self._get_session_hash(session_data)
            if current_hash == self._last_saved_hash:
                return  # No changes, skip save

            self.project.save_session_state(session_data)
            self._last_saved_hash = current_hash
            print(f"Session saved to {self.project.get_session_file().relative_to(self.project.project_dir)}")
        except Exception as e:
            print(f"Warning: Could not save session: {e}")


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="tau - Terminal Audio Workstation with Neural Network Kernel Tuning"
    )
    parser.add_argument(
        'audio',
        nargs='?',
        help='Audio file to load (auto-runs tscale if needed)'
    )
    parser.add_argument(
        '--project-dir',
        help='Project directory (default: search for .snn/)'
    )
    parser.add_argument(
        '--context-dir',
        help='Context directory for cache and recordings (default: ~/recordings/)'
    )
    parser.add_argument(
        '--no-video',
        action='store_true',
        help='Disable video playback features'
    )

    args = parser.parse_args()

    # Create app (minimal init - heavy work happens in TUI with splash)
    app = App(
        audio_path=args.audio,
        project_dir=args.project_dir,
        context_dir=args.context_dir,
        no_video=args.no_video
    )

    # Setup signal handlers with app reference
    def sigint_handler(sig, frame):
        # Stop audio playback if initialized
        if app.state and app.state.transport.tau:
            try:
                app.state.transport.tau.stop_all()
            except:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        # Run curses app (shows splash immediately, then loads)
        curses.wrapper(app.run)
    except curses.error as e:
        print(f"Curses error: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Quick cleanup on exit - just kill engine, don't send stop commands
        if app.state and app.state.transport.tau:
            try:
                if app.state.transport.tau.engine_process:
                    app.state.transport.tau._cleanup_engine()
            except:
                pass
        app.save_state()
        if app._initialized:
            print("\nGoodbye!")


if __name__ == "__main__":
    main()
