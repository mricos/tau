"""
Lane command definitions.
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_lane_commands(app_state):
    """Register lane commands."""

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

