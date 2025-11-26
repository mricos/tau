"""
Zoom command definitions (part of TRANSPORT category).
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_zoom_commands(app_state):
    """Register zoom commands (grouped under TRANSPORT)."""

    # ========== ZOOM COMMANDS (TRANSPORT) ==========

    registry.register(CommandDef(
        name="zoom",
        category=CommandCategory.TRANSPORT,
        description_short="Set zoom span (time window width)",
        params=[
            CommandParam("span", ParamType.FLOAT, "Span in seconds", min_val=0.01)
        ],
        handler=lambda span: app_state.transport.zoom(span)
    ))

    registry.register(CommandDef(
        name="zoom_in",
        category=CommandCategory.TRANSPORT,
        description_short="Zoom in (decrease span)",
        aliases=["zi"],
        key_binding="<",
        handler=lambda: app_state.transport.zoom_in()
    ))

    registry.register(CommandDef(
        name="zoom_out",
        category=CommandCategory.TRANSPORT,
        description_short="Zoom out (increase span)",
        aliases=["zo"],
        key_binding=">",
        handler=lambda: app_state.transport.zoom_out()
    ))

