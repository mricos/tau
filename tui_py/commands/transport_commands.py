"""
Transport command definitions.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_transport_commands(app_state):
    """Register transport commands."""

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
        description_short="Jump to start of timeline",
        aliases=["start", "rewind", "rw"],
        key_binding="Home",
        handler=lambda: app_state.transport.home()
    ))

    registry.register(CommandDef(
        name="end",
        category=CommandCategory.TRANSPORT,
        description_short="Jump to end of timeline",
        aliases=["finish", "ff"],
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

