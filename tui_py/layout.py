"""
Layout calculation for tau TUI.

Centralizes all layout calculations for the terminal interface.
Uses LayoutConfig from state for configurable parameters.
"""

from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tau_lib.core.state import LayoutConfig, AppState


@dataclass
class LayoutMetrics:
    """Computed layout metrics for a single frame."""

    # Terminal dimensions
    term_height: int
    term_width: int

    # Vertical positions (y coordinates)
    header_y: int = 0
    data_lanes_y: int = 0
    cli_output_y: int = 0
    cli_prompt_y: int = 0
    special_lanes_y: int = 0
    status_line_y: int = 0

    # Heights
    header_height: int = 0
    data_viewport_height: int = 0
    cli_output_height: int = 0
    special_lanes_height: int = 0

    # State flags
    terminal_too_small: bool = False


def compute_layout(
    term_height: int,
    term_width: int,
    config: 'LayoutConfig',
    events_lane_height: int = 0,
    logs_lane_height: int = 0,
    completion_item_count: int = 0,
    completions_visible: bool = False,
    cli_output_line_count: int = 0,
) -> LayoutMetrics:
    """
    Compute layout metrics for the current terminal size and state.

    Args:
        term_height: Terminal height in rows
        term_width: Terminal width in columns
        config: Layout configuration
        events_lane_height: Height of events lane (0 if hidden)
        logs_lane_height: Height of logs lane (0 if hidden)
        completion_item_count: Number of completion items
        completions_visible: Whether completion popup is shown
        cli_output_line_count: Number of CLI output lines

    Returns:
        LayoutMetrics with computed positions and heights
    """
    metrics = LayoutMetrics(term_height=term_height, term_width=term_width)

    # Check minimum terminal size
    if term_width < config.min_terminal_width or term_height < config.min_terminal_height:
        metrics.terminal_too_small = True
        return metrics

    # Fixed layout elements
    metrics.header_height = config.header_height
    metrics.header_y = 0

    # Special lanes (events + logs)
    metrics.special_lanes_height = events_lane_height + logs_lane_height

    # Status line is always at bottom
    metrics.status_line_y = term_height - 1

    # Calculate available space for data lanes and CLI output
    fixed_height = (
        config.header_height +
        config.cli_prompt_height +
        metrics.special_lanes_height +
        config.cli_status_height
    )
    available_for_data_and_cli = term_height - fixed_height

    # Calculate CLI output height
    if completions_visible:
        # Completion popup sizing
        num_items = min(completion_item_count, config.completion_max_items)
        # header (1) + items + blank (1) + preview
        metrics.cli_output_height = 1 + num_items + 1 + config.completion_preview_height
    else:
        # Normal CLI output - dynamic sizing
        max_cli_for_screen = max(
            config.cli_output_min_height,
            available_for_data_and_cli - config.min_data_viewport
        )
        desired_cli_height = min(cli_output_line_count, config.cli_output_max_height)
        metrics.cli_output_height = min(desired_cli_height, max_cli_for_screen)

    # Data viewport uses remaining space
    metrics.data_viewport_height = max(
        config.min_data_viewport,
        available_for_data_and_cli - metrics.cli_output_height
    )

    # Calculate y positions
    metrics.data_lanes_y = metrics.header_y + metrics.header_height
    metrics.cli_output_y = metrics.data_lanes_y + metrics.data_viewport_height

    # CLI prompt positioned above status with offset for feedback area
    metrics.cli_prompt_y = (
        metrics.status_line_y -
        metrics.special_lanes_height -
        config.cli_prompt_offset
    )

    # Special lanes between prompt and status
    metrics.special_lanes_y = metrics.status_line_y - metrics.special_lanes_height

    return metrics


def get_special_lanes_info(state: 'AppState') -> tuple[int, int]:
    """
    Get heights of special lanes (events and logs).

    Args:
        state: Application state

    Returns:
        Tuple of (events_height, logs_height)
    """
    events_lane = state.lanes.get_lane(9)
    logs_lane = state.lanes.get_lane(0)

    events_height = 0
    logs_height = 0

    if events_lane and events_lane.is_visible():
        events_height = events_lane.get_height()

    if logs_lane and logs_lane.is_visible():
        logs_height = logs_lane.get_height()

    return events_height, logs_height


def get_max_special_lanes_height(state: 'AppState') -> int:
    """
    Get maximum possible height for special lanes area (for clearing).

    Args:
        state: Application state

    Returns:
        Maximum combined height of events + logs lanes
    """
    events_lane = state.lanes.get_lane(9)
    logs_lane = state.lanes.get_lane(0)

    max_height = 0
    if events_lane:
        max_height += events_lane.HEIGHT_SPECIAL
    if logs_lane:
        max_height += logs_lane.HEIGHT_SPECIAL

    return max_height
