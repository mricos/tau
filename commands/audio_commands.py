"""
Audio playback command definitions (Tau engine integration).
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_audio_commands(app_state):
    """Register audio playback commands."""

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


# Helper functions
def _load_audio_to_lane(app_state, lane_id, audio_path):
    """Load audio file to specified lane."""
    # Implementation handled by app_state
    if hasattr(app_state, 'load_audio_to_lane'):
        app_state.load_audio_to_lane(lane_id, audio_path)


def _unload_audio_from_lane(app_state, lane_id):
    """Unload audio from specified lane."""
    if hasattr(app_state, 'unload_audio_from_lane'):
        app_state.unload_audio_from_lane(lane_id)


def _set_audio_gain(app_state, lane_id, gain):
    """Set audio gain for specified lane."""
    if hasattr(app_state, 'set_audio_gain'):
        app_state.set_audio_gain(lane_id, gain)


def _show_tau_status(app_state):
    """Show tau engine status."""
    if hasattr(app_state, 'show_tau_status'):
        app_state.show_tau_status()
