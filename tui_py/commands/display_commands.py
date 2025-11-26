"""
Display command definitions (part of VIEW category).
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_display_commands(app_state):
    """Register display commands (grouped under VIEW)."""

    # ========== DISPLAY COMMANDS (VIEW) ==========

    registry.register(CommandDef(
        name="envelope",
        category=CommandCategory.VIEW,
        description_short="Set envelope rendering mode",
        description_long="Show waveforms as min/max envelope bars",
        handler=lambda: setattr(app_state.display, 'mode', 'envelope')
    ))

    registry.register(CommandDef(
        name="points",
        category=CommandCategory.VIEW,
        description_short="Set points rendering mode",
        description_long="Show waveforms as interpolated points",
        handler=lambda: setattr(app_state.display, 'mode', 'points')
    ))

    registry.register(CommandDef(
        name="toggle_mode",
        category=CommandCategory.VIEW,
        description_short="Toggle between envelope and points mode",
        aliases=["tm"],
        key_binding="o",
        handler=lambda: app_state.display.toggle_mode()
    ))

