"""
Command definitions package.
"""

from .transport_commands import register_transport_commands
from .audio_commands import register_audio_commands
from .zoom_commands import register_zoom_commands
from .parameter_commands import register_parameter_commands
from .lane_commands import register_lane_commands
from .marker_commands import register_marker_commands
from .display_commands import register_display_commands
from .config_commands import register_config_commands
from .events_lane_commands import register_events_lane_commands
from .utility_commands import register_utility_commands
from .trs_project_commands import register_trs_project_commands
from .palette_and_theming_commands import register_palette_and_theming_commands
from .lane_editor_commands import register_lane_editor_commands
from .semantic_name_mapping_commands import register_semantic_name_mapping_commands


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


__all__ = ['register_all_commands']
