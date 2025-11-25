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
from tui_py.layout import compute_layout, get_special_lanes_info, get_max_special_lanes_height
from tui_py.input_handler import InputHandler
from tau_lib.core.project import TauProject
from tau_lib.integration.tscale_runner import TscaleRunner


REFRESH_HZ = 30  # Display refresh rate
CLI_POLL_MS = 5  # CLI input polling rate (ms) - fast for tight timing


class App:
    """Main application."""

    def __init__(self, audio_path: str = None, project_dir: str = None, context_dir: str = None, no_video: bool = False):
        """
        Initialize application.

        Args:
            audio_path: Optional audio file to load (auto-runs tscale if needed)
            project_dir: Optional project directory (default: search for .snn/)
            context_dir: Optional context directory (default: ~/recordings/)
            no_video: Disable video features
        """
        # Initialize project
        print("Initializing tau...")
        self.project = TauProject(project_dir)

        # Show project info
        info = self.project.get_info()
        print(f"Project: {info['project_dir']}")
        print(f"Session: {info['current_session']}")
        if info['audio_files']:
            print(f"Audio: {', '.join(info['audio_files'][:3])}{' ...' if len(info['audio_files']) > 3 else ''}")
        if info['available_sessions']:
            print(f"Sessions: {', '.join(info['available_sessions'])}")

        # Initialize state
        self.state = AppState()

        # Set context directory
        if context_dir:
            from pathlib import Path
            self.state.context_dir = Path(context_dir).expanduser().resolve()
        # else: will use default ~/recordings/ from __post_init__

        # Create context directory if it doesn't exist
        self.state.context_dir.mkdir(parents=True, exist_ok=True)
        print(f"Context directory: {self.state.context_dir}")

        # Video feature detection (lazy, non-blocking)
        if not no_video:
            self._detect_video_features()
        else:
            self.state.features.video_enabled = False
            print("Video features disabled (--no-video)")

        # Initialize CLI
        self.cli = CLIManager()

        # Set up event/log callbacks BEFORE first output
        self.cli.set_event_callback(lambda text, delta_ms: self.state.lanes.add_event(text, delta_ms))
        self.cli.set_log_callback(lambda text, level, delta_ms: self.state.lanes.add_log(text, level, delta_ms))

        self.cli.add_output("tau - Terminal Audio Workstation - Type 'quickstart' for tutorial, 'help' for commands")
        self.cli.add_output(f"System ready. Session: {info['current_session']} | Lane 0=logs, Lane 9=events", is_log=True, log_level="INFO")

        # Initialize CLI renderer (will be set up properly in run() with state)
        self.cli_renderer = None

        # Initialize command registry (new system)
        register_all_commands(self.state)

        # Store project and CLI references for commands and rendering
        self.state.project = self.project
        self.state.cli = self.cli  # Make CLI accessible from state

        # Set up rich completion provider
        from tui_py.ui.completion import get_completions_rich
        self.cli.set_completion_rich_provider(get_completions_rich)

        # Initialize input handler
        self.input_handler = InputHandler(
            state=self.state,
            cli=self.cli,
            execute_command=self._execute_command,
            show_help=self._show_help,
        )

        # Try to load local config
        local_config = self.project.load_local_config()
        if self.project.get_config_file().exists():
            print(f"Loaded config from {self.project.get_config_file().relative_to(self.project.project_dir)}")
            # Apply config (TODO: implement config application)

        # Load or generate data
        if audio_path:
            self._load_audio(audio_path)
        else:
            # Try to load from last session
            session = self.project.load_session_state()
            if session and 'audio_file' in session:
                print(f"Restoring session: {session['audio_file']}")
                self._load_audio(session['audio_file'])
                # Restore position and markers
                if 'position' in session:
                    self.state.transport.position = session['position']
                if 'markers' in session:
                    for m in session['markers']:
                        self.state.markers.add(m['time'], m['label'])
            else:
                # No session, look for latest data
                latest = self.project.trs.query_latest(type="data", kind="raw")
                if latest:
                    print(f"Loading latest data: {latest.filepath.name}")
                    self.state.data_buffer = load_data_file(str(latest.filepath))
                    self.state.transport.duration = compute_duration(self.state.data_buffer)
                    print(f"Loaded {len(self.state.data_buffer)} samples, duration {self.state.transport.duration:.3f}s")
                else:
                    print("No data found. Use :load <audio.wav> to process audio file.")
                    # Create minimal empty data
                    self.state.data_buffer = [(0.0, [0.0, 0.0, 0.0, 0.0])]
                    self.state.transport.duration = 0.0

    def _detect_video_features(self):
        """Detect video feature availability (non-blocking, graceful degradation)."""
        try:
            import cv2
            self.state.features.video_available = True
            self.state.features.video_enabled = True
            print(f"✓ Video features available (opencv-python {cv2.__version__})")
        except ImportError:
            self.state.features.video_available = False
            self.state.features.video_enabled = False
            print("Video features unavailable (install opencv-python for video playback)")

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

        print(f"Loading audio: {audio_file}")

        # Check for existing data or generate
        runner = TscaleRunner(self.project.trs)

        try:
            data_path = runner.find_or_generate(audio_file, self.state.kernel)
            print(f"Using data: {data_path.name}")

            # Load data
            self.state.data_buffer = load_data_file(str(data_path))
            self.state.transport.duration = compute_duration(self.state.data_buffer)
            self.state.audio_input = str(audio_file)
            self.state.data_file = str(data_path)

            print(f"Loaded {len(self.state.data_buffer)} samples, duration {self.state.transport.duration:.3f}s")

            # Load audio to tau-engine for playback (lane 1 by default)
            if self.state.transport.load_audio_for_lane(1, audio_file):
                print(f"✓ Audio loaded to tau-engine for playback")

        except Exception as e:
            print(f"Error processing audio: {e}")
            raise

    def run(self, stdscr):
        """Main curses loop."""
        stdscr.nodelay(True)
        # Start with CLI-optimized timeout (fast input response)
        stdscr.timeout(CLI_POLL_MS)

        init_colors()

        # Initialize CLI renderer with state
        self.cli_renderer = CLIRenderer(self.state)

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

        while True:
            # Check terminal size
            h, w = stdscr.getmaxyx()
            if w < lc.min_terminal_width or h < lc.min_terminal_height:
                stdscr.erase()
                msg = f"Terminal too small! Need {lc.min_terminal_width}x{lc.min_terminal_height}, got {w}x{h}"
                stdscr.addstr(0, 0, msg[:w-1])
                stdscr.refresh()
                time.sleep(0.1)
                continue
            # Update transport
            if self.state.transport.playing:
                self.state.transport.update()
                need_full_redraw = True  # Waveform position changed

            # Get screen size
            h, w = stdscr.getmaxyx()

            # Check if CLI buffer changed (for CLI-only updates)
            cli_buffer_changed = (last_cli_buffer != self.cli.input_buffer)
            if cli_buffer_changed:
                last_cli_buffer = self.cli.input_buffer

            # Smart rendering: only full redraw when needed
            # In CLI mode with no playback, only redraw CLI sections
            if need_full_redraw or not self.cli.mode:
                # Full screen redraw
                stdscr.erase()
                need_full_redraw = False
            elif cli_buffer_changed:
                # CLI-only update: just redraw CLI prompt and status
                # Don't erase - just overwrite CLI sections
                pass  # Will render CLI below

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

            # Render sections (skip expensive parts in CLI-only mode)
            y_cursor = 0

            if not self.cli.mode or need_full_redraw:
                # Full render when not in CLI mode or when redraw needed
                # 1. HEADER
                render_header(stdscr, self.state, w)
                y_cursor += lc.header_height

                # 2. DATA LANES 1-8 (scrollable viewport) - EXPENSIVE
                self._render_data_lanes(stdscr, y_cursor, data_viewport_h, w)
                y_cursor += data_viewport_h

            # 3. CLI OUTPUT or COMPLETIONS (grows upward from prompt)
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
                # Render completion popup
                self.cli_renderer.render_completions(stdscr, cli_output_y, w)
            else:
                # Render normal CLI output
                self._render_cli_output(stdscr, cli_output_y, cli_output_height, w, cli_output_lines)

            y_cursor = cli_output_y + cli_output_height

            # 5. SPECIAL LANES: Events (lane 9) then Logs (lane 0) - between prompt and status
            # Calculate position from bottom up: status_line + special_lanes
            status_line_y = h - 1

            # 4. CLI PROMPT (1 row) - positioned above status with feedback area below
            cli_prompt_y = status_line_y - special_lanes_height - lc.cli_prompt_offset
            self.cli_renderer.render_prompt(stdscr, cli_prompt_y, w)

            # Calculate the maximum possible special lanes area (when both visible)
            max_special_lanes_height = 0
            if events_lane:
                max_special_lanes_height += events_lane.HEIGHT_SPECIAL
            if logs_lane:
                max_special_lanes_height += logs_lane.HEIGHT_SPECIAL

            # Clear the entire special lanes area (to remove old content when toggled off)
            if max_special_lanes_height > 0:
                clear_start_y = status_line_y - max_special_lanes_height
                for clear_y in range(clear_start_y, status_line_y):
                    if clear_y >= y_cursor:  # Don't clear above CLI prompt
                        stdscr.move(clear_y, 0)
                        stdscr.clrtoeol()

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

            # 7. VIDEO POPUP (overlay on top of everything)
            if self.state.video_popup and self.state.video_popup.visible:
                self.state.video_popup.render(stdscr, self.state.transport, h, w)

            # Cursor visibility
            try:
                curses.curs_set(1 if self.cli.mode else 0)
            except:
                pass

            # Refresh
            stdscr.refresh()

            # Handle input
            key = stdscr.getch()

            # No key - tight loop for rhythm interface
            if key == -1:
                continue

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

            # Center single-line messages if it's the only line and not too long
            if height == 1 and len(line) < width - 4:
                padding = (width - len(line)) // 2
                x_pos = max(0, padding)
                safe_addstr(scr, y, x_pos, line[:width-1], attr)
            else:
                # Multi-line or long messages: left-aligned with indent
                safe_addstr(scr, y, 2, line[:width-4], attr)

            # Clear rest of line
            scr.move(y, 0)
            scr.clrtoeol()

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

    def save_state(self):
        """Save session state to data/sessions/{name}.json."""
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

            # Save session state
            session_data = {
                'timestamp': int(time.time()),
                'audio_file': audio_file,
                'data_file': data_file,
                'position': self.state.transport.position,
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
            self.project.save_session_state(session_data)
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

    # Create app first (before signal handlers)
    try:
        app = App(
            audio_path=args.audio,
            project_dir=args.project_dir,
            context_dir=args.context_dir,
            no_video=args.no_video
        )
    except Exception as e:
        print(f"Error initializing app: {e}")
        sys.exit(1)

    # Setup signal handlers with app reference
    def sigint_handler(sig, frame):
        # Stop audio playback
        if app.state.transport.tau:
            try:
                app.state.transport.tau.stop_all()
            except:
                pass
        # Curses will handle the rest
        sys.exit(0)

    signal.signal(signal.SIGINT, sigint_handler)

    try:
        # Run curses app
        curses.wrapper(app.run)
    finally:
        # Stop audio and cleanup on exit
        if app.state.transport.tau:
            try:
                app.state.transport.tau.stop_all()
                # Cleanup auto-started engine
                if app.state.transport.tau.engine_process:
                    app.state.transport.tau._cleanup_engine()
            except:
                pass
        app.save_state()
        print("\nAudio stopped, session saved. Goodbye!")


if __name__ == "__main__":
    main()
