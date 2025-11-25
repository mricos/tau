#!/usr/bin/env python3
"""
Unit tests for completion system.

Tests:
- CompletionState class
- completion.py functions
- Hierarchical category navigation
"""

import sys
import pytest
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from repl_py.cli.manager import CompletionState, CLIManager


class TestCompletionState:
    """Tests for the CompletionState dataclass."""

    def test_initial_state(self):
        """Test default initialization."""
        cs = CompletionState()
        assert cs.items == []
        assert cs.visible == False
        assert cs.selected_index == 0
        assert cs.current_category is None
        assert cs.provider is None

    def test_hide_resets_state(self):
        """Test that hide() resets all state."""
        cs = CompletionState()
        cs.items = [MockItem("test")]
        cs.visible = True
        cs.selected_index = 5
        cs.current_category = "Transport"

        cs.hide()

        assert cs.items == []
        assert cs.visible == False
        assert cs.selected_index == 0
        assert cs.current_category is None

    def test_select_next_wraps(self):
        """Test that selection wraps around."""
        cs = CompletionState()
        cs.items = [MockItem("a"), MockItem("b"), MockItem("c")]
        cs.selected_index = 2

        cs.select_next()
        assert cs.selected_index == 0  # Wrapped

    def test_select_prev_wraps(self):
        """Test that selection wraps backwards."""
        cs = CompletionState()
        cs.items = [MockItem("a"), MockItem("b"), MockItem("c")]
        cs.selected_index = 0

        cs.select_prev()
        assert cs.selected_index == 2  # Wrapped to end

    def test_select_with_empty_items(self):
        """Test selection on empty list is safe."""
        cs = CompletionState()
        cs.select_next()  # Should not raise
        cs.select_prev()  # Should not raise
        assert cs.selected_index == 0

    def test_get_selected_with_items(self):
        """Test getting selected item."""
        cs = CompletionState()
        items = [MockItem("a"), MockItem("b")]
        cs.items = items
        cs.selected_index = 1

        assert cs.get_selected() == items[1]

    def test_get_selected_empty_returns_none(self):
        """Test get_selected with no items."""
        cs = CompletionState()
        assert cs.get_selected() is None

    def test_drill_into_category(self):
        """Test drilling into a category item."""
        cs = CompletionState()
        cs.items = [MockItem("Transport", type="category")]
        cs.selected_index = 0

        result = cs.drill_into()

        assert result == True
        assert cs.current_category == "Transport"
        assert cs.selected_index == 0

    def test_drill_into_command_returns_false(self):
        """Test that drilling into a command returns False."""
        cs = CompletionState()
        cs.items = [MockItem("play", type="command")]
        cs.selected_index = 0

        result = cs.drill_into()

        assert result == False
        assert cs.current_category is None

    def test_drill_out_from_category(self):
        """Test going back from category."""
        cs = CompletionState()
        cs.current_category = "Transport"

        result = cs.drill_out()

        assert result == True
        assert cs.current_category is None

    def test_drill_out_from_root_returns_false(self):
        """Test drill_out at root level."""
        cs = CompletionState()
        result = cs.drill_out()
        assert result == False

    def test_update_with_provider(self):
        """Test update calls provider correctly."""
        cs = CompletionState()
        calls = []

        def mock_provider(buffer, category):
            calls.append((buffer, category))
            return [MockItem("result")]

        cs.provider = mock_provider
        cs.current_category = "TestCat"

        cs.update("test")

        assert len(calls) == 1
        assert calls[0] == ("test", "TestCat")
        assert len(cs.items) == 1
        assert cs.visible == True

    def test_update_shows_popup_with_results(self):
        """Test popup becomes visible with results."""
        cs = CompletionState()
        cs.provider = lambda b, c: [MockItem("a"), MockItem("b")]

        cs.update("test")

        assert cs.visible == True
        assert len(cs.items) == 2

    def test_update_hides_popup_with_no_results(self):
        """Test popup hidden when no results."""
        cs = CompletionState()
        cs.provider = lambda b, c: []
        cs.visible = True

        cs.update("test")

        assert cs.visible == False

    def test_update_resets_selection_if_out_of_bounds(self):
        """Test selection reset when items change."""
        cs = CompletionState()
        cs.provider = lambda b, c: [MockItem("only_one")]
        cs.selected_index = 5

        cs.update("test")

        assert cs.selected_index == 0


class TestCLIManagerCompletion:
    """Tests for CLIManager completion integration."""

    def test_completion_property_accessors(self):
        """Test that property accessors work."""
        cli = CLIManager()
        cli._completion.items = [MockItem("test")]
        cli._completion.visible = True
        cli._completion.selected_index = 0
        cli._completion.current_category = "Test"

        assert cli.completion_items == [cli._completion.items[0]]
        assert cli.completions_visible == True
        assert cli.selected_index == 0
        assert cli.current_category == "Test"

    def test_set_completion_provider(self):
        """Test setting completion provider."""
        cli = CLIManager()
        provider = lambda b, c: []

        cli.set_completion_rich_provider(provider)

        assert cli._completion.provider == provider

    def test_update_completions_rich_uses_buffer(self):
        """Test update uses input buffer up to cursor."""
        cli = CLIManager()
        calls = []

        def mock_provider(buffer, category):
            calls.append(buffer)
            return []

        cli._completion.provider = mock_provider
        cli.input_buffer = "hello world"
        cli.cursor_pos = 5  # At "hello"

        cli.update_completions_rich()

        assert calls == ["hello"]

    def test_accept_completion_replaces_command(self):
        """Test accepting completion replaces command name."""
        cli = CLIManager()
        cli._completion.items = [MockItem("play")]
        cli._completion.selected_index = 0
        cli.input_buffer = "pl"
        cli.cursor_pos = 2

        cli.accept_completion()

        assert cli.input_buffer == "play "
        assert cli.cursor_pos == 5

    def test_accept_completion_replaces_argument(self):
        """Test accepting completion replaces argument."""
        cli = CLIManager()
        cli._completion.items = [MockItem("filename.wav")]
        cli._completion.selected_index = 0
        cli.input_buffer = "load file"
        cli.cursor_pos = 9

        cli.accept_completion()

        assert cli.input_buffer == "load filename.wav "
        assert cli.cursor_pos == len("load filename.wav ")

    def test_hide_completions_delegates(self):
        """Test hide_completions delegates to CompletionState."""
        cli = CLIManager()
        cli._completion.visible = True
        cli._completion.items = [MockItem("test")]

        cli.hide_completions()

        assert cli._completion.visible == False
        assert cli._completion.items == []


class MockItem:
    """Mock completion item for testing."""

    def __init__(self, text, type="command"):
        self.text = text
        self.type = type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
