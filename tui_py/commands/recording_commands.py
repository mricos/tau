"""
Recording and device management commands.

Provides commands for:
- Device enumeration and selection
- Recording start/stop/status
- Tetra configuration (apps, profiles, aliases)
"""

from pathlib import Path
from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_recording_commands(app_state):
    """Register recording and device management commands."""

    # ========== DEVICE COMMANDS ==========

    registry.register(CommandDef(
        name="devices",
        category=CommandCategory.SYSTEM,
        description_short="List available audio devices",
        description_long="List capture and playback devices from tau-engine",
        aliases=["dev"],
        params=[
            CommandParam("type", ParamType.STRING, "Device type: capture, playback, or all",
                        default="all", completions=["all", "capture", "playback"])
        ],
        handler=lambda type="all": _list_devices(app_state, type)
    ))

    registry.register(CommandDef(
        name="device",
        category=CommandCategory.SYSTEM,
        description_short="Select audio device",
        description_long="Select capture or playback device by name, alias, or index",
        params=[
            CommandParam("type", ParamType.STRING, "Device type: capture or playback",
                        completions=["capture", "playback"]),
            CommandParam("identifier", ParamType.STRING, "Device name, alias, index, or 'default'")
        ],
        handler=lambda type, identifier: _select_device(app_state, type, identifier)
    ))

    registry.register(CommandDef(
        name="aliases",
        category=CommandCategory.SYSTEM,
        description_short="Show device aliases",
        description_long="List friendly name aliases from ~/.config/tetra/devices.toml",
        handler=lambda: _show_aliases(app_state)
    ))

    registry.register(CommandDef(
        name="alias",
        category=CommandCategory.SYSTEM,
        description_short="Set device alias",
        description_long="Create a friendly name for a device pattern",
        params=[
            CommandParam("name", ParamType.STRING, "Alias name (e.g., 'podcaster')"),
            CommandParam("pattern", ParamType.STRING, "Device name pattern to match"),
            CommandParam("type", ParamType.STRING, "Device type: capture or playback",
                        default="capture", completions=["capture", "playback"])
        ],
        handler=lambda name, pattern, type="capture": _set_alias(app_state, name, pattern, type)
    ))

    # ========== RECORDING COMMANDS ==========

    registry.register(CommandDef(
        name="record",
        category=CommandCategory.SYSTEM,
        description_short="Start recording",
        description_long="Start recording audio from capture device",
        aliases=["rec"],
        params=[
            CommandParam("path", ParamType.STRING, "Output file path (optional, auto-generated if empty)",
                        default="")
        ],
        key_binding="r",
        handler=lambda path="": _start_recording(app_state, path)
    ))

    registry.register(CommandDef(
        name="record_stop",
        category=CommandCategory.SYSTEM,
        description_short="Stop recording",
        aliases=["stop_rec"],
        key_binding="R",
        handler=lambda: _stop_recording(app_state)
    ))

    registry.register(CommandDef(
        name="record_status",
        category=CommandCategory.SYSTEM,
        description_short="Show recording status",
        handler=lambda: _recording_status(app_state)
    ))

    # ========== TETRA CONFIG COMMANDS ==========

    registry.register(CommandDef(
        name="apps",
        category=CommandCategory.SYSTEM,
        description_short="List apps using tetra",
        description_long="Show apps with configuration in ~/.config/tetra/apps/",
        params=[
            CommandParam("app_name", ParamType.STRING, "Show specific app config (optional)",
                        default="")
        ],
        handler=lambda app_name="": _list_apps(app_state, app_name)
    ))

    registry.register(CommandDef(
        name="profiles",
        category=CommandCategory.SYSTEM,
        description_short="List recording profiles",
        description_long="Show profiles from ~/.config/tetra/profiles/",
        params=[
            CommandParam("profile_name", ParamType.STRING, "Show specific profile (optional)",
                        default="")
        ],
        handler=lambda profile_name="": _list_profiles(app_state, profile_name)
    ))

    registry.register(CommandDef(
        name="profile",
        category=CommandCategory.SYSTEM,
        description_short="Use a recording profile",
        description_long="Load settings from a profile",
        params=[
            CommandParam("action", ParamType.STRING, "Action: use, save, or show",
                        completions=["use", "save", "show"]),
            CommandParam("name", ParamType.STRING, "Profile name")
        ],
        handler=lambda action, name: _profile_action(app_state, action, name)
    ))


# ========== HELPER FUNCTIONS ==========

def _get_devices_manager(app_state):
    """Get or create TetraDevices instance."""
    if not hasattr(app_state, '_tetra_devices'):
        from tau_lib.core.devices import TetraDevices
        # Use transport's tau socket if available
        socket_path = None
        if hasattr(app_state, 'transport') and hasattr(app_state.transport, '_tau'):
            tau = app_state.transport._tau
            if tau:
                socket_path = tau.socket_path
        app_state._tetra_devices = TetraDevices(socket_path)
    return app_state._tetra_devices


def _list_devices(app_state, device_type):
    """List available audio devices."""
    try:
        devices = _get_devices_manager(app_state)
        capture, playback = devices.list_devices()

        lines = []
        if device_type in ("all", "capture"):
            lines.append("CAPTURE DEVICES:")
            for dev in capture:
                lines.append(f"  {dev}")

        if device_type in ("all", "playback"):
            if lines:
                lines.append("")
            lines.append("PLAYBACK DEVICES:")
            for dev in playback:
                lines.append(f"  {dev}")

        return "\n".join(lines)
    except ConnectionError as e:
        return f"Error: {e}\nIs tau-engine running?"
    except Exception as e:
        return f"Error listing devices: {e}"


def _select_device(app_state, device_type, identifier):
    """Select a capture or playback device."""
    if device_type not in ("capture", "playback"):
        return "Error: type must be 'capture' or 'playback'"

    try:
        devices = _get_devices_manager(app_state)
        device = devices.select_device(identifier, device_type)

        if device:
            return f"Selected {device_type}: {device}\n(restart tau-engine to apply)"
        else:
            return f"Device not found: {identifier}"
    except ConnectionError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error selecting device: {e}"


def _show_aliases(app_state):
    """Show device aliases."""
    try:
        devices = _get_devices_manager(app_state)

        lines = ["CAPTURE ALIASES:"]
        for alias, pattern in devices.get_aliases("capture").items():
            lines.append(f"  {alias} → {pattern}")

        lines.append("\nPLAYBACK ALIASES:")
        for alias, pattern in devices.get_aliases("playback").items():
            lines.append(f"  {alias} → {pattern}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def _set_alias(app_state, name, pattern, device_type):
    """Set a device alias."""
    try:
        devices = _get_devices_manager(app_state)
        devices.set_alias(name, pattern, device_type)
        return f"Alias set: {name} → {pattern} ({device_type})"
    except Exception as e:
        return f"Error setting alias: {e}"


def _start_recording(app_state, path):
    """Start recording."""
    try:
        from tau_lib.data.recording_api import TauRecorder
        import time

        # Get or create recorder
        if not hasattr(app_state, '_recorder'):
            app_state._recorder = TauRecorder()

        recorder = app_state._recorder

        # Check if already recording
        status = recorder.get_status()
        if status.get('recording'):
            return "Already recording"

        # Generate path if not provided
        if not path:
            # Use context directory or default
            if hasattr(app_state, 'context_dir') and app_state.context_dir:
                base_dir = Path(app_state.context_dir) / "db"
            else:
                base_dir = Path.home() / "tau" / "recordings"

            base_dir.mkdir(parents=True, exist_ok=True)
            epoch = int(time.time())
            path = str(base_dir / f"{epoch}.audio.raw.wav")

        # Start recording
        recorder.start_recording(output_path=path)
        return f"Recording started: {path}"

    except Exception as e:
        return f"Error starting recording: {e}"


def _stop_recording(app_state):
    """Stop recording."""
    try:
        if not hasattr(app_state, '_recorder'):
            return "No recording active"

        recorder = app_state._recorder
        status = recorder.get_status()

        if not status.get('recording'):
            return "No recording active"

        metadata = recorder.stop_recording()
        duration = metadata.get('duration_sec', 0)
        path = metadata.get('output_path', '')

        return f"Recording stopped: {duration:.1f}s\nSaved: {path}"

    except Exception as e:
        return f"Error stopping recording: {e}"


def _recording_status(app_state):
    """Show recording status."""
    try:
        if not hasattr(app_state, '_recorder'):
            return "Recording: inactive"

        recorder = app_state._recorder
        status = recorder.get_status()

        if status.get('recording'):
            duration = status.get('duration_sec', 0)
            path = status.get('output_path', '')
            return f"Recording: active\nDuration: {duration:.1f}s\nOutput: {path}"
        else:
            return "Recording: inactive"

    except Exception as e:
        return f"Error: {e}"


def _list_apps(app_state, app_name):
    """List apps using tetra configuration."""
    try:
        devices = _get_devices_manager(app_state)

        if app_name:
            # Show specific app config
            config = devices.get_app_config(app_name)
            if not config:
                return f"App not found: {app_name}"

            lines = [f"APP: {app_name}"]
            for key, value in config.items():
                if isinstance(value, dict):
                    lines.append(f"\n[{key}]")
                    for k, v in value.items():
                        lines.append(f"  {k} = {v}")
                else:
                    lines.append(f"{key} = {value}")
            return "\n".join(lines)
        else:
            # List all apps
            apps = devices.list_apps()
            if not apps:
                return "No apps configured"

            lines = ["APPS WITH TETRA CONFIG:"]
            for app in apps:
                config = devices.get_app_config(app)
                desc = config.get('description', '') if config else ''
                lines.append(f"  {app}: {desc}")

            return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def _list_profiles(app_state, profile_name):
    """List recording profiles."""
    try:
        devices = _get_devices_manager(app_state)

        if profile_name:
            # Show specific profile
            config = devices.get_profile(profile_name)
            if not config:
                return f"Profile not found: {profile_name}"

            lines = [f"PROFILE: {profile_name}"]
            for key, value in config.items():
                if isinstance(value, dict):
                    lines.append(f"\n[{key}]")
                    for k, v in value.items():
                        lines.append(f"  {k} = {v}")
                else:
                    lines.append(f"{key} = {value}")
            return "\n".join(lines)
        else:
            # List all profiles
            profiles = devices.list_profiles()
            if not profiles:
                return "No profiles configured"

            lines = ["AVAILABLE PROFILES:"]
            for profile in profiles:
                config = devices.get_profile(profile)
                desc = config.get('description', '') if config else ''
                created_by = config.get('created_by', '') if config else ''
                lines.append(f"  {profile}: {desc}")
                if created_by:
                    lines.append(f"    (created by {created_by})")

            return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def _profile_action(app_state, action, name):
    """Handle profile actions: use, save, show."""
    try:
        devices = _get_devices_manager(app_state)

        if action == "show":
            return _list_profiles(app_state, name)

        elif action == "use":
            config = devices.get_profile(name)
            if not config:
                return f"Profile not found: {name}"

            # Apply recording settings from profile
            recording = config.get('recording', {})
            if 'capture_device' in recording:
                _select_device(app_state, 'capture', recording['capture_device'])

            # Save active profile to app config
            devices.set_app_config('tau', {'profiles': {'active': name}})

            return f"Profile loaded: {name}"

        elif action == "save":
            # Save current settings as profile
            config = {
                'description': f"Saved from tau",
                'recording': {
                    'capture_device': 'default',  # TODO: get current device
                    'sample_rate': 48000,
                    'channels': 2,
                }
            }
            devices.save_profile(name, config, created_by='tau')
            return f"Profile saved: {name}"

        else:
            return f"Unknown action: {action} (use: use, save, show)"

    except Exception as e:
        return f"Error: {e}"
