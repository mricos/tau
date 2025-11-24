"""
Utility command definitions.
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_utility_commands(app_state):
    """Register utility commands."""

    # ========== UTILITY COMMANDS ==========

    registry.register(CommandDef(
        name="help",
        category=CommandCategory.UTILITY,
        description_short="Show help for commands",
        aliases=["h", "?"],
        params=[
            CommandParam("command", ParamType.STRING, "Command name (optional)", default=""),
            CommandParam("show_osc", ParamType.BOOL, "Show OSC addresses", default=True)
        ],
        key_binding="?",
        handler=lambda command="", show_osc=True: _show_help(app_state, command if command else None, show_osc)
    ))

    registry.register(CommandDef(
        name="quickstart",
        category=CommandCategory.UTILITY,
        description_short="Interactive quickstart guide for new users",
        aliases=["quick", "intro", "tutorial"],
        handler=lambda: _show_quickstart(app_state)
    ))

    registry.register(CommandDef(
        name="list_commands",
        category=CommandCategory.UTILITY,
        description_short="List all available commands",
        aliases=["lc", "commands"],
        handler=lambda: _list_commands(app_state)
    ))

    registry.register(CommandDef(
        name="clear",
        category=CommandCategory.UTILITY,
        description_short="Clear CLI output history",
        handler=lambda: None  # Handled by CLI manager
    ))

    registry.register(CommandDef(
        name="quit",
        category=CommandCategory.UTILITY,
        description_short="Quit application",
        aliases=["q", "exit"],
        key_binding="q",
        handler=lambda: None  # Handled by main loop
    ))

