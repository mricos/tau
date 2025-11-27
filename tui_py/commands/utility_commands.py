"""
Utility command definitions.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)
from tau_lib.core.aliases import get_alias_manager


def _show_help(app_state, command=None, show_osc=True):
    """Show help for a specific command or list all commands."""
    if command:
        # Show help for specific command
        cmd_def = registry.get(command)
        if not cmd_def:
            return f"Unknown command: {command}"

        lines = [f"=== {cmd_def.name} ==="]
        lines.append(cmd_def.description_short)
        if cmd_def.description_long:
            lines.append(cmd_def.description_long)

        if cmd_def.aliases:
            lines.append(f"Aliases: {', '.join(cmd_def.aliases)}")

        if cmd_def.params:
            lines.append("Parameters:")
            for p in cmd_def.params:
                req = "" if p.default is None else f" (default: {p.default})"
                lines.append(f"  {p.name}: {p.description}{req}")

        if cmd_def.key_binding:
            lines.append(f"Key binding: {cmd_def.key_binding}")

        return "\n".join(lines)
    else:
        # Show command categories overview
        return _list_commands(app_state)


def _list_commands(app_state):
    """List all available commands grouped by category."""
    commands = registry.list_all()

    # Group by category
    by_category = {}
    for cmd in commands:
        cat = cmd.category.value if cmd.category else "other"
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(cmd)

    lines = ["Commands by category:"]
    for cat in sorted(by_category.keys()):
        cmds = by_category[cat]
        cmd_names = [c.name for c in cmds[:5]]
        more = f" +{len(cmds)-5}" if len(cmds) > 5 else ""
        lines.append(f"  {cat}: {', '.join(cmd_names)}{more}")

    lines.append("Type 'help <command>' for details")
    return "\n".join(lines)


def _show_quickstart(app_state):
    """Show quickstart guide."""
    return """=== tau Quickstart ===

Navigation:
  Arrow keys: scrub audio (←/→) or scroll lanes (↑/↓)
  < >: zoom in/out
  Double-space: play/pause

Input:
  Just type to enter commands
  Tab: show completions
  Enter: execute command

Lanes:
  0-9: toggle lane visibility
  Shift+0-9: cycle display mode

Try these commands:
  status    - show current state
  ls        - list files
  help <cmd> - get command help
"""


def register_utility_commands(app_state):
    """Register utility commands."""

    # ========== UTILITY COMMANDS ==========

    registry.register(CommandDef(
        name="help",
        category=CommandCategory.SYSTEM,
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
        category=CommandCategory.SYSTEM,
        description_short="Interactive quickstart guide for new users",
        aliases=["quick", "intro", "tutorial"],
        handler=lambda: _show_quickstart(app_state)
    ))

    registry.register(CommandDef(
        name="list_commands",
        category=CommandCategory.SYSTEM,
        description_short="List all available commands",
        aliases=["lc", "commands"],
        handler=lambda: _list_commands(app_state)
    ))

    registry.register(CommandDef(
        name="clear",
        category=CommandCategory.SYSTEM,
        description_short="Clear CLI output history",
        handler=lambda: None  # Handled by CLI manager
    ))

    registry.register(CommandDef(
        name="quit",
        category=CommandCategory.SYSTEM,
        description_short="Quit application",
        aliases=["q", "exit"],
        key_binding="q",
        handler=lambda: None  # Handled by main loop
    ))

    # Alias commands
    registry.register(CommandDef(
        name="alias",
        category=CommandCategory.SYSTEM,
        description_short="Set or view a command alias",
        description_long="Create user-defined aliases stored in ~/.config/tau/aliases.toml",
        params=[
            CommandParam("name", ParamType.STRING, "Alias name", default=""),
            CommandParam("command", ParamType.STRING, "Command to alias", default=""),
        ],
        handler=lambda name="", command="": (
            get_alias_manager().format_list() if not name
            else get_alias_manager().set(name, command) if command
            else f"{name} = {get_alias_manager().get(name)}" if get_alias_manager().get(name)
            else f"No alias: {name}"
        )
    ))

    registry.register(CommandDef(
        name="unalias",
        category=CommandCategory.SYSTEM,
        description_short="Remove a command alias",
        params=[
            CommandParam("name", ParamType.STRING, "Alias to remove"),
        ],
        handler=lambda name: get_alias_manager().remove(name)
    ))

    registry.register(CommandDef(
        name="aliases",
        category=CommandCategory.SYSTEM,
        description_short="List all user aliases",
        handler=lambda: get_alias_manager().format_list()
    ))

