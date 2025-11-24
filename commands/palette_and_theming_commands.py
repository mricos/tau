"""
Palette And Theming command definitions.
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_palette_and_theming_commands(app_state):
    """Register palette and theming commands."""

    # ========== PALETTE AND THEMING COMMANDS ==========

    registry.register(CommandDef(
        name="palette",
        category=CommandCategory.UTILITY,
        description_short="Show color palette inspector",
        aliases=["colors"],
        handler=lambda: _show_palette(app_state)
    ))

    registry.register(CommandDef(
        name="theme",
        category=CommandCategory.UTILITY,
        description_short="Load TDS theme file",
        params=[
            CommandParam("theme_name", ParamType.STRING, "Theme name (e.g., 'warm')")
        ],
        handler=lambda theme_name: _load_theme(app_state, theme_name)
    ))

