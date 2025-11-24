"""
Config command definitions.
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_config_commands(app_state):
    """Register config commands."""

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

