"""
Marker command definitions.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_marker_commands(app_state):
    """Register marker commands."""

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

