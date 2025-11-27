"""
Display command definitions (part of VIEW category).
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_display_commands(app_state):
    """Register display commands (grouped under VIEW)."""

    # ========== CLI HEIGHT COMMAND ==========

    def show_cli_settings():
        """Show current CLI layout settings."""
        lc = app_state.layout
        lines = [
            f"CLI Settings:",
            f"  float: {lc.cli_float} (up=CLI hugs lanes, down=CLI hugs bottom)",
            f"  height: {lc.cli_output_min_height}-{lc.cli_output_max_height} lines",
            f"  completions: {lc.cli_completions} (above/below prompt)",
        ]
        return "\n".join(lines)

    registry.register(CommandDef(
        name="cli",
        category=CommandCategory.VIEW,
        description_short="Show CLI layout settings",
        description_long="Display current CLI float, height, and completions settings",
        handler=show_cli_settings
    ))

    def set_cli_height(max_height: int, min_height: int = 1):
        """Set CLI output area height limits."""
        if max_height < 1:
            return "✗ max must be >= 1"
        if min_height < 1:
            return "✗ min must be >= 1"
        if min_height > max_height:
            return f"✗ min ({min_height}) cannot exceed max ({max_height})"

        app_state.layout.cli_output_max_height = max_height
        app_state.layout.cli_output_min_height = min_height
        return f"✓ CLI height: {min_height}-{max_height} lines"

    registry.register(CommandDef(
        name="cli-height",
        category=CommandCategory.VIEW,
        description_short="Set CLI output height limits",
        description_long="Set max and optional min height for CLI output area below prompt",
        params=[
            CommandParam("max", ParamType.INT, "Maximum lines (1-50)"),
            CommandParam("min", ParamType.INT, "Minimum lines (default 1)", default=1),
        ],
        handler=set_cli_height
    ))

    def set_cli_float(direction: str):
        """Set CLI float direction."""
        direction = direction.lower()
        if direction not in ("up", "down"):
            return f"✗ Invalid direction '{direction}'. Use 'up' or 'down'"
        app_state.layout.cli_float = direction
        if direction == "up":
            return "✓ CLI floats up (hugs data lanes)"
        else:
            return "✓ CLI floats down (hugs bottom, above logs)"

    registry.register(CommandDef(
        name="cli-float",
        category=CommandCategory.VIEW,
        description_short="Set CLI float direction",
        description_long="up = CLI area hugs data lanes, down = CLI area hugs bottom",
        params=[
            CommandParam("direction", ParamType.STRING, "up or down", enum_values=["up", "down"]),
        ],
        handler=set_cli_float
    ))

    def set_cli_completions(position: str):
        """Set completions popup position."""
        position = position.lower()
        if position not in ("above", "below"):
            return f"✗ Invalid position '{position}'. Use 'above' or 'below'"
        app_state.layout.cli_completions = position
        if position == "above":
            return "✓ Completions appear above prompt"
        else:
            return "✓ Completions appear below prompt (overlay)"

    registry.register(CommandDef(
        name="cli-completions",
        category=CommandCategory.VIEW,
        description_short="Set completions popup position",
        description_long="above = overlay on data lanes, below = overlay to bottom of screen",
        params=[
            CommandParam("position", ParamType.STRING, "above or below", enum_values=["above", "below"]),
        ],
        handler=set_cli_completions
    ))

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

    # ========== TIPS COMMAND ==========

    def show_tips():
        """Show startup tips screen."""
        app_state.features.show_tips_requested = True
        return "✓ Opening tips..."

    registry.register(CommandDef(
        name="tips",
        category=CommandCategory.VIEW,
        description_short="Show startup tips",
        description_long="Display the 'Did You Know?' tips screen with keyboard shortcuts and features",
        handler=show_tips
    ))

