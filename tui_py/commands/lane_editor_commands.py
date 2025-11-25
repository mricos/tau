"""
Lane Editor command definitions.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_lane_editor_commands(app_state):
    """Register lane editor commands."""

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

