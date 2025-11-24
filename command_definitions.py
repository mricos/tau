"""
Complete command definitions for ASCII Scope SNN.
All commands with handlers, metadata, OSC mapping, and tab-completion.
"""

from .commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_all_commands(app_state):
    """
    Register all SNN commands with the global registry.

    Args:
        app_state: Application state object
    """

    # ========== TRANSPORT COMMANDS ==========

    registry.register(CommandDef(
        name="play",
        category=CommandCategory.TRANSPORT,
        description_short="Start playback",
        description_long="Begin transport playback from current position",
        key_binding="Space",
        handler=lambda: app_state.transport.toggle_play() if app_state.transport.playing else setattr(app_state.transport, 'playing', True)
    ))

    registry.register(CommandDef(
        name="stop",
        category=CommandCategory.TRANSPORT,
        description_short="Stop playback",
        handler=lambda: setattr(app_state.transport, 'playing', False)
    ))

    registry.register(CommandDef(
        name="toggle_play",
        category=CommandCategory.TRANSPORT,
        description_short="Toggle play/pause",
        aliases=["pause"],
        handler=lambda: app_state.transport.toggle_play()
    ))

    registry.register(CommandDef(
        name="seek",
        category=CommandCategory.TRANSPORT,
        description_short="Seek to absolute time position",
        params=[
            CommandParam("time", ParamType.FLOAT, "Time in seconds", min_val=0.0)
        ],
        handler=lambda time: app_state.transport.seek(time)
    ))

    registry.register(CommandDef(
        name="scrub",
        category=CommandCategory.TRANSPORT,
        description_short="Scrub by relative delta",
        params=[
            CommandParam("delta", ParamType.FLOAT, "Time delta in seconds (can be negative)")
        ],
        handler=lambda delta: app_state.transport.scrub(delta)
    ))

    registry.register(CommandDef(
        name="scrub_pct",
        category=CommandCategory.TRANSPORT,
        description_short="Scrub by percentage of duration",
        params=[
            CommandParam("percent", ParamType.FLOAT, "Percentage to scrub (-100 to 100)", min_val=-100, max_val=100)
        ],
        handler=lambda pct: app_state.transport.scrub_pct(pct)
    ))

    registry.register(CommandDef(
        name="home",
        category=CommandCategory.TRANSPORT,
        description_short="Jump to start",
        key_binding="Home",
        handler=lambda: app_state.transport.home()
    ))

    registry.register(CommandDef(
        name="end",
        category=CommandCategory.TRANSPORT,
        description_short="Jump to end",
        key_binding="End",
        handler=lambda: app_state.transport.end()
    ))

    # ========== AUDIO PLAYBACK COMMANDS (TAU) ==========

    registry.register(CommandDef(
        name="load_audio",
        category=CommandCategory.TRANSPORT,
        description_short="Load audio file to lane for playback",
        aliases=["audio"],
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane number (1-8)", min_val=1, max_val=8),
            CommandParam("audio_path", ParamType.STRING, "Path to audio file")
        ],
        handler=lambda lane_id, audio_path: _load_audio_to_lane(app_state, lane_id, audio_path)
    ))

    registry.register(CommandDef(
        name="unload_audio",
        category=CommandCategory.TRANSPORT,
        description_short="Unload audio from lane",
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane number (1-8)", min_val=1, max_val=8)
        ],
        handler=lambda lane_id: _unload_audio_from_lane(app_state, lane_id)
    ))

    registry.register(CommandDef(
        name="audio_gain",
        category=CommandCategory.TRANSPORT,
        description_short="Set audio gain for lane",
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane number (1-8)", min_val=1, max_val=8),
            CommandParam("gain", ParamType.FLOAT, "Gain level (0.0-1.0)", min_val=0.0, max_val=1.0)
        ],
        handler=lambda lane_id, gain: _set_audio_gain(app_state, lane_id, gain)
    ))

    registry.register(CommandDef(
        name="tau_status",
        category=CommandCategory.TRANSPORT,
        description_short="Show tau audio engine status",
        handler=lambda: _show_tau_status(app_state)
    ))

    # ========== ZOOM COMMANDS ==========

    registry.register(CommandDef(
        name="zoom",
        category=CommandCategory.ZOOM,
        description_short="Set zoom span (time window width)",
        params=[
            CommandParam("span", ParamType.FLOAT, "Span in seconds", min_val=0.01)
        ],
        handler=lambda span: app_state.transport.zoom(span)
    ))

    registry.register(CommandDef(
        name="zoom_in",
        category=CommandCategory.ZOOM,
        description_short="Zoom in (decrease span)",
        aliases=["zi"],
        key_binding="<",
        handler=lambda: app_state.transport.zoom_in()
    ))

    registry.register(CommandDef(
        name="zoom_out",
        category=CommandCategory.ZOOM,
        description_short="Zoom out (increase span)",
        aliases=["zo"],
        key_binding=">",
        handler=lambda: app_state.transport.zoom_out()
    ))

    # ========== PARAMETER COMMANDS ==========

    registry.register(CommandDef(
        name="tau_a",
        category=CommandCategory.PARAMS,
        description_short="Set attack time constant",
        description_long="Controls rise time of envelope detector. Smaller = faster attack.",
        params=[
            CommandParam("tau", ParamType.FLOAT, "Time constant in seconds", min_val=0.0001, max_val=1.0)
        ],
        handler=lambda tau: setattr(app_state.kernel, 'tau_a', tau)
    ))

    registry.register(CommandDef(
        name="tau_r",
        category=CommandCategory.PARAMS,
        description_short="Set release time constant",
        description_long="Controls decay time of envelope detector. Smaller = faster release.",
        params=[
            CommandParam("tau", ParamType.FLOAT, "Time constant in seconds", min_val=0.0001, max_val=1.0)
        ],
        handler=lambda tau: setattr(app_state.kernel, 'tau_r', tau)
    ))

    registry.register(CommandDef(
        name="thr",
        category=CommandCategory.PARAMS,
        description_short="Set threshold",
        description_long="Detection threshold in sigma units. Higher = fewer detections.",
        aliases=["threshold"],
        params=[
            CommandParam("threshold", ParamType.FLOAT, "Threshold in sigma", min_val=0.5, max_val=20.0)
        ],
        handler=lambda thr: setattr(app_state.kernel, 'threshold', thr)
    ))

    registry.register(CommandDef(
        name="ref",
        category=CommandCategory.PARAMS,
        description_short="Set refractory period",
        description_long="Minimum time between detections. Prevents double-triggers.",
        aliases=["refractory"],
        params=[
            CommandParam("ref", ParamType.FLOAT, "Refractory period in seconds", min_val=0.001, max_val=1.0)
        ],
        handler=lambda ref: setattr(app_state.kernel, 'refractory', ref)
    ))

    registry.register(CommandDef(
        name="tau_a_semitone",
        category=CommandCategory.PARAMS,
        description_short="Adjust tau_a by musical semitones",
        description_long="±1 semitone = 2^(±1/12) frequency ratio. Useful for musical tuning.",
        params=[
            CommandParam("semitones", ParamType.INT, "Number of semitones (can be negative)", min_val=-24, max_val=24)
        ],
        key_binding="z/Z",
        handler=lambda st: _adjust_tau_semitone(app_state, 'tau_a', st)
    ))

    registry.register(CommandDef(
        name="tau_r_semitone",
        category=CommandCategory.PARAMS,
        description_short="Adjust tau_r by musical semitones",
        params=[
            CommandParam("semitones", ParamType.INT, "Number of semitones (can be negative)", min_val=-24, max_val=24)
        ],
        key_binding="x/X",
        handler=lambda st: _adjust_tau_semitone(app_state, 'tau_r', st)
    ))

    # ========== LANE COMMANDS ==========

    registry.register(CommandDef(
        name="lane_toggle",
        category=CommandCategory.LANES,
        description_short="Toggle lane visibility",
        aliases=["lt"],
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane number (1-8)", min_val=1, max_val=8)
        ],
        handler=lambda lane_id: app_state.lanes.toggle_visibility(lane_id - 1)
    ))

    registry.register(CommandDef(
        name="lane_expand",
        category=CommandCategory.LANES,
        description_short="Toggle lane expand/collapse",
        aliases=["le"],
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane number (1-8)", min_val=1, max_val=8)
        ],
        handler=lambda lane_id: app_state.lanes.toggle_expanded(lane_id - 1)
    ))

    registry.register(CommandDef(
        name="lane_gain",
        category=CommandCategory.LANES,
        description_short="Set lane gain/amplitude",
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane number (1-8)", min_val=1, max_val=8),
            CommandParam("gain", ParamType.FLOAT, "Gain multiplier", min_val=0.1, max_val=10.0)
        ],
        handler=lambda lane_id, gain: app_state.lanes.set_gain(lane_id - 1, gain)
    ))

    # ========== MARKER COMMANDS ==========

    def _marker_completions(arg_index, partial):
        """Dynamic completion for marker labels."""
        if arg_index == 0:  # label parameter
            markers = app_state.markers.all()
            labels = [m.label for m in markers if m.label.startswith(partial)]
            return labels
        return []

    registry.register(CommandDef(
        name="mark",
        category=CommandCategory.MARKERS,
        description_short="Create marker at current position or specified time",
        params=[
            CommandParam("label", ParamType.STRING, "Marker label"),
            CommandParam("time", ParamType.FLOAT, "Time in seconds (default: current position)", default=None)
        ],
        key_binding="m",
        handler=lambda label, time=None: _create_marker(app_state, label, time)
    ))

    registry.register(CommandDef(
        name="goto",
        category=CommandCategory.MARKERS,
        description_short="Jump to marker by label",
        aliases=["goto_marker"],
        params=[
            CommandParam("label", ParamType.STRING, "Marker label")
        ],
        arg_completions=_marker_completions,
        handler=lambda label: _goto_marker(app_state, label)
    ))

    registry.register(CommandDef(
        name="next_marker",
        category=CommandCategory.MARKERS,
        description_short="Jump to next marker",
        aliases=["nm"],
        key_binding="`",
        handler=lambda: _next_marker(app_state)
    ))

    registry.register(CommandDef(
        name="prev_marker",
        category=CommandCategory.MARKERS,
        description_short="Jump to previous marker",
        aliases=["pm"],
        key_binding="~",
        handler=lambda: _prev_marker(app_state)
    ))

    registry.register(CommandDef(
        name="list_markers",
        category=CommandCategory.MARKERS,
        description_short="List all markers",
        aliases=["lm", "markers"],
        handler=lambda: _list_markers(app_state)
    ))

    registry.register(CommandDef(
        name="del_marker",
        category=CommandCategory.MARKERS,
        description_short="Delete marker by label",
        aliases=["dm"],
        params=[
            CommandParam("label", ParamType.STRING, "Marker label")
        ],
        arg_completions=_marker_completions,
        handler=lambda label: app_state.markers.remove(label)
    ))

    # ========== DISPLAY COMMANDS ==========

    registry.register(CommandDef(
        name="envelope",
        category=CommandCategory.DISPLAY,
        description_short="Set envelope rendering mode",
        description_long="Show waveforms as min/max envelope bars",
        handler=lambda: setattr(app_state.display, 'mode', 'envelope')
    ))

    registry.register(CommandDef(
        name="points",
        category=CommandCategory.DISPLAY,
        description_short="Set points rendering mode",
        description_long="Show waveforms as interpolated points",
        handler=lambda: setattr(app_state.display, 'mode', 'points')
    ))

    registry.register(CommandDef(
        name="toggle_mode",
        category=CommandCategory.DISPLAY,
        description_short="Toggle between envelope and points mode",
        aliases=["tm"],
        key_binding="o",
        handler=lambda: app_state.display.toggle_mode()
    ))

    # ========== CONFIG COMMANDS ==========

    registry.register(CommandDef(
        name="save",
        category=CommandCategory.CONFIG,
        description_short="Save configuration to file",
        params=[
            CommandParam("filename", ParamType.STRING, "Config file path (default: ~/.ascii_scope_snn.toml)", default=None)
        ],
        handler=lambda filename=None: _save_config(app_state, filename)
    ))

    registry.register(CommandDef(
        name="load",
        category=CommandCategory.CONFIG,
        description_short="Load configuration from file",
        params=[
            CommandParam("filename", ParamType.STRING, "Config file path")
        ],
        handler=lambda filename: _load_config(app_state, filename)
    ))

    registry.register(CommandDef(
        name="status",
        category=CommandCategory.CONFIG,
        description_short="Show current status",
        aliases=["stat"],
        handler=lambda: _show_status(app_state)
    ))

    registry.register(CommandDef(
        name="info",
        category=CommandCategory.CONFIG,
        description_short="Push detailed info to CLI lanes 7-8",
        params=[
            CommandParam(
                "topic",
                ParamType.ENUM,
                "Info topic",
                enum_values=["params", "markers", "lanes"],
                completions=["params", "markers", "lanes"],
                default="params"
            )
        ],
        handler=lambda topic="params": _push_info(app_state, topic)
    ))

    registry.register(CommandDef(
        name="press_up_quick",
        category=CommandCategory.CONFIG,
        description_short="Set up-quick (tap) max duration in ms",
        aliases=["puq", "press_quick"],
        params=[
            CommandParam("ms", ParamType.INT, "Max duration for quick release (default: 500)", min_val=50, max_val=2000)
        ],
        handler=lambda ms: _set_press_threshold(app_state, "up_quick", ms)
    ))

    registry.register(CommandDef(
        name="press_up_medium",
        category=CommandCategory.CONFIG,
        description_short="Set up-medium (hold) threshold in ms",
        aliases=["pum", "press_medium"],
        params=[
            CommandParam("ms", ParamType.INT, "Hold duration for medium action (default: 500)", min_val=100, max_val=3000)
        ],
        handler=lambda ms: _set_press_threshold(app_state, "up_medium", ms)
    ))

    registry.register(CommandDef(
        name="press_up_long",
        category=CommandCategory.CONFIG,
        description_short="Set up-long (long hold) threshold in ms",
        aliases=["pul", "press_long"],
        params=[
            CommandParam("ms", ParamType.INT, "Hold duration for long action (default: 1000)", min_val=200, max_val=5000)
        ],
        handler=lambda ms: _set_press_threshold(app_state, "up_long", ms)
    ))

    registry.register(CommandDef(
        name="press_double_click",
        category=CommandCategory.CONFIG,
        description_short="Set double-click window in ms",
        aliases=["pdc", "press_dc"],
        params=[
            CommandParam("ms", ParamType.INT, "Max time between clicks (default: 300)", min_val=50, max_val=1000)
        ],
        handler=lambda ms: _set_press_threshold(app_state, "double_click", ms)
    ))

    registry.register(CommandDef(
        name="press_info",
        category=CommandCategory.CONFIG,
        description_short="Show current press threshold settings",
        aliases=["pi"],
        handler=lambda: _show_press_info(app_state)
    ))

    # ========== EVENTS LANE COMMANDS ==========

    registry.register(CommandDef(
        name="events_add",
        category=CommandCategory.UTILITY,
        description_short="Add event to events lane",
        aliases=["event", "log"],
        params=[
            CommandParam("level", ParamType.ENUM, "Event level",
                        enum_values=["debug", "info", "warn", "error"],
                        completions=["debug", "info", "warn", "error"],
                        default="info"),
            CommandParam("message", ParamType.STRING, "Event message")
        ],
        handler=lambda level="info", message="": _events_add(app_state, level, message)
    ))

    registry.register(CommandDef(
        name="events_filter",
        category=CommandCategory.UTILITY,
        description_short="Filter events by level, message, or time",
        aliases=["ef"],
        params=[
            CommandParam("filter_type", ParamType.ENUM, "Filter type",
                        enum_values=["level", "msg", "time", "clear"],
                        completions=["level", "msg", "time", "clear"]),
            CommandParam("value", ParamType.STRING, "Filter value", default="")
        ],
        handler=lambda filter_type, value="": _events_filter(app_state, filter_type, value)
    ))

    registry.register(CommandDef(
        name="events_time_format",
        category=CommandCategory.UTILITY,
        description_short="Set event timestamp format",
        aliases=["etf"],
        params=[
            CommandParam("format", ParamType.ENUM, "Time format",
                        enum_values=["absolute", "relative", "delta", "timestamp"],
                        completions=["absolute", "relative", "delta", "timestamp"])
        ],
        handler=lambda format: _events_time_format(app_state, format)
    ))

    registry.register(CommandDef(
        name="events_stats",
        category=CommandCategory.UTILITY,
        description_short="Show event statistics",
        aliases=["es"],
        handler=lambda: _events_stats(app_state)
    ))

    registry.register(CommandDef(
        name="events_clear",
        category=CommandCategory.UTILITY,
        description_short="Clear all events",
        aliases=["ec"],
        handler=lambda: _events_clear(app_state)
    ))

    # ========== UTILITY COMMANDS ==========

    registry.register(CommandDef(
        name="help",
        category=CommandCategory.UTILITY,
        description_short="Show help for commands",
        aliases=["h", "?"],
        params=[
            CommandParam("command", ParamType.STRING, "Command name (optional)", default=""),
            CommandParam("show_osc", ParamType.BOOL, "Show OSC addresses", default=True)
        ],
        key_binding="?",
        handler=lambda command="", show_osc=True: _show_help(app_state, command if command else None, show_osc)
    ))

    registry.register(CommandDef(
        name="quickstart",
        category=CommandCategory.UTILITY,
        description_short="Interactive quickstart guide for new users",
        aliases=["quick", "intro", "tutorial"],
        handler=lambda: _show_quickstart(app_state)
    ))

    registry.register(CommandDef(
        name="list_commands",
        category=CommandCategory.UTILITY,
        description_short="List all available commands",
        aliases=["lc", "commands"],
        handler=lambda: _list_commands(app_state)
    ))

    registry.register(CommandDef(
        name="clear",
        category=CommandCategory.UTILITY,
        description_short="Clear CLI output history",
        handler=lambda: None  # Handled by CLI manager
    ))

    registry.register(CommandDef(
        name="quit",
        category=CommandCategory.UTILITY,
        description_short="Quit application",
        aliases=["q", "exit"],
        key_binding="q",
        handler=lambda: None  # Handled by main loop
    ))

    # ========== TRS/PROJECT COMMANDS ==========

    registry.register(CommandDef(
        name="load",
        category=CommandCategory.UTILITY,
        description_short="Load audio file (auto-runs tscale)",
        params=[
            CommandParam("audio_file", ParamType.STRING, "Audio file path (relative to CWD)")
        ],
        handler=lambda audio_file: _load_audio(app_state, audio_file)
    ))

    registry.register(CommandDef(
        name="reload",
        category=CommandCategory.UTILITY,
        description_short="Reload current audio with updated kernel params",
        handler=lambda: _reload_audio(app_state)
    ))

    registry.register(CommandDef(
        name="cwd",
        category=CommandCategory.UTILITY,
        description_short="Get or set current working directory",
        params=[
            CommandParam("path", ParamType.STRING, "New working directory path", default=None)
        ],
        handler=lambda path=None: _cwd_command(app_state, path)
    ))

    registry.register(CommandDef(
        name="session",
        category=CommandCategory.UTILITY,
        description_short="Show current session info",
        handler=lambda: _show_session(app_state)
    ))

    registry.register(CommandDef(
        name="project",
        category=CommandCategory.UTILITY,
        description_short="Show project info",
        handler=lambda: _show_project(app_state)
    ))

    registry.register(CommandDef(
        name="data",
        category=CommandCategory.UTILITY,
        description_short="List data files in db/",
        params=[
            CommandParam("action", ParamType.ENUM, "Action to perform",
                        enum_values=["list", "latest"],
                        default="list")
        ],
        handler=lambda action="list": _data_command(app_state, action)
    ))

    # ========== PALETTE AND THEMING COMMANDS ==========

    registry.register(CommandDef(
        name="palette",
        category=CommandCategory.UTILITY,
        description_short="Show color palette inspector",
        aliases=["colors"],
        handler=lambda: _show_palette(app_state)
    ))

    registry.register(CommandDef(
        name="theme",
        category=CommandCategory.UTILITY,
        description_short="Load TDS theme file",
        params=[
            CommandParam("theme_name", ParamType.STRING, "Theme name (e.g., 'warm')")
        ],
        handler=lambda theme_name: _load_theme(app_state, theme_name)
    ))

    # ========== LANE EDITOR COMMANDS ==========

    registry.register(CommandDef(
        name="inspect",
        category=CommandCategory.UTILITY,
        description_short="Inspect data values in current window",
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane ID (1-8)", min_val=1, max_val=8)
        ],
        handler=lambda lane_id: _inspect_lane_data(app_state, lane_id)
    ))

    registry.register(CommandDef(
        name="term_info",
        category=CommandCategory.UTILITY,
        description_short="Show terminal color capabilities",
        handler=lambda: _show_terminal_info()
    ))

    registry.register(CommandDef(
        name="lane",
        category=CommandCategory.UTILITY,
        description_short="Edit lane properties (name, clip_name, gain, color, height, label)",
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane ID (1-8)", min_val=1, max_val=8,
                        completions=["1", "2", "3", "4", "5", "6", "7", "8"]),
            CommandParam("property", ParamType.ENUM, "Property to edit",
                        enum_values=["name", "clip_name", "gain", "color", "height", "label", "visible", "expanded"],
                        completions=["name", "clip_name", "gain", "color", "height", "label", "visible", "expanded"]),
            CommandParam("value", ParamType.STRING, "New value")
        ],
        handler=lambda lane_id, property, value: _edit_lane(app_state, lane_id, property, value)
    ))

    registry.register(CommandDef(
        name="clip",
        category=CommandCategory.UTILITY,
        description_short="Set clip name for a lane",
        params=[
            CommandParam("lane_id", ParamType.INT, "Lane ID (1-8)", min_val=1, max_val=8),
            CommandParam("clip_name", ParamType.STRING, "Clip name (max 16 chars)")
        ],
        handler=lambda lane_id, clip_name: _set_clip_name(app_state, lane_id, clip_name)
    ))

    # ========== SEMANTIC NAME MAPPING COMMANDS ==========

    registry.register(CommandDef(
        name="map",
        category=CommandCategory.UTILITY,
        description_short="Map semantic name to lane",
        params=[
            CommandParam("semantic_name", ParamType.STRING, "Semantic name (e.g., 'kick')"),
            CommandParam("lane_id", ParamType.INT, "Lane ID (1-8)", min_val=1, max_val=8)
        ],
        handler=lambda semantic_name, lane_id: _map_semantic_name(app_state, semantic_name, lane_id)
    ))

    registry.register(CommandDef(
        name="mappings",
        category=CommandCategory.UTILITY,
        description_short="Show all semantic name mappings",
        handler=lambda: _show_mappings(app_state)
    ))

    # Register video commands (if feature is enabled)
    if app_state.features.video_enabled:
        register_video_commands(app_state)


# ========== HELPER FUNCTIONS ==========

def _adjust_tau_semitone(state, param_name, semitones):
    """Adjust tau by musical semitones."""
    SEMITONE_RATIO = 2.0 ** (1.0 / 12.0)
    current = getattr(state.kernel, param_name)
    new_value = current * (SEMITONE_RATIO ** semitones)
    setattr(state.kernel, param_name, new_value)
    return f"✓ {param_name} = {new_value:.6f}s ({semitones:+d} semitones)"


def _create_marker(state, label, time=None):
    """Create marker."""
    if time is None:
        time = state.transport.position
    state.markers.add(time, label)
    return f"✓ Marker '{label}' created at {time:.3f}s"


def _goto_marker(state, label):
    """Jump to marker."""
    marker = state.markers.get_by_label(label)
    if marker:
        state.transport.seek(marker.time)
        return f"✓ Jumped to '{label}' at {marker.time:.3f}s"
    else:
        return f"✗ Marker '{label}' not found"


def _next_marker(state):
    """Jump to next marker."""
    marker = state.markers.find_next(state.transport.position)
    if marker:
        state.transport.seek(marker.time)
        return f"✓ Next marker: '{marker.label}' at {marker.time:.3f}s"
    else:
        return "✗ No next marker"


def _prev_marker(state):
    """Jump to previous marker."""
    marker = state.markers.find_prev(state.transport.position)
    if marker:
        state.transport.seek(marker.time)
        return f"✓ Previous marker: '{marker.label}' at {marker.time:.3f}s"
    else:
        return "✗ No previous marker"


def _list_markers(state):
    """List all markers."""
    markers = state.markers.all()
    if not markers:
        return "No markers"

    lines = ["Markers:", ""] + [f"{m.time:7.3f}s  {m.label}" for m in markers]
    return "\n".join(lines)


def _save_config(state, filename):
    """Save configuration."""
    from .config import save_config, get_default_config_path
    path = filename or get_default_config_path()
    save_config(state, path)
    return f"✓ Config saved to {path}"


def _load_config(state, filename):
    """Load configuration."""
    from .config import load_config
    loaded = load_config(filename)
    if loaded:
        # Update state (preserve data buffer)
        data_buffer = state.data_buffer
        state.__dict__.update(loaded.__dict__)
        state.data_buffer = data_buffer
        return f"✓ Config loaded from {filename}"
    else:
        return f"✗ Failed to load {filename}"


def _show_status(state):
    """Show current status."""
    lines = [
        f"Position: {state.transport.position:.3f}s / {state.transport.duration:.3f}s",
        f"Playing: {state.transport.playing}",
        f"Zoom: {state.transport.span:.3f}s",
        "",
        f"tau_a: {state.kernel.tau_a:.6f}s",
        f"tau_r: {state.kernel.tau_r:.6f}s",
        f"threshold: {state.kernel.threshold:.2f}σ",
        f"refractory: {state.kernel.refractory:.6f}s",
    ]
    return "\n".join(lines)


def _push_info(state, topic):
    """Show info in CLI output."""
    if topic == "params":
        lines = [
            "Kernel Parameters:",
            "",
            f"tau_a: {state.kernel.tau_a:.6f}s",
            f"tau_r: {state.kernel.tau_r:.6f}s",
            f"threshold: {state.kernel.threshold:.2f}σ",
            f"refractory: {state.kernel.refractory:.6f}s",
        ]
        return "\n".join(lines)
    elif topic == "markers":
        markers = state.markers.all()
        if markers:
            lines = ["Markers:", ""] + [f"{m.time:7.3f}s  {m.label}" for m in markers]
        else:
            lines = ["No markers"]
        return "\n".join(lines)
    elif topic == "lanes":
        from .lanes import LaneDisplayMode
        lines = ["Lanes Status:", ""]
        mode_markers = {
            LaneDisplayMode.HIDDEN: "○",
            LaneDisplayMode.COMPACT: "c",
            LaneDisplayMode.FULL: "●"
        }
        for lane in state.lanes.lanes:
            marker = mode_markers.get(lane.display_mode, "?")
            lines.append(f"[{lane.id+1}] {lane.name:8s} {marker} {lane.lane_type}")
        return "\n".join(lines)
    else:
        return f"✗ Unknown topic: {topic}"


def _show_help(state, command, show_osc):
    """Show help."""
    if command:
        # Detailed help for specific command
        cmd = registry.get(command)
        if cmd:
            lines = cmd.format_help(show_osc=show_osc)
            return "\n".join(lines)
        else:
            return f"✗ Unknown command: {command}"
    else:
        # Show compact categorized command overview
        lines = []

        for category in CommandCategory:
            cmds = registry.list_by_category(category)
            if cmds:
                # Category header (compact)
                cat_name = category.category_name
                lines.append(f"=== {cat_name.upper()} ===")

                # Show commands in compact format
                for cmd in cmds:
                    usage = cmd.format_usage()
                    desc = cmd.description_short

                    # Truncate description if too long
                    if len(desc) > 40:
                        desc = desc[:37] + "..."

                    # Add key binding if available (short format)
                    if cmd.key_binding:
                        key = f"[{cmd.key_binding}]"
                        lines.append(f"  {usage:20s} {desc:40s} {key}")
                    else:
                        lines.append(f"  {usage:20s} {desc}")

                lines.append("")

        # Add footer
        lines.append("Type 'help <cmd>' for details. Tab completes commands.")

        return "\n".join(lines)


def _show_quickstart(state):
    """Show quickstart guide for new users."""
    lines = [
        "=== QUICKSTART ===",
        "",
        "KEYBOARD SHORTCUTS:",
        "  1-8: Toggle lanes (hold to expand)",
        "  Space: Play/pause",
        "  </>,./: Zoom in/out",
        "  ←/→: Scrub",
        "  z/Z x/X: Adjust tau_a/tau_r by semitone",
        "",
        "COMMON COMMANDS:",
        "  status              Current parameters",
        "  tau_a <t>           Set attack time",
        "  mark <label>        Create marker",
        "  help <cmd>          Detailed help",
        "",
        "Type 'help' for full command list."
    ]

    return "\n".join(lines)


def _list_commands(state):
    """List all commands grouped by category."""
    lines = []

    total_count = 0
    for category in CommandCategory:
        cmds = registry.list_by_category(category)
        if cmds:
            cat_name = category.category_name
            cmd_names = sorted([cmd.name for cmd in cmds])
            total_count += len(cmd_names)

            cmd_list = ", ".join(cmd_names)
            lines.append(f"{cat_name}: {cmd_list}")

    lines.append("")
    lines.append(f"Total: {total_count} commands. Type 'help' for details.")

    return "\n".join(lines)


# ========== TRS/PROJECT COMMAND HANDLERS ==========

def _load_audio(state, audio_file):
    """Load audio file (auto-runs tscale)."""
    try:
        from .tscale_runner import TscaleRunner
        from .data_loader import load_data_file, compute_duration
        from pathlib import Path

        project = state.project
        audio_path = project.cwd_mgr.resolve_path(audio_file)

        if not audio_path.exists():
            return f"✗ Audio file not found: {audio_file}"

        # Run tscale
        runner = TscaleRunner(project.trs)
        data_path = runner.find_or_generate(audio_path, state.kernel)

        # Load data
        state.data_buffer = load_data_file(str(data_path))
        state.transport.duration = compute_duration(state.data_buffer)
        state.audio_input = str(audio_path)
        state.data_file = str(data_path)

        return f"✓ Loaded {len(state.data_buffer)} samples, {state.transport.duration:.3f}s"

    except Exception as e:
        return f"✗ Error loading audio: {str(e)}"


def _reload_audio(state):
    """Reload current audio with updated kernel params."""
    if not state.audio_input:
        return "✗ No audio file loaded"

    try:
        from .tscale_runner import TscaleRunner
        from .data_loader import load_data_file, compute_duration
        from pathlib import Path

        project = state.project
        audio_path = Path(state.audio_input)

        # Run tscale with current kernel params
        runner = TscaleRunner(project.trs)
        data_path = runner.run(audio_path, state.kernel)

        # Load data
        state.data_buffer = load_data_file(str(data_path))
        state.transport.duration = compute_duration(state.data_buffer)
        state.data_file = str(data_path)

        return f"✓ Reloaded with current params, {state.transport.duration:.3f}s"

    except Exception as e:
        return f"✗ Error reloading: {str(e)}"


def _cwd_command(state, path):
    """Get or set CWD."""
    from pathlib import Path

    project = state.project

    if path is None:
        # Get current CWD
        return f"CWD: {project.cwd_mgr.get_cwd()}"
    else:
        # Set new CWD
        try:
            new_cwd = project.cwd_mgr.set_cwd(Path(path))
            return f"✓ CWD set to: {new_cwd}"
        except Exception as e:
            return f"✗ Error setting CWD: {str(e)}"


def _show_session(state):
    """Show current session info."""
    project = state.project
    session = project.load_session_state()

    if not session:
        return "No session saved"

    lines = [
        "Current Session:",
        "",
        f"Audio: {session.get('audio_file', 'N/A')}",
        f"Position: {session.get('position', 0):.3f}s",
        f"Markers: {len(session.get('markers', []))}",
        f"Mode: {session.get('display_mode', 'N/A')}",
    ]

    return "\n".join(lines)


def _show_project(state):
    """Show project info."""
    project = state.project
    info = project.get_info()

    lines = [
        "Project Info:",
        "",
        f"Project: {info['project_dir']}",
        f"CWD: {info['cwd']}",
        f"DB Size: {info['db_size_mb']} MB",
        "",
        "Records:",
        f"  Data: {info['record_counts']['data']}",
        f"  Config: {info['record_counts']['config']}",
        f"  Session: {info['record_counts']['session']}",
        f"  Log: {info['record_counts']['log']}",
        f"  Audio: {info['record_counts']['audio']}",
    ]

    return "\n".join(lines)


def _data_command(state, action):
    """Data file operations."""
    project = state.project

    if action == "list":
        # List all data files
        records = project.trs.query(type="data", kind="raw")

        if not records:
            return "No data files found"

        lines = [f"Data Files ({len(records)} total):", ""]
        for r in records[:20]:  # Limit to 20
            size_kb = r.filepath.stat().st_size / 1024
            lines.append(f"{r.timestamp}  {r.filepath.name}  ({size_kb:.1f} KB)")

        return "\n".join(lines)

    elif action == "latest":
        latest = project.trs.query_latest(type="data", kind="raw")
        if latest:
            return f"Latest: {latest.filepath.name} ({latest.timestamp})"
        else:
            return "No data files found"

    return f"✗ Unknown action: {action}"


def _show_palette(state):
    """Show color palette inspector with ALL colors from TDS theme."""
    from .palette import ColorPalette
    import curses

    # Get palette from state if available, or create default
    if not hasattr(state, 'palette'):
        state.palette = ColorPalette()

    lines = [
        "Color Palette Inspector",
        "=" * 60,
        f"Theme: {state.palette.theme_name}",
        "",
        "Lane Colors (curses color pairs):",
    ]

    # Show each lane color mapping
    lane_colors = [
        ("Lane 1 (ENV/amber)", state.palette.COLOR_LANE_1, "PALETTE_PRIMARY_300"),
        ("Lane 2 (ENV/amber)", state.palette.COLOR_LANE_2, "PALETTE_PRIMARY_400"),
        ("Lane 3 (MODE/orange)", state.palette.COLOR_LANE_3, "PALETTE_SECONDARY_300"),
        ("Lane 4 (MODE/orange)", state.palette.COLOR_LANE_4, "PALETTE_SECONDARY_400"),
        ("Lane 5 (VERBS/red)", state.palette.COLOR_LANE_5, "PALETTE_ACCENT_300"),
        ("Lane 6 (VERBS/red)", state.palette.COLOR_LANE_6, "PALETTE_ACCENT_400"),
        ("Lane 7 (NOUNS/gray)", state.palette.COLOR_LANE_7, "PALETTE_NEUTRAL_300"),
        ("Lane 8 (NOUNS/gray)", state.palette.COLOR_LANE_8, "PALETTE_NEUTRAL_400"),
    ]

    for name, color_idx, var_name in lane_colors:
        hex_color = state.palette.get_hex(var_name, "#ffffff")
        lines.append(f"  {name:22s} pair({color_idx}) → {var_name:25s} {hex_color}")

    # Show ALL TDS color mappings if theme is loaded
    if state.palette.colors:
        lines.append("")
        lines.append("=" * 60)
        lines.append("TDS Theme Color Variables (ALL):")
        lines.append("=" * 60)

        # Group by palette type
        palettes = {
            "PRIMARY (Amber)": [],
            "SECONDARY (Orange)": [],
            "ACCENT (Red)": [],
            "NEUTRAL (Warm Gray)": [],
            "STATE": []
        }

        for var_name, hex_color in sorted(state.palette.colors.items()):
            if "PRIMARY" in var_name:
                palettes["PRIMARY (Amber)"].append((var_name, hex_color))
            elif "SECONDARY" in var_name:
                palettes["SECONDARY (Orange)"].append((var_name, hex_color))
            elif "ACCENT" in var_name:
                palettes["ACCENT (Red)"].append((var_name, hex_color))
            elif "NEUTRAL" in var_name:
                palettes["NEUTRAL (Warm Gray)"].append((var_name, hex_color))
            elif any(x in var_name for x in ["SUCCESS", "WARNING", "ERROR", "INFO"]):
                palettes["STATE"].append((var_name, hex_color))

        for palette_name, colors in palettes.items():
            if colors:
                lines.append("")
                lines.append(f"{palette_name}:")
                for var_name, hex_color in colors:
                    lines.append(f"  {var_name:30s} {hex_color}")

    return "\n".join(lines)


def _load_theme(state, theme_name):
    """Load TDS theme."""
    from .palette import ColorPalette, find_tds_theme

    # Find theme file
    theme_path = find_tds_theme(theme_name)
    if not theme_path:
        return f"✗ Theme '{theme_name}' not found"

    # Create/update palette
    if not hasattr(state, 'palette'):
        state.palette = ColorPalette()

    # Load theme
    if state.palette.load_tds_theme(theme_path):
        # Apply to curses (may fail if terminal doesn't support color changes)
        if state.palette.apply_to_curses():
            return f"✓ Theme '{theme_name}' loaded and applied"
        else:
            return f"✓ Theme '{theme_name}' loaded (terminal doesn't support color changes)"
    else:
        return f"✗ Failed to load theme '{theme_name}'"


def _show_terminal_info():
    """Show terminal color capabilities."""
    import curses

    lines = ["Terminal Color Capabilities:"]
    lines.append(f"  has_colors: {curses.has_colors()}")
    lines.append(f"  can_change_color: {curses.can_change_color()}")
    lines.append(f"  COLORS: {curses.COLORS}")
    lines.append(f"  COLOR_PAIRS: {curses.COLOR_PAIRS}")

    # Check which mode we're in
    from .palette import find_tds_theme
    theme_path = find_tds_theme("warm")
    if theme_path:
        lines.append(f"  TDS theme: FOUND at {theme_path}")
        lines.append(f"  Background: Using TDS theme dark-gray (RGB 26,26,26)")
    else:
        lines.append(f"  TDS theme: NOT FOUND")
        if curses.can_change_color():
            lines.append(f"  Background: Custom dark-gray (slot 30, RGB 26,26,26)")
        else:
            lines.append(f"  Background: COLOR_BLACK (terminal can't change colors)")

    return "\n".join(lines)


def _inspect_lane_data(state, lane_id):
    """Inspect data values in current window for a lane."""
    lane = state.lanes.get_lane(lane_id - 1)  # Convert to 0-indexed
    if not lane:
        return f"✗ Invalid lane ID: {lane_id}"

    if not lane.is_timebased():
        return f"✗ Lane {lane_id} is not time-based (type: {lane.lane_type})"

    # Get current time window
    left_t, right_t = state.transport.compute_window()

    # Sample first 100 data points in window
    channel_id = lane.channel_id
    sample_count = 0
    values = []

    for t, vals in state.data_buffer:
        if t < left_t:
            continue
        if t > right_t:
            break
        if channel_id >= len(vals):
            continue

        values.append(vals[channel_id])
        sample_count += 1

        if sample_count >= 100:
            break

    if not values:
        return f"✗ No data in window for lane {lane_id} (channel {channel_id})"

    # Calculate statistics
    min_val = min(values)
    max_val = max(values)
    avg_val = sum(values) / len(values)
    abs_max = max(abs(v) for v in values)

    # Count unique values (useful for detecting binary pulse data)
    unique_vals = sorted(set(values))
    unique_str = ", ".join(f"{v:.3f}" for v in unique_vals[:10])
    if len(unique_vals) > 10:
        unique_str += f" ... ({len(unique_vals)} unique)"

    return (f"Lane {lane_id} ({lane.name}) ch={channel_id} samples={sample_count}\n"
            f"  min={min_val:.6f} max={max_val:.6f} avg={avg_val:.6f} abs_max={abs_max:.6f}\n"
            f"  unique values: {unique_str}")


def _edit_lane(state, lane_id, property, value):
    """Edit lane property."""
    lane = state.lanes.get_lane(lane_id - 1)  # Convert to 0-indexed
    if not lane:
        return f"✗ Invalid lane ID: {lane_id}"

    try:
        if property == "name" or property == "label":
            lane.name = value
            return f"✓ Lane {lane_id} name set to '{value}'"
        elif property == "clip_name":
            lane.clip_name = value[:16]  # Truncate to 16 chars
            return f"✓ Lane {lane_id} clip_name set to '{lane.clip_name}'"
        elif property == "gain":
            lane.gain = float(value)
            return f"✓ Lane {lane_id} gain set to {lane.gain}"
        elif property == "color":
            color_val = int(value)
            if 1 <= color_val <= 12:
                lane.color = color_val
                return f"✓ Lane {lane_id} color set to {lane.color}"
            else:
                return f"✗ Color must be 1-12, got {color_val}"
        elif property == "height":
            from .lanes import LaneDisplayMode
            height_val = int(value)
            if height_val == 1:
                lane.display_mode = LaneDisplayMode.COMPACT
                return f"✓ Lane {lane_id} set to compact (1 line)"
            elif height_val <= 5:
                lane.display_mode = LaneDisplayMode.FULL
                return f"✓ Lane {lane_id} set to normal (5 lines)"
            elif height_val <= 20:
                lane.display_mode = LaneDisplayMode.FULL
                return f"✓ Lane {lane_id} set to full (20 lines)"
            else:
                return f"✗ Height must be 1-20, got {height_val}"
        elif property == "visible":
            from .lanes import LaneDisplayMode
            visible_val = value.lower() in ["true", "1", "yes", "on"]
            if visible_val:
                if lane.display_mode == LaneDisplayMode.HIDDEN:
                    lane.display_mode = LaneDisplayMode.FULL
                status = "visible"
            else:
                lane.display_mode = LaneDisplayMode.HIDDEN
                status = "hidden"
            return f"✓ Lane {lane_id} {status}"
        elif property == "expanded":
            from .lanes import LaneDisplayMode
            expanded_val = value.lower() in ["true", "1", "yes", "on"]
            if expanded_val:
                lane.display_mode = LaneDisplayMode.FULL
                status = "normal (5 lines)"
            else:
                lane.display_mode = LaneDisplayMode.COMPACT
                status = "compact (1 line)"
            return f"✓ Lane {lane_id} {status}"
        else:
            return f"✗ Unknown property: {property}"
    except ValueError as e:
        return f"✗ Invalid value for {property}: {value}"


def _set_clip_name(state, lane_id, clip_name):
    """Set clip name for lane."""
    lane = state.lanes.get_lane(lane_id - 1)  # Convert to 0-indexed
    if not lane:
        return f"✗ Invalid lane ID: {lane_id}"

    lane.clip_name = clip_name[:16]  # Truncate to 16 chars
    return f"✓ Lane {lane_id} clip name set to '{lane.clip_name}'"


def _map_semantic_name(state, semantic_name, lane_id):
    """Map semantic name to lane."""
    from .ui_utils import SEMANTIC_MAPPER

    lane = state.lanes.get_lane(lane_id - 1)  # Convert to 0-indexed
    if not lane:
        return f"✗ Invalid lane ID: {lane_id}"

    SEMANTIC_MAPPER.register(semantic_name, lane_id - 1)
    return f"✓ Mapped '{semantic_name}' to lane {lane_id} ({lane.name})"


def _show_mappings(state):
    """Show all semantic name mappings."""
    from .ui_utils import SEMANTIC_MAPPER

    mappings = SEMANTIC_MAPPER.list_all()
    if not mappings:
        return "No semantic name mappings defined"

    lines = [
        "Semantic Name Mappings",
        "=" * 40,
    ]

    # Group by lane ID
    by_lane = {}
    for name, lane_id in mappings:
        if lane_id not in by_lane:
            by_lane[lane_id] = []
        by_lane[lane_id].append(name)

    for lane_id in sorted(by_lane.keys()):
        lane = state.lanes.get_lane(lane_id)
        lane_name = lane.name if lane else f"lane{lane_id}"
        names = ", ".join(by_lane[lane_id])
        lines.append(f"  Lane {lane_id+1} ({lane_name}): {names}")

    return "\n".join(lines)


def _set_press_threshold(state, threshold_type, ms):
    """Deprecated - keypress thresholds no longer used."""
    return f"✗ Keypress thresholds are no longer used. Use keys 1-9 to toggle, Shift+1-9 to cycle modes."


def _show_press_info(state):
    """Show current lane control help."""
    lines = [
        "Lane Control System",
        "=" * 40,
        "",
        "Simple Key Bindings:",
        "  1-9          Toggle visibility (HIDDEN ↔ NORMAL/5-lines)",
        "  Shift+1-9    Cycle display modes:",
        "               COMPACT (1 line) → NORMAL (5 lines) → FULL (20 lines)",
        "",
        "Display Modes:",
        "  HIDDEN (○)   Not visible",
        "  COMPACT (c)  1-line sparkline",
        "  NORMAL (●)   5-line waveform (default)",
        "  FULL (F)     20-line detailed view",
        "",
        "CLI Commands:",
        "  :lane <1-9>          Toggle visibility",
        "  :lane <1-9> on/off   Show/hide lane",
        "  :lane <1-9> expand   Set to normal (5 lines)",
        "  :lane <1-9> collapse Set to compact (1 line)",
        "  :lane <1-9> full     Set to full (20 lines)",
        "  :info lanes          Show all lane status",
    ]

    return "\n".join(lines)


def _events_add(state, level, message):
    """Add an event to the events lane."""
    from .clips import EventLevel

    # Convert string level to EventLevel
    level_map = {
        "debug": EventLevel.DEBUG,
        "info": EventLevel.INFO,
        "warn": EventLevel.WARN,
        "error": EventLevel.ERROR,
    }

    event_level = level_map.get(level.lower(), EventLevel.INFO)

    # Get or create events clip (placeholder - will be integrated properly later)
    # For now, just log to CLI
    return f"✓ Event added: [{level.upper()}] {message}"


def _events_filter(state, filter_type, value):
    """Filter events by level, message, or time range."""
    from .clips import EventFilter, EventLevel

    if filter_type == "clear":
        # Clear filter (placeholder)
        return "✓ Event filter cleared"
    elif filter_type == "level":
        # Parse comma-separated levels
        levels_str = value.lower().split(",")
        level_map = {
            "debug": EventLevel.DEBUG,
            "info": EventLevel.INFO,
            "warn": EventLevel.WARN,
            "error": EventLevel.ERROR,
        }
        levels = [level_map[l.strip()] for l in levels_str if l.strip() in level_map]
        return f"✓ Filtering events by levels: {', '.join(levels_str)}"
    elif filter_type == "msg":
        # Message pattern filter
        return f"✓ Filtering events by message pattern: {value}"
    elif filter_type == "time":
        # Time range filter (e.g., "2.5-5.0")
        return f"✓ Filtering events by time range: {value}"
    else:
        return f"✗ Unknown filter type: {filter_type}"


def _events_time_format(state, format):
    """Set event timestamp display format."""
    from .clips import TimeFormat

    format_map = {
        "absolute": TimeFormat.ABSOLUTE,
        "relative": TimeFormat.RELATIVE,
        "delta": TimeFormat.DELTA,
        "timestamp": TimeFormat.TIMESTAMP,
    }

    time_format = format_map.get(format.lower())
    if not time_format:
        return f"✗ Unknown time format: {format}"

    # Set format (placeholder - will be integrated properly later)
    return f"✓ Event time format set to: {format}"


def _events_stats(state):
    """Show event statistics."""
    # Placeholder - will be integrated properly later
    lines = [
        "Event Statistics",
        "=" * 40,
        "",
        "Total events: 0",
        "Filtered events: 0",
        "",
        "By level:",
        "  DEBUG: 0",
        "  INFO: 0",
        "  WARN: 0",
        "  ERROR: 0",
        "",
        "Delta time stats:",
        "  Mean: 0.0ms",
        "  StdDev: 0.0ms",
    ]

    return "\n".join(lines)


def _events_clear(state):
    """Clear all events."""
    # Placeholder - will be integrated properly later
    return "✓ All events cleared"


# ========== TAU AUDIO PLAYBACK HANDLERS ==========

def _load_audio_to_lane(state, lane_id, audio_path):
    """Load audio file to lane for playback via tau."""
    from pathlib import Path

    # Resolve path
    audio_file = Path(audio_path).expanduser()
    if not audio_file.exists():
        # Try relative to CWD
        audio_file = Path(state.project.cwd_mgr.get_cwd()) / audio_path
        if not audio_file.exists():
            return f"✗ Audio file not found: {audio_path}"

    # Load to lane
    if state.transport.load_audio_for_lane(lane_id, audio_file):
        return f"✓ Loaded {audio_file.name} to lane {lane_id}"
    else:
        return f"✗ Failed to load audio (is tau running? Check: tau status)"


def _unload_audio_from_lane(state, lane_id):
    """Unload audio from lane."""
    if lane_id not in state.transport.loaded_tracks:
        return f"✗ Lane {lane_id} has no audio loaded"

    state.transport.unload_audio_for_lane(lane_id)
    return f"✓ Unloaded audio from lane {lane_id}"


def _set_audio_gain(state, lane_id, gain):
    """Set audio gain for lane."""
    if lane_id not in state.transport.loaded_tracks:
        return f"✗ Lane {lane_id} has no audio loaded"

    state.transport.set_lane_gain(lane_id, gain)
    return f"✓ Lane {lane_id} gain set to {gain:.2f}"


def _show_tau_status(state):
    """Show tau audio engine status."""
    lines = ["Tau Audio Engine Status", "=" * 40, ""]

    # Check if tau is connected
    state.transport._ensure_tau()
    if not state.transport.tau:
        lines.append("✗ Tau not available")
        lines.append("")
        lines.append("To start tau:")
        lines.append("  $ cd ~/src/mricos/demos/tau")
        lines.append("  $ ./tau")
        return "\n".join(lines)

    # Check socket
    if state.transport.tau.check_connection():
        lines.append("✓ Tau engine: Connected")
        lines.append(f"  Socket: {state.transport.tau.socket_path}")
    else:
        lines.append("✗ Tau engine: Socket not found")
        return "\n".join(lines)

    # Show loaded tracks
    lines.append("")
    lines.append("Loaded Tracks:")
    if state.transport.loaded_tracks:
        for lane_id, track_id in sorted(state.transport.loaded_tracks.items()):
            audio_path = state.transport.tau.loaded_tracks.get(track_id)
            if audio_path:
                lines.append(f"  Lane {lane_id} → Track {track_id}: {audio_path.name}")
            else:
                lines.append(f"  Lane {lane_id} → Track {track_id}")
    else:
        lines.append("  (none)")

    lines.append("")
    lines.append("Commands:")
    lines.append("  load_audio <lane> <path>  Load audio to lane")
    lines.append("  audio_gain <lane> <gain>  Set lane volume")
    lines.append("  Space                     Play/pause (synced)")

    return "\n".join(lines)


# Video commands helper functions
def _video_load(state, video_path: str, lane_id: int = 5) -> str:
    """Load video to lane."""
    from pathlib import Path

    if not state.features.video_available:
        return "✗ Video features not available (install opencv-python)"

    if not state.features.video_enabled:
        return "✗ Video features disabled (restart without --no-video)"

    # Resolve path
    video_file = Path(video_path)
    if not video_file.is_absolute():
        video_file = state.project.cwd_mgr.resolve_path(video_path)

    if not video_file.exists():
        return f"✗ Video file not found: {video_file}"

    # Load video
    try:
        from .video_lane import VideoLane

        video_lane = VideoLane(
            video_path=video_file,
            context_dir=state.context_dir,
            thumbnail_size=state.features.video_thumbnail_size,
            sampling_interval=state.features.video_sampling_interval
        )

        if not video_lane.load():
            return f"✗ Failed to load video: {video_file.name}"

        # Store in lane 5 (or specified lane)
        # For now, store in state (we'll integrate with lanes system later)
        if not state.video_popup:
            from .video_popup import VideoPopup
            state.video_popup = VideoPopup(
                video_lane=video_lane,
                resolution=state.features.video_popup_resolution
            )
        else:
            state.video_popup.set_video_lane(video_lane)

        info = video_lane.get_info()
        return f"✓ Video loaded: {info['duration']:.1f}s, {info['resolution']}, {info['num_thumbnails']} frames cached"

    except Exception as e:
        return f"✗ Error loading video: {e}"


def _video_load_session(state, epoch: str) -> str:
    """Load video from screentool session."""
    from pathlib import Path

    if not state.features.video_available:
        return "✗ Video features not available (install opencv-python)"

    try:
        from .video_lane import load_video_from_screentool_session

        video_lane = load_video_from_screentool_session(
            context_dir=state.context_dir,
            epoch=epoch,
            thumbnail_size=state.features.video_thumbnail_size,
            sampling_interval=state.features.video_sampling_interval
        )

        if not video_lane:
            return f"✗ Video not found in session: {epoch}"

        if not video_lane.load():
            return f"✗ Failed to load video from session: {epoch}"

        # Store video
        if not state.video_popup:
            from .video_popup import VideoPopup
            state.video_popup = VideoPopup(
                video_lane=video_lane,
                resolution=state.features.video_popup_resolution
            )
        else:
            state.video_popup.set_video_lane(video_lane)

        info = video_lane.get_info()
        return f"✓ Video loaded from session {epoch}: {info['duration']:.1f}s, {info['num_thumbnails']} frames"

    except Exception as e:
        return f"✗ Error loading video: {e}"


def _video_toggle(state) -> str:
    """Toggle video popup viewer."""
    if not state.video_popup or not state.video_popup.video_lane:
        return "✗ No video loaded (use video_load first)"

    state.video_popup.toggle()
    status = "visible" if state.video_popup.visible else "hidden"
    return f"✓ Video popup: {status}"


def _video_info(state) -> str:
    """Show video information."""
    if not state.video_popup or not state.video_popup.video_lane:
        return "No video loaded"

    info = state.video_popup.video_lane.get_info()
    lines = [
        "=== VIDEO INFO ===",
        f"Path: {info['path']}",
        f"Duration: {info['duration']:.2f}s",
        f"FPS: {info['fps']:.1f}",
        f"Resolution: {info['resolution']}",
        f"Codec: {info['codec']}",
        f"Thumbnail size: {info['thumbnail_size']}x{info['thumbnail_size']}",
        f"Sampling: {info['sampling_interval']} fps",
        f"Cached frames: {info['num_thumbnails']}"
    ]
    return "\n".join(lines)


def _video_resample(state, sampling_interval: float = None, thumbnail_size: int = None) -> str:
    """Regenerate video thumbnail strip with new settings."""
    if not state.video_popup or not state.video_popup.video_lane:
        return "✗ No video loaded"

    video_lane = state.video_popup.video_lane

    # Update settings
    if sampling_interval is not None:
        video_lane.sampling_interval = sampling_interval
        state.features.video_sampling_interval = sampling_interval

    if thumbnail_size is not None:
        video_lane.thumbnail_size = thumbnail_size
        state.features.video_thumbnail_size = thumbnail_size

    # Regenerate
    try:
        if video_lane._generate_thumbnail_strip():
            # Save new cache
            cache_path = video_lane._get_cache_path()
            video_lane._save_cached_strip(cache_path)

            info = video_lane.get_info()
            return f"✓ Video resampled: {info['num_thumbnails']} frames at {info['sampling_interval']} fps"
        else:
            return "✗ Failed to resample video"
    except Exception as e:
        return f"✗ Error resampling: {e}"


# Register video commands
def register_video_commands(app_state):
    """Register video commands."""

    registry.register(CommandDef(
        name="video_load",
        category=CommandCategory.SYSTEM,
        description_short="Load video file for playback",
        params=[
            CommandParam("video_path", ParamType.STRING, "Path to video file (mp4, mkv, etc.)"),
            CommandParam("lane_id", ParamType.INT, "Lane to display in (default: 5)", required=False, default=5)
        ],
        handler=lambda video_path, lane_id=5: _video_load(app_state, video_path, lane_id)
    ))

    registry.register(CommandDef(
        name="video_load_session",
        category=CommandCategory.SYSTEM,
        description_short="Load video from screentool session",
        params=[
            CommandParam("epoch", ParamType.STRING, "Session epoch timestamp")
        ],
        handler=lambda epoch: _video_load_session(app_state, epoch)
    ))

    registry.register(CommandDef(
        name="video_toggle",
        category=CommandCategory.DISPLAY,
        description_short="Toggle video popup viewer",
        aliases=["vt"],
        key_binding="v",
        handler=lambda: _video_toggle(app_state)
    ))

    registry.register(CommandDef(
        name="video_info",
        category=CommandCategory.INFO,
        description_short="Show video information",
        aliases=["vi"],
        handler=lambda: _video_info(app_state)
    ))

    registry.register(CommandDef(
        name="video_resample",
        category=CommandCategory.SYSTEM,
        description_short="Regenerate video thumbnail strip",
        params=[
            CommandParam("sampling_interval", ParamType.FLOAT, "Frames per second to sample", required=False),
            CommandParam("thumbnail_size", ParamType.INT, "NxN thumbnail size", required=False)
        ],
        handler=lambda sampling_interval=None, thumbnail_size=None: _video_resample(app_state, sampling_interval, thumbnail_size)
    ))
