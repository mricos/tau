"""
Command definitions package.
"""

from tui_py.commands.transport_commands import register_transport_commands
from tui_py.commands.audio_commands import register_audio_commands
from tui_py.commands.zoom_commands import register_zoom_commands
from tui_py.commands.parameter_commands import register_parameter_commands
from tui_py.commands.lane_commands import register_lane_commands
from tui_py.commands.marker_commands import register_marker_commands
from tui_py.commands.display_commands import register_display_commands
from tui_py.commands.config_commands import register_config_commands
from tui_py.commands.events_lane_commands import register_events_lane_commands
from tui_py.commands.utility_commands import register_utility_commands
from tui_py.commands.trs_project_commands import register_trs_project_commands
from tui_py.commands.palette_and_theming_commands import register_palette_and_theming_commands
from tui_py.commands.lane_editor_commands import register_lane_editor_commands
from tui_py.commands.semantic_name_mapping_commands import register_semantic_name_mapping_commands
from tui_py.commands.video_commands import register_video_commands as register_video_display_commands
from tui_py.commands.recording_commands import register_recording_commands
from tui_py.commands.osc_commands import register_osc_commands


def register_all_commands(app_state):
    """
    Register all SNN commands with the global registry.

    Args:
        app_state: Application state object
    """
    register_transport_commands(app_state)
    register_audio_commands(app_state)
    register_zoom_commands(app_state)
    register_parameter_commands(app_state)
    register_lane_commands(app_state)
    register_marker_commands(app_state)
    register_display_commands(app_state)
    register_config_commands(app_state)
    register_events_lane_commands(app_state)
    register_utility_commands(app_state)
    register_trs_project_commands(app_state)
    register_palette_and_theming_commands(app_state)
    register_lane_editor_commands(app_state)
    register_semantic_name_mapping_commands(app_state)
    register_video_display_commands(app_state)
    register_recording_commands(app_state)
    register_osc_commands(app_state)


__all__ = ['register_all_commands']
