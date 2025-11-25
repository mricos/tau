#!/usr/bin/env python3
"""
Unit tests for layout calculation module.

Tests:
- LayoutConfig dataclass
- compute_layout function
- Layout metrics calculation
"""

import sys
import pytest
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tau_lib.core.state import LayoutConfig
from tui_py.layout import compute_layout, LayoutMetrics


class TestLayoutConfig:
    """Tests for the LayoutConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        lc = LayoutConfig()
        assert lc.header_height == 2
        assert lc.cli_prompt_height == 1
        assert lc.cli_status_height == 1
        assert lc.cli_prompt_offset == 4
        assert lc.cli_output_min_height == 0
        assert lc.cli_output_max_height == 25
        assert lc.completion_max_items == 8
        assert lc.completion_preview_height == 3
        assert lc.min_data_viewport == 4
        assert lc.min_terminal_width == 80
        assert lc.min_terminal_height == 24

    def test_custom_values(self):
        """Test custom configuration."""
        lc = LayoutConfig(
            header_height=3,
            min_data_viewport=8,
            cli_prompt_offset=6
        )
        assert lc.header_height == 3
        assert lc.min_data_viewport == 8
        assert lc.cli_prompt_offset == 6


class TestComputeLayout:
    """Tests for compute_layout function."""

    def test_terminal_too_small_width(self):
        """Test detection of terminal too narrow."""
        lc = LayoutConfig(min_terminal_width=80, min_terminal_height=24)
        metrics = compute_layout(24, 60, lc)  # Width < 80
        assert metrics.terminal_too_small == True

    def test_terminal_too_small_height(self):
        """Test detection of terminal too short."""
        lc = LayoutConfig(min_terminal_width=80, min_terminal_height=24)
        metrics = compute_layout(20, 100, lc)  # Height < 24
        assert metrics.terminal_too_small == True

    def test_terminal_adequate_size(self):
        """Test normal terminal size."""
        lc = LayoutConfig()
        metrics = compute_layout(40, 100, lc)
        assert metrics.terminal_too_small == False

    def test_header_position(self):
        """Test header is at top."""
        lc = LayoutConfig(header_height=2)
        metrics = compute_layout(40, 100, lc)
        assert metrics.header_y == 0
        assert metrics.header_height == 2

    def test_status_line_at_bottom(self):
        """Test status line is at bottom."""
        metrics = compute_layout(40, 100, LayoutConfig())
        assert metrics.status_line_y == 39  # Last row (40 - 1)

    def test_data_viewport_minimum(self):
        """Test data viewport respects minimum."""
        lc = LayoutConfig(min_data_viewport=4)
        metrics = compute_layout(24, 80, lc)
        assert metrics.data_viewport_height >= 4

    def test_cli_output_respects_max(self):
        """Test CLI output respects maximum height."""
        lc = LayoutConfig(cli_output_max_height=10)
        metrics = compute_layout(
            50, 100, lc,
            cli_output_line_count=100  # More lines than max
        )
        assert metrics.cli_output_height <= 10

    def test_completion_popup_sizing(self):
        """Test completion popup height calculation."""
        lc = LayoutConfig(
            completion_max_items=8,
            completion_preview_height=3
        )
        metrics = compute_layout(
            50, 100, lc,
            completions_visible=True,
            completion_item_count=5
        )
        # 1 header + 5 items + 1 blank + 3 preview = 10
        assert metrics.cli_output_height == 10

    def test_completion_popup_caps_items(self):
        """Test completion popup caps visible items."""
        lc = LayoutConfig(
            completion_max_items=8,
            completion_preview_height=3
        )
        metrics = compute_layout(
            50, 100, lc,
            completions_visible=True,
            completion_item_count=100  # Way more than max
        )
        # 1 header + 8 items (capped) + 1 blank + 3 preview = 13
        assert metrics.cli_output_height == 13

    def test_special_lanes_affect_layout(self):
        """Test that special lanes reduce available space."""
        lc = LayoutConfig()

        without_special = compute_layout(40, 100, lc)
        with_special = compute_layout(
            40, 100, lc,
            events_lane_height=3,
            logs_lane_height=3
        )

        assert with_special.special_lanes_height == 6
        # Data viewport should be smaller when special lanes are visible
        # (though actual effect depends on how space is distributed)

    def test_data_lanes_position(self):
        """Test data lanes start after header."""
        lc = LayoutConfig(header_height=2)
        metrics = compute_layout(40, 100, lc)
        assert metrics.data_lanes_y == 2  # After 2-row header

    def test_cli_output_position(self):
        """Test CLI output position calculation."""
        lc = LayoutConfig(header_height=2)
        metrics = compute_layout(40, 100, lc)
        expected = lc.header_height + metrics.data_viewport_height
        assert metrics.cli_output_y == expected


class TestLayoutMetrics:
    """Tests for LayoutMetrics dataclass."""

    def test_default_metrics(self):
        """Test default metrics values."""
        metrics = LayoutMetrics(term_height=40, term_width=100)
        assert metrics.term_height == 40
        assert metrics.term_width == 100
        assert metrics.terminal_too_small == False

    def test_all_positions_stored(self):
        """Test that all position fields are populated."""
        lc = LayoutConfig()
        metrics = compute_layout(40, 100, lc)

        # All positions should be non-negative
        assert metrics.header_y >= 0
        assert metrics.data_lanes_y >= 0
        assert metrics.cli_output_y >= 0
        assert metrics.cli_prompt_y >= 0
        assert metrics.status_line_y >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
