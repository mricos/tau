"""
Trs Project command definitions.
"""

from ..core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


def register_trs_project_commands(app_state):
    """Register trs project commands."""

    # ========== TRS/PROJECT COMMANDS ==========

    registry.register(CommandDef(
        name="load",
        category=CommandCategory.UTILITY,
        description_short="Load audio file (auto-runs tscale)",
        params=[
            CommandParam("audio_file", ParamType.STRING, "Audio file path (relative to CWD)")
        ],
        handler=lambda audio_file: _load_audio(app_state, audio_file)
    ))

    registry.register(CommandDef(
        name="reload",
        category=CommandCategory.UTILITY,
        description_short="Reload current audio with updated kernel params",
        handler=lambda: _reload_audio(app_state)
    ))

    registry.register(CommandDef(
        name="cwd",
        category=CommandCategory.UTILITY,
        description_short="Get or set current working directory",
        params=[
            CommandParam("path", ParamType.STRING, "New working directory path", default=None)
        ],
        handler=lambda path=None: _cwd_command(app_state, path)
    ))

    registry.register(CommandDef(
        name="session",
        category=CommandCategory.UTILITY,
        description_short="Show current session info",
        handler=lambda: _show_session(app_state)
    ))

    registry.register(CommandDef(
        name="project",
        category=CommandCategory.UTILITY,
        description_short="Show project info",
        handler=lambda: _show_project(app_state)
    ))

    registry.register(CommandDef(
        name="data",
        category=CommandCategory.UTILITY,
        description_short="List data files in db/",
        params=[
            CommandParam("action", ParamType.ENUM, "Action to perform",
                        enum_values=["list", "latest"],
                        default="list")
        ],
        handler=lambda action="list": _data_command(app_state, action)
    ))

