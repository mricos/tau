"""
Trs Project command definitions.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_trs_project_commands(app_state):
    """Register trs project commands."""

    # ========== TRS/PROJECT COMMANDS ==========

    registry.register(CommandDef(
        name="load",
        category=CommandCategory.SYSTEM,
        description_short="Load audio file (auto-runs tscale)",
        params=[
            CommandParam("audio_file", ParamType.STRING, "Audio file path (relative to CWD)")
        ],
        handler=lambda audio_file: _load_audio(app_state, audio_file)
    ))

    registry.register(CommandDef(
        name="reload",
        category=CommandCategory.SYSTEM,
        description_short="Reload current audio with updated kernel params",
        handler=lambda: _reload_audio(app_state)
    ))

    registry.register(CommandDef(
        name="cwd",
        category=CommandCategory.SYSTEM,
        description_short="Get or set current working directory",
        params=[
            CommandParam("path", ParamType.STRING, "New working directory path", default=None)
        ],
        handler=lambda path=None: _cwd_command(app_state, path)
    ))

    registry.register(CommandDef(
        name="session",
        category=CommandCategory.SYSTEM,
        description_short="Show current session info",
        handler=lambda: _show_session(app_state)
    ))

    registry.register(CommandDef(
        name="project",
        category=CommandCategory.SYSTEM,
        description_short="Show project info",
        handler=lambda: _show_project(app_state)
    ))

    registry.register(CommandDef(
        name="data",
        category=CommandCategory.SYSTEM,
        description_short="List data files in db/",
        params=[
            CommandParam("action", ParamType.ENUM, "Action to perform",
                        enum_values=["list", "latest"],
                        default="list")
        ],
        handler=lambda action="list": _data_command(app_state, action)
    ))

    # ========== FILESYSTEM COMMANDS ==========

    registry.register(CommandDef(
        name="ls",
        category=CommandCategory.SYSTEM,
        description_short="List files in directory",
        params=[
            CommandParam("path", ParamType.STRING, "Directory path (default: current)", default=".")
        ],
        handler=lambda path=".": _ls_command(app_state, path)
    ))

    registry.register(CommandDef(
        name="cd",
        category=CommandCategory.SYSTEM,
        description_short="Change current directory",
        params=[
            CommandParam("path", ParamType.STRING, "Directory path")
        ],
        handler=lambda path: _cd_command(app_state, path)
    ))

    registry.register(CommandDef(
        name="pwd",
        category=CommandCategory.SYSTEM,
        description_short="Print current working directory",
        handler=lambda: _pwd_command(app_state)
    ))

    # ========== ENGINE COMMANDS ==========

    registry.register(CommandDef(
        name="engine",
        category=CommandCategory.SYSTEM,
        description_short="Show tau-engine status",
        aliases=["eng"],
        handler=lambda: _engine_status(app_state)
    ))

    registry.register(CommandDef(
        name="engine_start",
        category=CommandCategory.SYSTEM,
        description_short="Start tau-engine",
        aliases=["eng_start"],
        handler=lambda: _engine_start(app_state)
    ))

    registry.register(CommandDef(
        name="engine_stop",
        category=CommandCategory.SYSTEM,
        description_short="Stop tau-engine",
        aliases=["eng_stop"],
        handler=lambda: _engine_stop(app_state)
    ))

    registry.register(CommandDef(
        name="engine_restart",
        category=CommandCategory.SYSTEM,
        description_short="Restart tau-engine",
        aliases=["eng_restart"],
        handler=lambda: _engine_restart(app_state)
    ))


# ========== HELPER FUNCTIONS ==========

def _load_audio(app_state, audio_file: str) -> str:
    """Load an audio file, running tscale if needed."""
    from pathlib import Path
    from tau_lib.integration.tscale_runner import TscaleRunner
    from tau_lib.data.data_loader import load_data_file, compute_duration

    project = app_state.project
    if not project:
        return "✗ No project loaded"

    # Resolve path
    audio_path = Path(audio_file)
    if not audio_path.is_absolute():
        # Try relative to project directory first
        project_relative = project.project_dir / audio_file
        if project_relative.exists():
            audio_path = project_relative
        else:
            # Try CWD
            audio_path = project.cwd_mgr.resolve_path(audio_file)

    if not audio_path.exists():
        return f"✗ File not found: {audio_file}"

    try:
        runner = TscaleRunner(project.trs)
        data_path = runner.find_or_generate(audio_path, app_state.kernel)

        # Load data
        app_state.data_buffer = load_data_file(str(data_path))
        app_state.transport.duration = compute_duration(app_state.data_buffer)
        app_state.audio_input = str(audio_path)
        app_state.data_file = str(data_path)

        # Load audio for playback
        if app_state.transport.load_audio_for_lane(1, audio_path):
            return f"✓ Loaded {audio_path.name} ({len(app_state.data_buffer)} samples, {app_state.transport.duration:.2f}s)"
        else:
            return f"✓ Loaded {audio_path.name} (no playback - tau-engine not available)"

    except Exception as e:
        return f"✗ Error loading audio: {e}"


def _reload_audio(app_state) -> str:
    """Reload current audio with updated kernel parameters."""
    if not app_state.audio_input:
        return "✗ No audio loaded"

    from pathlib import Path
    from tau_lib.integration.tscale_runner import TscaleRunner
    from tau_lib.data.data_loader import load_data_file, compute_duration

    project = app_state.project
    if not project:
        return "✗ No project loaded"

    audio_path = Path(app_state.audio_input)
    if not audio_path.exists():
        return f"✗ Audio file not found: {audio_path}"

    try:
        runner = TscaleRunner(project.trs)
        # Force regeneration with current kernel params
        data_path = runner.run(audio_path, app_state.kernel)

        app_state.data_buffer = load_data_file(str(data_path))
        app_state.transport.duration = compute_duration(app_state.data_buffer)
        app_state.data_file = str(data_path)

        return f"✓ Reloaded with τa={app_state.kernel.tau_a:.4f}, τr={app_state.kernel.tau_r:.4f}"

    except Exception as e:
        return f"✗ Error reloading: {e}"


def _cwd_command(app_state, path: str = None) -> str:
    """Get or set current working directory."""
    project = app_state.project
    if not project:
        return "✗ No project loaded"

    if path is None:
        return f"CWD: {project.cwd_mgr.cwd}"
    else:
        try:
            project.cwd_mgr.set_cwd(path)
            return f"✓ CWD: {project.cwd_mgr.cwd}"
        except Exception as e:
            return f"✗ {e}"


def _show_session(app_state) -> str:
    """Show current session info."""
    project = app_state.project
    if not project:
        return "No project loaded"

    info = project.get_info()
    lines = [
        f"Session: {info['current_session']}",
        f"Project: {info['project_dir']}",
    ]
    if app_state.audio_input:
        lines.append(f"Audio: {app_state.audio_input}")
    if app_state.data_file:
        lines.append(f"Data: {app_state.data_file}")

    return "\n".join(lines)


def _show_project(app_state) -> str:
    """Show project info."""
    project = app_state.project
    if not project:
        return "No project loaded"

    info = project.get_info()
    lines = [
        f"Project: {info['project_dir']}",
        f"Session: {info['current_session']}",
        f"Sessions: {', '.join(info['available_sessions']) if info['available_sessions'] else 'none'}",
    ]
    if info['audio_files']:
        lines.append(f"Audio files: {len(info['audio_files'])}")
        for f in info['audio_files'][:5]:
            lines.append(f"  {f}")
        if len(info['audio_files']) > 5:
            lines.append(f"  ... and {len(info['audio_files']) - 5} more")

    return "\n".join(lines)


def _data_command(app_state, action: str) -> str:
    """List or show data files."""
    project = app_state.project
    if not project:
        return "No project loaded"

    if action == "latest":
        latest = project.trs.query_latest(type="data", kind="raw")
        if latest:
            return f"Latest: {latest.filepath.name} ({latest.timestamp})"
        return "No data files found"

    # List all data files
    records = project.trs.query(type="data")
    if not records:
        return "No data files found"

    lines = [f"Data files ({len(records)}):"]
    for r in records[:10]:
        lines.append(f"  {r.filepath.name}")
    if len(records) > 10:
        lines.append(f"  ... and {len(records) - 10} more")

    return "\n".join(lines)


def _ls_command(app_state, path: str = ".") -> str:
    """List files in directory (most recent first)."""
    from pathlib import Path

    project = app_state.project
    if project:
        target = project.cwd_mgr.resolve_path(path)
    else:
        target = Path(path).expanduser().resolve()

    if not target.exists():
        return f"✗ Path not found: {path}"

    if not target.is_dir():
        # Single file info
        return f"{target.name} ({target.stat().st_size} bytes)"

    # List directory - most recent first, directories at top
    entries = list(target.iterdir())
    # Sort: directories first, then by modification time (newest first)
    entries = sorted(entries, key=lambda p: (not p.is_dir(), -p.stat().st_mtime))

    lines = [f"{target}:"]
    for entry in entries[:20]:
        if entry.is_dir():
            lines.append(f"  {entry.name}/")
        else:
            # Show file with size
            size = entry.stat().st_size
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size // 1024}K"
            else:
                size_str = f"{size // (1024 * 1024)}M"
            lines.append(f"  {entry.name} ({size_str})")

    if len(entries) > 20:
        lines.append(f"  ... and {len(entries) - 20} more")

    return "\n".join(lines)


def _cd_command(app_state, path: str) -> str:
    """Change current directory."""
    project = app_state.project
    if not project:
        return "✗ No project loaded"

    try:
        project.cwd_mgr.set_cwd(path)
        return f"✓ {project.cwd_mgr.cwd}"
    except Exception as e:
        return f"✗ {e}"


def _pwd_command(app_state) -> str:
    """Print current working directory."""
    project = app_state.project
    if project:
        return str(project.cwd_mgr.cwd)
    else:
        from pathlib import Path
        return str(Path.cwd())


# ========== ENGINE HELPER FUNCTIONS ==========

def _engine_status(app_state) -> str:
    """Show tau-engine status."""
    tau = app_state.transport.tau
    lines = ["=== Tau Engine Status ==="]

    if tau is None:
        lines.append("Status: NOT CONNECTED")
        lines.append("Engine: Not initialized")
        lines.append("")
        lines.append("Try: :engine_start")
        return "\n".join(lines)

    # Check connection
    try:
        connected = tau.check_connection()
    except Exception:
        connected = False

    if connected:
        lines.append("Status: CONNECTED")
        lines.append(f"Socket: {tau.socket_path}")

        # Show loaded tracks
        if tau.loaded_tracks:
            lines.append(f"Tracks loaded: {len(tau.loaded_tracks)}")
            for track_id, path in tau.loaded_tracks.items():
                lines.append(f"  Track {track_id}: {path.name if hasattr(path, 'name') else path}")
        else:
            lines.append("Tracks loaded: 0")

        # Engine process info
        if tau.engine_process:
            lines.append(f"Engine PID: {tau.engine_process.pid} (auto-started)")
        else:
            lines.append("Engine: External (not managed)")
    else:
        lines.append("Status: DISCONNECTED")
        lines.append(f"Socket: {tau.socket_path}")
        if not tau.socket_path.exists():
            lines.append("  (socket file not found)")
        lines.append("")
        lines.append("Try: :engine_start or :engine_restart")

    return "\n".join(lines)


def _engine_start(app_state) -> str:
    """Start tau-engine."""
    from tau_lib.integration.tau_playback import TauMultitrack

    # Check if already running
    if app_state.transport.tau and app_state.transport.tau.check_connection():
        return "✓ Engine already running"

    try:
        # Try to create new connection with auto-start
        tau = TauMultitrack(auto_start=True)
        if tau.check_connection():
            app_state.transport.tau = tau
            return f"✓ Engine started (socket: {tau.socket_path})"
        else:
            return "✗ Engine started but not responding"
    except FileNotFoundError as e:
        return f"✗ Engine binary not found: {e}"
    except ConnectionError as e:
        return f"✗ Connection failed: {e}"
    except Exception as e:
        return f"✗ Failed to start engine: {e}"


def _engine_stop(app_state) -> str:
    """Stop tau-engine."""
    tau = app_state.transport.tau
    if tau is None:
        return "Engine not initialized"

    try:
        # Stop all playback first
        tau.stop_all()

        # If we auto-started it, terminate the process
        if tau.engine_process:
            tau._cleanup_engine()
            app_state.transport.tau = None
            return "✓ Engine stopped"
        else:
            # External engine - just disconnect
            app_state.transport.tau = None
            return "✓ Disconnected from engine (external engine still running)"
    except Exception as e:
        return f"✗ Error stopping engine: {e}"


def _engine_restart(app_state) -> str:
    """Restart tau-engine."""
    # Stop first
    stop_result = _engine_stop(app_state)

    # Brief pause
    import time
    time.sleep(0.5)

    # Start
    start_result = _engine_start(app_state)

    return f"{stop_result}\n{start_result}"

