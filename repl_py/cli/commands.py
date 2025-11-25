"""
Command registry for ASCII Scope SNN.
ALL interactions are CLI commands - keyboard shortcuts just invoke these.
"""

import math
import subprocess
import tempfile
import os
import threading
from typing import Callable, List, Any, Optional

from repl_py.cli.parser import parse_command, CommandParseError


# Musical scaling: 1 semitone = 2^(1/12) frequency ratio
SEMITONE_RATIO = 2.0 ** (1.0/12.0)

# Global reprocessing state (thread-safe)
reprocess_lock = threading.Lock()
reprocessing = False
reprocess_status = ""


class CommandRegistry:
    """Registry of all available commands."""

    def __init__(self, app_state):
        self.state = app_state
        self.commands = {}
        self._register_all_commands()

    def _register_all_commands(self):
        """Register all available commands."""

        # ===== TRANSPORT COMMANDS =====
        self.register("play", self.cmd_play, "Start playback")
        self.register("stop", self.cmd_stop, "Stop playback")
        self.register("toggle_play", self.cmd_toggle_play, "Toggle play/pause")
        self.register("seek", self.cmd_seek, "Seek to time: seek <seconds>")
        self.register("scrub", self.cmd_scrub, "Scrub by delta: scrub <seconds>")
        self.register("scrub_pct", self.cmd_scrub_pct, "Scrub by percent: scrub_pct <percent>")
        self.register("home", self.cmd_home, "Jump to start")
        self.register("end", self.cmd_end, "Jump to end")

        # ===== ZOOM COMMANDS =====
        self.register("zoom", self.cmd_zoom, "Set zoom: zoom <span_seconds>")
        self.register("zoom_in", self.cmd_zoom_in, "Zoom in")
        self.register("zoom_out", self.cmd_zoom_out, "Zoom out")

        # ===== CHANNEL COMMANDS =====
        self.register("toggle", self.cmd_toggle, "Toggle channel: toggle ch<N>")
        self.register("gain", self.cmd_gain, "Set gain: gain ch<N> <value> | gain ch<N> <factor>x")
        self.register("offset", self.cmd_offset, "Set offset: offset ch<N> <value>")
        self.register("reset", self.cmd_reset, "Reset channel: reset ch<N>")

        # ===== PARAMETER COMMANDS =====
        self.register("tau_a", self.cmd_tau_a, "Set tau_a: tau_a <seconds>")
        self.register("tau_r", self.cmd_tau_r, "Set tau_r: tau_r <seconds>")
        self.register("thr", self.cmd_thr, "Set threshold: thr <sigma>")
        self.register("ref", self.cmd_ref, "Set refractory: ref <seconds>")
        self.register("tau_a_semitone", self.cmd_tau_a_semitone, "Adjust tau_a by semitones: tau_a_semitone <±N>")
        self.register("tau_r_semitone", self.cmd_tau_r_semitone, "Adjust tau_r by semitones: tau_r_semitone <±N>")
        self.register("reprocess", self.cmd_reprocess, "Reprocess audio with current params")

        # ===== MARKER COMMANDS =====
        self.register("mark", self.cmd_mark, "Create marker: mark <label> | mark <time> <label>")
        self.register("goto", self.cmd_goto, "Jump to marker: goto <label>")
        self.register("list_markers", self.cmd_list_markers, "List all markers")
        self.register("del_marker", self.cmd_del_marker, "Delete marker: del_marker <label>")
        self.register("next_marker", self.cmd_next_marker, "Jump to next marker")
        self.register("prev_marker", self.cmd_prev_marker, "Jump to previous marker")

        # ===== LANE COMMANDS =====
        self.register("lane", self.cmd_lane, "Control lane: lane <1-8> [on/off/expand/collapse]")

        # ===== DISPLAY COMMANDS =====
        self.register("envelope", self.cmd_envelope, "Set envelope rendering mode")
        self.register("points", self.cmd_points, "Set points rendering mode")
        self.register("toggle_mode", self.cmd_toggle_mode, "Toggle rendering mode")

        # ===== CONFIG COMMANDS =====
        self.register("save", self.cmd_save, "Save config: save <filename>")
        self.register("load", self.cmd_load, "Load config: load <filename>")
        self.register("status", self.cmd_status, "Show current status")
        self.register("info", self.cmd_info, "Push detailed info to lanes 7-8: info [params|markers|lanes]")

        # ===== UTILITY COMMANDS =====
        self.register("help", self.cmd_help, "Show help: help | help <command>")
        self.register("list_commands", self.cmd_list_commands, "List all commands")
        self.register("clear", self.cmd_clear, "Clear CLI output")

    def register(self, name: str, handler: Callable, help_text: str):
        """Register a command."""
        self.commands[name] = {
            'handler': handler,
            'help': help_text,
        }

    def execute(self, cmd_str: str) -> str:
        """
        Execute a command string.

        Returns:
            Output message (success/error)
        """
        try:
            verb, args = parse_command(cmd_str)

            if verb not in self.commands:
                return f"? Unknown command: {verb} (type 'help' for commands)"

            # Execute command handler
            handler = self.commands[verb]['handler']
            return handler(args)

        except CommandParseError as e:
            return f"✗ Parse error: {str(e)}"
        except Exception as e:
            return f"✗ Error: {str(e)}"

    # ========== TRANSPORT COMMAND HANDLERS ==========

    def cmd_play(self, args):
        self.state.transport.playing = True
        self.state.transport.last_update = __import__('time').time()
        return "✓ Playing"

    def cmd_stop(self, args):
        self.state.transport.playing = False
        return "✓ Stopped"

    def cmd_toggle_play(self, args):
        self.state.transport.toggle_play()
        return "✓ Playing" if self.state.transport.playing else "✓ Stopped"

    def cmd_seek(self, args):
        if len(args) < 1:
            return "✗ Usage: seek <seconds>"
        self.state.transport.seek(float(args[0]))
        return f"✓ Seek to {self.state.transport.position:.3f}s"

    def cmd_scrub(self, args):
        if len(args) < 1:
            return "✗ Usage: scrub <seconds>"
        delta = float(args[0])
        self.state.transport.scrub(delta)
        return f"✓ Scrubbed to {self.state.transport.position:.3f}s"

    def cmd_scrub_pct(self, args):
        if len(args) < 1:
            return "✗ Usage: scrub_pct <percent>"
        pct = float(args[0])
        self.state.transport.scrub_pct(pct)
        return f"✓ Scrubbed to {self.state.transport.position:.3f}s"

    def cmd_home(self, args):
        self.state.transport.home()
        return "✓ Jump to start"

    def cmd_end(self, args):
        self.state.transport.end()
        return "✓ Jump to end"

    # ========== ZOOM COMMAND HANDLERS ==========

    def cmd_zoom(self, args):
        if len(args) < 1:
            return "✗ Usage: zoom <seconds>"
        self.state.transport.zoom(float(args[0]))
        return f"✓ Zoom = {self.state.transport.span:.3f}s"

    def cmd_zoom_in(self, args):
        self.state.transport.zoom_in()
        return f"✓ Zoom = {self.state.transport.span:.3f}s"

    def cmd_zoom_out(self, args):
        self.state.transport.zoom_out()
        return f"✓ Zoom = {self.state.transport.span:.3f}s"

    # ========== CHANNEL COMMAND HANDLERS ==========

    def _extract_channel_id(self, args, arg_index=0) -> Optional[int]:
        """Extract channel ID from args."""
        if len(args) <= arg_index:
            return None
        arg = args[arg_index]
        if isinstance(arg, tuple) and arg[0] == 'channel':
            return arg[1]
        return None

    def cmd_toggle(self, args):
        ch_id = self._extract_channel_id(args, 0)
        if ch_id is None:
            return "✗ Usage: toggle ch<N>"
        self.state.channels.toggle_visibility(ch_id)
        ch = self.state.channels.get(ch_id)
        status = "ON" if ch.visible else "off"
        return f"✓ {ch.name}: {status}"

    def cmd_gain(self, args):
        ch_id = self._extract_channel_id(args, 0)
        if ch_id is None or len(args) < 2:
            return "✗ Usage: gain ch<N> <value> | gain ch<N> <factor>x"

        value = args[1]

        # Check if it's a multiplier
        if isinstance(value, tuple) and value[0] == 'x':
            self.state.channels.multiply_gain(ch_id, value[1])
            return f"✓ {self.state.channels.get(ch_id).name} gain = {self.state.channels.get(ch_id).gain:.3f}"
        else:
            self.state.channels.set_gain(ch_id, float(value))
            return f"✓ {self.state.channels.get(ch_id).name} gain = {self.state.channels.get(ch_id).gain:.3f}"

    def cmd_offset(self, args):
        ch_id = self._extract_channel_id(args, 0)
        if ch_id is None or len(args) < 2:
            return "✗ Usage: offset ch<N> <value>"

        self.state.channels.set_offset(ch_id, float(args[1]))
        return f"✓ {self.state.channels.get(ch_id).name} offset = {self.state.channels.get(ch_id).offset:.2f}"

    def cmd_reset(self, args):
        ch_id = self._extract_channel_id(args, 0)
        if ch_id is None:
            return "✗ Usage: reset ch<N>"
        self.state.channels.reset_channel(ch_id)
        return f"✓ {self.state.channels.get(ch_id).name} reset"

    # ========== PARAMETER COMMAND HANDLERS ==========

    def _format_tau(self, tau_sec):
        """Format tau in ms or μs."""
        if tau_sec >= 0.001:
            return f"{tau_sec*1000:.2f}ms"
        else:
            return f"{tau_sec*1e6:.1f}μs"

    def _compute_fc(self):
        """Compute pseudo center frequency from tau_a and tau_r."""
        ta = self.state.kernel.tau_a
        tr = self.state.kernel.tau_r
        return 1.0 / (2.0 * math.pi * math.sqrt(ta * tr))

    def cmd_tau_a(self, args):
        if len(args) < 1:
            return "✗ Usage: tau_a <seconds>"
        self.state.kernel.tau_a = float(args[0])
        return f"✓ tau_a = {self._format_tau(self.state.kernel.tau_a)}"

    def cmd_tau_r(self, args):
        if len(args) < 1:
            return "✗ Usage: tau_r <seconds>"
        self.state.kernel.tau_r = float(args[0])
        return f"✓ tau_r = {self._format_tau(self.state.kernel.tau_r)}"

    def cmd_thr(self, args):
        if len(args) < 1:
            return "✗ Usage: thr <sigma>"
        self.state.kernel.threshold = float(args[0])
        return f"✓ threshold = {self.state.kernel.threshold:.2f}σ"

    def cmd_ref(self, args):
        if len(args) < 1:
            return "✗ Usage: ref <seconds>"
        self.state.kernel.refractory = float(args[0])
        return f"✓ refractory = {self._format_tau(self.state.kernel.refractory)}"

    def cmd_tau_a_semitone(self, args):
        if len(args) < 1:
            return "✗ Usage: tau_a_semitone <±N>"
        semitones = int(args[0])
        factor = SEMITONE_RATIO ** semitones
        self.state.kernel.tau_a *= factor
        self.state.kernel.tau_a = max(1e-6, min(0.1, self.state.kernel.tau_a))
        return f"✓ tau_a = {self._format_tau(self.state.kernel.tau_a)}"

    def cmd_tau_r_semitone(self, args):
        if len(args) < 1:
            return "✗ Usage: tau_r_semitone <±N>"
        semitones = int(args[0])
        factor = SEMITONE_RATIO ** semitones
        self.state.kernel.tau_r *= factor
        self.state.kernel.tau_r = max(self.state.kernel.tau_a * 1.01, min(1.0, self.state.kernel.tau_r))
        return f"✓ tau_r = {self._format_tau(self.state.kernel.tau_r)}"

    def cmd_reprocess(self, args):
        """Trigger audio reprocessing with current kernel params."""
        global reprocessing

        with reprocess_lock:
            if reprocessing:
                return "⟳ Already processing..."

        if not self.state.audio_input or not os.path.exists(self.state.audio_input):
            return "✗ No audio input file"

        # Start background thread
        thread = threading.Thread(
            target=self._reprocess_worker,
            daemon=True
        )
        thread.start()
        return "✓ Reprocessing..."

    def _reprocess_worker(self):
        """Background worker for reprocessing."""
        global reprocessing, reprocess_status

        from tau_lib.data.data_loader import load_data_file, compute_duration

        with reprocess_lock:
            reprocessing = True

        try:
            # Create temp output file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tmp:
                tmp_path = tmp.name

            # Build tscale command
            cmd = ['./tscale', '-i', self.state.audio_input]
            cmd.extend(self.state.kernel.to_tscale_args())
            cmd.extend(['-norm', 'l2', '-sym', '-mode', 'iir', '-o', tmp_path])

            # Run tscale
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                with reprocess_lock:
                    reprocess_status = f"✗ tscale error"
                    reprocessing = False
                os.unlink(tmp_path)
                return

            # Load new data
            new_buffer = load_data_file(tmp_path)
            new_duration = compute_duration(new_buffer)

            # Atomically replace data
            with reprocess_lock:
                self.state.data_buffer = new_buffer
                self.state.transport.duration = new_duration
                reprocess_status = "✓ Reprocessed"
                reprocessing = False

            os.unlink(tmp_path)

        except subprocess.TimeoutExpired:
            with reprocess_lock:
                reprocess_status = "✗ Timeout"
                reprocessing = False
        except Exception as e:
            with reprocess_lock:
                reprocess_status = f"✗ Error: {str(e)[:20]}"
                reprocessing = False

    # ========== MARKER COMMAND HANDLERS ==========

    def cmd_mark(self, args):
        if len(args) == 0:
            return "✗ Usage: mark <label> | mark <time> <label>"

        # mark <label> - create at current playhead
        if len(args) == 1:
            label = str(args[0])
            time = self.state.transport.position
        # mark <time> <label>
        elif len(args) == 2:
            time = float(args[0])
            label = str(args[1])
        else:
            return "✗ Usage: mark <label> | mark <time> <label>"

        try:
            self.state.markers.add(time, label)
            return f"✓ Marker '{label}' at {time:.3f}s"
        except ValueError as e:
            return f"✗ {str(e)}"

    def cmd_goto(self, args):
        if len(args) < 1:
            return "✗ Usage: goto <label>"
        label = str(args[0])
        marker = self.state.markers.get_by_label(label)
        if not marker:
            return f"✗ Marker '{label}' not found"
        self.state.transport.seek(marker.time)
        return f"✓ Jumped to '{label}' at {marker.time:.3f}s"

    def cmd_list_markers(self, args):
        markers = self.state.markers.all()
        if not markers:
            return "No markers"
        lines = [f"{m.time:.3f}s: {m.label}" for m in markers]
        return " | ".join(lines[:3])  # Show first 3

    def cmd_del_marker(self, args):
        if len(args) < 1:
            return "✗ Usage: del_marker <label>"
        label = str(args[0])
        if self.state.markers.remove(label):
            return f"✓ Deleted marker '{label}'"
        return f"✗ Marker '{label}' not found"

    def cmd_next_marker(self, args):
        marker = self.state.markers.find_next(self.state.transport.position)
        if not marker:
            return "✗ No next marker"
        self.state.transport.seek(marker.time)
        return f"✓ Next: '{marker.label}' at {marker.time:.3f}s"

    def cmd_prev_marker(self, args):
        marker = self.state.markers.find_prev(self.state.transport.position)
        if not marker:
            return "✗ No previous marker"
        self.state.transport.seek(marker.time)
        return f"✓ Prev: '{marker.label}' at {marker.time:.3f}s"

    # ========== LANE COMMAND HANDLERS ==========

    def cmd_lane(self, args):
        """Toggle lane visibility or set explicit state."""
        if len(args) < 1:
            return "✗ Usage: lane <1-8> | lane <1-8> on/off | lane <1-8> expand/collapse"

        lane_num = int(args[0])
        lane_id = lane_num - 1  # Convert to 0-based

        lane = self.state.lanes.get_lane(lane_id)
        if not lane:
            return f"✗ Lane must be 1-{len(self.state.lanes.lanes)}"

        if len(args) == 1:
            # Toggle visibility
            msg = self.state.lanes.toggle_visibility(lane_id)
            return f"✓ {msg}"
        else:
            from tui_py.content.lanes import LaneDisplayMode
            action = args[1].lower()
            if action in ('on', 'show', 'true', '1'):
                if lane.display_mode == LaneDisplayMode.HIDDEN:
                    lane.display_mode = LaneDisplayMode.FULL
                return f"✓ Lane {lane_num} ({lane.name}): visible"
            elif action in ('off', 'hide', 'false', '0'):
                lane.display_mode = LaneDisplayMode.HIDDEN
                return f"✓ Lane {lane_num} ({lane.name}): hidden"
            elif action in ('expand', 'e'):
                lane.display_mode = LaneDisplayMode.FULL
                return f"✓ Lane {lane_num} ({lane.name}): normal (5 lines)"
            elif action in ('collapse', 'c'):
                lane.display_mode = LaneDisplayMode.COMPACT
                return f"✓ Lane {lane_num} ({lane.name}): compact (1 line)"
            elif action in ('full', 'f'):
                lane.display_mode = LaneDisplayMode.FULL
                return f"✓ Lane {lane_num} ({lane.name}): full (20 lines)"
            else:
                return f"✗ Unknown action: {action}"

    # ========== DISPLAY COMMAND HANDLERS ==========

    def cmd_envelope(self, args):
        self.state.display.mode = "envelope"
        return "✓ Envelope mode"

    def cmd_points(self, args):
        self.state.display.mode = "points"
        return "✓ Points mode"

    def cmd_toggle_mode(self, args):
        self.state.display.toggle_mode()
        return f"✓ {self.state.display.mode.capitalize()} mode"

    # ========== CONFIG COMMAND HANDLERS ==========

    def cmd_save(self, args):
        from tau_lib.core.config import save_config, get_default_config_path

        if len(args) == 0:
            path = get_default_config_path()
        else:
            path = str(args[0])

        try:
            save_config(self.state, path)
            return f"✓ Saved to {path}"
        except Exception as e:
            return f"✗ Save failed: {str(e)}"

    def cmd_load(self, args):
        from tau_lib.core.config import load_config

        if len(args) < 1:
            return "✗ Usage: load <filename>"

        path = str(args[0])
        try:
            loaded_state = load_config(path)
            if not loaded_state:
                return f"✗ File not found: {path}"

            # Copy loaded state (preserve data_buffer)
            data_buffer = self.state.data_buffer
            self.state.__dict__.update(loaded_state.__dict__)
            self.state.data_buffer = data_buffer

            return f"✓ Loaded from {path}"
        except Exception as e:
            return f"✗ Load failed: {str(e)}"

    def cmd_status(self, args):
        """Show current status."""
        pos = self.state.transport.position
        dur = self.state.transport.duration
        ta = self._format_tau(self.state.kernel.tau_a)
        tr = self._format_tau(self.state.kernel.tau_r)
        thr = self.state.kernel.threshold

        return f"pos={pos:.3f}s/{dur:.3f}s τa={ta} τr={tr} thr={thr:.1f}σ"

    # ========== UTILITY COMMAND HANDLERS ==========

    def cmd_help(self, args):
        if len(args) == 0:
            return "Commands: tau_a/tau_r/thr/ref | play/stop/seek/zoom | mark/goto | gain/offset/toggle | help <cmd>"

        cmd = str(args[0])
        if cmd in self.commands:
            return self.commands[cmd]['help']
        return f"? Unknown command: {cmd}"

    def cmd_list_commands(self, args):
        """List all commands."""
        return " | ".join(sorted(self.commands.keys())[:10]) + "..."

    def cmd_clear(self, args):
        """Clear output (handled by CLI manager)."""
        return ""  # CLI manager will clear

    def cmd_info(self, args):
        """Push detailed info to CLI result lanes 7-8."""
        info_type = args[0] if args else "params"

        if info_type == "params":
            # Kernel parameters info
            lines = [
                "Kernel Parameters:",
                "",
                f"tau_a:      {self._format_tau(self.state.kernel.tau_a)}",
                f"tau_r:      {self._format_tau(self.state.kernel.tau_r)}",
                f"threshold:  {self.state.kernel.threshold:.2f} sigma",
                f"refractory: {self.state.kernel.refractory*1000:.2f} ms",
                f"sample_rate: {self.state.kernel.fs:.0f} Hz",
                "",
                f"fc (pseudo): {self._compute_fc():.1f} Hz",
            ]
            return "\n".join(lines)

        elif info_type == "markers":
            # Markers info
            markers = self.state.markers.all()
            if not markers:
                lines = ["No markers defined"]
            else:
                lines = ["Markers:", ""]
                for m in markers:
                    lines.append(f"{m.time:7.3f}s  {m.label}")
            return "\n".join(lines)

        elif info_type == "lanes":
            # Lanes info
            from tui_py.content.lanes import LaneDisplayMode
            mode_markers = {
                LaneDisplayMode.HIDDEN: "○",
                LaneDisplayMode.COMPACT: "c",
                LaneDisplayMode.FULL: "●"
            }
            lines = ["Lanes Status:", ""]
            for lane in self.state.lanes.lanes:
                marker = mode_markers.get(lane.display_mode, "?")
                ltype = lane.lane_type[:4]  # "time" or "pinn"
                lines.append(f"[{lane.id+1}] {lane.name:8s} {marker} {ltype} color={lane.color}")
            return "\n".join(lines)

        else:
            return f"✗ Unknown info type: {info_type} (use: params|markers|lanes)"

