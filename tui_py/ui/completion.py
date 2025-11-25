"""
Tab completion system for ASCII Scope SNN.

Provides rich completion items with descriptions, categories, and preview help.
"""

from dataclasses import dataclass
from typing import List, Optional
from tau_lib.core.commands_api import COMMAND_REGISTRY, CommandCategory


@dataclass
class CompletionItem:
    """Rich completion item with metadata for display."""
    text: str                    # Completion text to insert
    description: str             # Short description (40 chars max)
    category: str                # Command category name
    color: int                   # Color pair index for display
    full_help: List[str]        # Full help text for preview pane
    type: str = "command"       # "command", "argument", "path"


def get_completions_rich(buffer: str) -> List[CompletionItem]:
    """
    Get rich completion items for current buffer.

    Args:
        buffer: Current input buffer before cursor

    Returns:
        List of CompletionItem objects with full metadata
    """
    parts = buffer.split()

    if not parts or (len(parts) == 1 and not buffer.endswith(' ')):
        # Completing command name
        prefix = parts[0] if parts else ""
        return _get_command_completions(prefix)
    else:
        # Completing command argument
        cmd_name = parts[0]
        cmd_def = COMMAND_REGISTRY.get(cmd_name)

        if not cmd_def:
            return []

        # Determine which argument we're completing
        arg_index = len(parts) - 1 if not buffer.endswith(' ') else len(parts)
        partial = parts[-1] if parts and not buffer.endswith(' ') else ""

        # Get argument completions from command
        arg_completions = cmd_def.get_completions(arg_index - 1, partial)

        # Convert to CompletionItem objects
        items = []
        for arg_text in arg_completions:
            # Get parameter info if available
            if arg_index - 1 < len(cmd_def.params):
                param = cmd_def.params[arg_index - 1]
                desc = param.description[:40]
                full_help = [
                    f"{cmd_def.name} → {param.name}",
                    "",
                    param.description,
                ]
            else:
                desc = "Argument value"
                full_help = [f"{cmd_def.name} argument"]

            items.append(CompletionItem(
                text=arg_text,
                description=desc,
                category=cmd_def.category.category_name,
                color=cmd_def.category.color,
                full_help=full_help,
                type="argument"
            ))

        return items


def _get_command_completions(prefix: str) -> List[CompletionItem]:
    """Get command name completions with rich metadata."""
    items = []

    # Get matching command names from registry
    cmd_names = COMMAND_REGISTRY.get_command_names(prefix)

    for name in cmd_names:
        cmd_def = COMMAND_REGISTRY.get(name)
        if not cmd_def:
            continue

        # Truncate description to 40 chars for 2-column layout
        desc = cmd_def.description_short
        if len(desc) > 40:
            desc = desc[:37] + "..."

        # Get full help for preview
        full_help = cmd_def.format_help(show_osc=False)

        items.append(CompletionItem(
            text=name,
            description=desc,
            category=cmd_def.category.category_name,
            color=cmd_def.category.color,
            full_help=full_help,
            type="command"
        ))

    return items


def format_completion_line(item: CompletionItem, width: int = 80, is_selected: bool = False) -> str:
    """
    Format a completion item for 2-column display.

    Args:
        item: CompletionItem to format
        width: Terminal width
        is_selected: Whether this item is currently selected

    Returns:
        Formatted string for display (without color codes)
    """
    # Layout: "  command_name       description text"
    #          ^-- 2 space indent
    #             ^-- 20 chars for command
    #                                ^-- remainder for description

    marker = ">" if is_selected else " "
    cmd_col_width = 20

    # Truncate command name if needed
    cmd_text = item.text[:cmd_col_width]

    # Pad command name to column width
    cmd_padded = cmd_text.ljust(cmd_col_width)

    # Calculate remaining space for description
    desc_width = width - cmd_col_width - 4  # -4 for marker and spacing
    desc_text = item.description[:desc_width]

    return f" {marker} {cmd_padded} {desc_text}"
