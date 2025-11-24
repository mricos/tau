"""
Events Lane command definitions.
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_events_lane_commands(app_state):
    """Register events lane commands."""

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

