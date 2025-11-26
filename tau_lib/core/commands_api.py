"""
Complete SNN Command API with metadata for CLI, OSC, and UI integration.

Each command includes:
- Name and aliases
- Category and description
- Parameters with types and validation
- OSC address mapping
- Tab-completion hints
- Color suggestion (1-8) for UI theming
- Keyboard shortcuts
- Handler function
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Any, Dict
from enum import Enum


class ParamType(Enum):
    """Parameter types."""
    FLOAT = "float"
    INT = "int"
    STRING = "string"
    BOOL = "bool"
    ENUM = "enum"


class CommandCategory(Enum):
    """Command categories with color suggestions (6 categories)."""
    TRANSPORT = ("transport", 1)   # Color 1 - playback, zoom, scrub
    PARAMS = ("params", 2)         # Color 2 - kernel parameters
    LANES = ("lanes", 3)           # Color 3 - lane management, display modes
    MARKERS = ("markers", 4)       # Color 4 - markers, navigation
    VIEW = ("view", 5)             # Color 5 - display settings, video, palettes
    SYSTEM = ("system", 6)         # Color 6 - config, files, engine, project

    # Legacy aliases for backwards compatibility during transition
    ZOOM = ("transport", 1)        # -> TRANSPORT
    DISPLAY = ("view", 5)          # -> VIEW
    CONFIG = ("system", 6)         # -> SYSTEM
    UTILITY = ("system", 6)        # -> SYSTEM

    def __init__(self, name: str, color: int):
        self.category_name = name
        self.color = color


@dataclass
class CommandParam:
    """Command parameter definition."""
    name: str
    type: ParamType
    description: str
    default: Any = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    enum_values: Optional[List[str]] = None

    # Tab-completion hints
    completions: Optional[List[str]] = None  # Suggested values for tab-complete

    def __post_init__(self):
        """Auto-generate completions for enums."""
        if self.type == ParamType.ENUM and self.enum_values and not self.completions:
            self.completions = self.enum_values

    def get_osc_type(self) -> str:
        """Get OSC type tag."""
        if self.type == ParamType.FLOAT:
            return 'f'
        elif self.type in (ParamType.INT, ParamType.BOOL):
            return 'i'
        else:
            return 's'

    def format_spec(self) -> str:
        """Format parameter specification for documentation."""
        parts = [f"{self.name}"]

        if self.type == ParamType.ENUM:
            parts.append(f"({' | '.join(self.enum_values)})")
        else:
            parts.append(f"<{self.type.value}>")

        if self.min_val is not None or self.max_val is not None:
            range_str = f"[{self.min_val or '-∞'}..{self.max_val or '∞'}]"
            parts.append(range_str)

        if self.default is not None:
            parts.append(f"={self.default}")

        return " ".join(parts)


@dataclass
class CommandDef:
    """
    Complete command definition with all metadata.
    """
    # Core identity
    name: str
    category: CommandCategory
    description_short: str
    description_long: str = ""

    # Parameters
    params: List[CommandParam] = field(default_factory=list)

    # Aliases for CLI
    aliases: List[str] = field(default_factory=list)

    # OSC mapping
    osc_address: Optional[str] = None

    # Keyboard shortcut
    key_binding: Optional[str] = None

    # Handler
    handler: Optional[Callable] = None

    # UI hints
    hidden: bool = False  # Hide from help listing

    # Tab-completion
    arg_completions: Optional[Callable] = None  # Dynamic completion function

    def get_color(self) -> int:
        """Get suggested color (1-8) for this command."""
        return self.category.color

    def get_osc_address(self) -> str:
        """Get OSC address (auto-generate if not specified)."""
        if self.osc_address:
            return self.osc_address
        return f"/snn/{self.category.category_name}/{self.name}"

    def get_osc_signature(self) -> str:
        """Get OSC type signature (e.g., 'ffi')."""
        return ''.join(p.get_osc_type() for p in self.params)

    def format_usage(self, show_types: bool = False) -> str:
        """Format command usage string."""
        parts = [self.name]

        for p in self.params:
            if p.default is not None:
                parts.append(f"[{p.name}]")
            else:
                parts.append(f"<{p.name}>")

        return " ".join(parts)

    def format_help(self, show_osc: bool = True, compact: bool = False) -> List[str]:
        """Format help text."""
        lines = []

        if compact:
            # Single line format
            usage = self.format_usage()
            lines.append(f"{usage:30s} {self.description_short}")
        else:
            # Full format
            lines.append(f"Command: {self.name}")
            if self.aliases:
                lines.append(f"Aliases: {', '.join(self.aliases)}")
            lines.append(f"Usage: {self.format_usage()}")
            lines.append(f"Description: {self.description_short}")

            if self.description_long:
                lines.append("")
                lines.append(self.description_long)

            if self.params:
                lines.append("")
                lines.append("Parameters:")
                for p in self.params:
                    lines.append(f"  {p.format_spec()}")
                    lines.append(f"    {p.description}")

            if self.key_binding:
                lines.append(f"Keyboard: {self.key_binding}")

            if show_osc:
                osc_addr = self.get_osc_address()
                osc_sig = self.get_osc_signature()
                lines.append(f"OSC: {osc_addr} ({osc_sig})")

            lines.append(f"Category: {self.category.category_name} (color {self.get_color()})")

        return lines

    def get_completions(self, arg_index: int, partial: str) -> List[str]:
        """
        Get tab-completion suggestions for argument at index.

        Args:
            arg_index: Which argument (0-based)
            partial: Partial string typed so far

        Returns:
            List of completion suggestions
        """
        # Check if we have a dynamic completion function
        if self.arg_completions:
            return self.arg_completions(arg_index, partial)

        # Use static completions from parameter definition
        if arg_index < len(self.params):
            param = self.params[arg_index]
            if param.completions:
                # Filter by partial match
                return [c for c in param.completions if c.startswith(partial)]

        return []

    def invoke(self, args: List[Any]) -> Any:
        """Invoke command with arguments."""
        if not self.handler:
            raise RuntimeError(f"Command {self.name} has no handler")

        # Validate argument count
        required_params = [p for p in self.params if p.default is None]
        if len(args) < len(required_params):
            raise ValueError(f"Missing required parameters. Usage: {self.format_usage()}")

        # Convert and validate arguments
        validated_args = []
        for i, param in enumerate(self.params):
            if i < len(args):
                value = args[i]

                # Type conversion
                if param.type == ParamType.FLOAT:
                    value = float(value)
                elif param.type == ParamType.INT:
                    value = int(value)
                elif param.type == ParamType.BOOL:
                    value = bool(value)

                # Range validation
                if param.type in (ParamType.FLOAT, ParamType.INT):
                    if param.min_val is not None and value < param.min_val:
                        raise ValueError(f"{param.name} must be >= {param.min_val}")
                    if param.max_val is not None and value > param.max_val:
                        raise ValueError(f"{param.name} must be <= {param.max_val}")

                # Enum validation
                if param.type == ParamType.ENUM:
                    if value not in param.enum_values:
                        raise ValueError(f"{param.name} must be one of: {', '.join(param.enum_values)}")

                validated_args.append(value)
            elif param.default is not None:
                validated_args.append(param.default)
            else:
                raise ValueError(f"Missing required parameter: {param.name}")

        return self.handler(*validated_args)


class CommandRegistry:
    """
    Global registry of all SNN commands.
    Provides lookup by name, category, OSC address, etc.
    """

    def __init__(self):
        self.commands: Dict[str, CommandDef] = {}
        self.by_category: Dict[CommandCategory, List[CommandDef]] = {}
        self.by_osc: Dict[str, CommandDef] = {}
        self.by_key: Dict[str, CommandDef] = {}

        # Initialize category buckets
        for cat in CommandCategory:
            self.by_category[cat] = []

    def register(self, cmd: CommandDef):
        """Register a command."""
        # By name
        self.commands[cmd.name] = cmd

        # By aliases
        for alias in cmd.aliases:
            self.commands[alias] = cmd

        # By category
        self.by_category[cmd.category].append(cmd)

        # By OSC address
        osc_addr = cmd.get_osc_address()
        self.by_osc[osc_addr] = cmd

        # By keyboard shortcut
        if cmd.key_binding:
            self.by_key[cmd.key_binding] = cmd

    def get(self, name: str) -> Optional[CommandDef]:
        """Get command by name or alias."""
        return self.commands.get(name)

    def get_by_osc(self, address: str) -> Optional[CommandDef]:
        """Get command by OSC address."""
        return self.by_osc.get(address)

    def get_by_key(self, key: str) -> Optional[CommandDef]:
        """Get command by keyboard shortcut."""
        return self.by_key.get(key)

    def list_all(self, include_hidden: bool = False) -> List[CommandDef]:
        """List all commands."""
        seen = set()
        result = []

        for cmd in self.commands.values():
            if cmd.name in seen:
                continue
            if not include_hidden and cmd.hidden:
                continue

            seen.add(cmd.name)
            result.append(cmd)

        return sorted(result, key=lambda c: (c.category.category_name, c.name))

    def list_by_category(self, category: CommandCategory, include_hidden: bool = False) -> List[CommandDef]:
        """List commands in a category."""
        commands = self.by_category.get(category, [])

        if not include_hidden:
            commands = [c for c in commands if not c.hidden]

        return sorted(commands, key=lambda c: c.name)

    def get_command_names(self, prefix: str = "") -> List[str]:
        """
        Get all command names for tab-completion.

        Args:
            prefix: Filter by prefix

        Returns:
            List of command names matching prefix
        """
        names = set()

        for cmd in self.commands.values():
            if not cmd.hidden:
                if cmd.name.startswith(prefix):
                    names.add(cmd.name)

                for alias in cmd.aliases:
                    if alias.startswith(prefix):
                        names.add(alias)

        return sorted(names)

    def export_api_doc(self, filepath: str):
        """Export complete API documentation."""
        lines = []
        lines.append("# ASCII Scope SNN - Command API Reference")
        lines.append("")
        lines.append("Complete reference for CLI, API, and OSC control.")
        lines.append("")
        lines.append("## Quick Reference")
        lines.append("")
        lines.append("| Command | Category | Color | Description |")
        lines.append("|---------|----------|-------|-------------|")

        for cmd in self.list_all():
            lines.append(f"| `{cmd.name}` | {cmd.category.category_name} | {cmd.get_color()} | {cmd.description_short} |")

        lines.append("")

        # By category
        for category in CommandCategory:
            commands = self.list_by_category(category)
            if not commands:
                continue

            lines.append(f"## {category.category_name.upper()} Commands (Color {category.color})")
            lines.append("")

            for cmd in commands:
                lines.append(f"### {cmd.name}")
                lines.append("")

                # Basic info
                lines.append(f"**Category:** {category.category_name}")
                lines.append(f"**Color:** {cmd.get_color()}")
                if cmd.aliases:
                    lines.append(f"**Aliases:** {', '.join(cmd.aliases)}")
                if cmd.key_binding:
                    lines.append(f"**Keyboard:** `{cmd.key_binding}`")
                lines.append(f"**OSC:** `{cmd.get_osc_address()}` ({cmd.get_osc_signature()})")
                lines.append("")

                # Description
                lines.append(f"**Description:** {cmd.description_short}")
                if cmd.description_long:
                    lines.append("")
                    lines.append(cmd.description_long)
                lines.append("")

                # Usage
                lines.append(f"**Usage:** `{cmd.format_usage()}`")
                lines.append("")

                # Parameters
                if cmd.params:
                    lines.append("**Parameters:**")
                    for i, p in enumerate(cmd.params, 1):
                        req = "" if p.default is None else " (optional)"
                        lines.append(f"{i}. `{p.name}` ({p.type.value}){req}: {p.description}")
                        if p.min_val is not None or p.max_val is not None:
                            lines.append(f"   - Range: {p.min_val or '-∞'} to {p.max_val or '∞'}")
                        if p.default is not None:
                            lines.append(f"   - Default: {p.default}")
                        if p.completions:
                            lines.append(f"   - Completions: {', '.join(p.completions[:5])}")
                    lines.append("")

                # Examples
                lines.append("**Examples:**")
                lines.append("```")
                lines.append(f"# CLI")
                if cmd.params:
                    example_args = " ".join(str(p.default or "...") for p in cmd.params)
                    lines.append(f":{cmd.name} {example_args}")
                else:
                    lines.append(f":{cmd.name}")

                lines.append("")
                lines.append(f"# OSC")
                if cmd.params:
                    example_args = " ".join(str(p.default or "0") for p in cmd.params)
                    lines.append(f"{cmd.get_osc_address()} {example_args}")
                else:
                    lines.append(f"{cmd.get_osc_address()}")

                if cmd.handler:
                    lines.append("")
                    lines.append(f"# Python API")
                    lines.append(f"registry.get('{cmd.name}').invoke([...])")

                lines.append("```")
                lines.append("")

        # Color guide
        lines.append("## Color Guide")
        lines.append("")
        lines.append("Commands are color-coded by category for UI integration:")
        lines.append("")
        lines.append("| Color | Category | Usage |")
        lines.append("|-------|----------|-------|")
        for cat in CommandCategory:
            lines.append(f"| {cat.color} | {cat.category_name} | Primary UI theme color |")
        lines.append("")

        # Tab completion
        lines.append("## Tab Completion")
        lines.append("")
        lines.append("Commands support tab-completion in CLI mode:")
        lines.append("")
        lines.append("1. **Command names** - Type `:p<TAB>` → suggests `play`, `points`, `prev_marker`")
        lines.append("2. **Parameter values** - Type `:toggle_mode <TAB>` → suggests `envelope`, `points`")
        lines.append("3. **File paths** - Commands with file parameters support path completion")
        lines.append("")

        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))


# Global command registry
COMMAND_REGISTRY = CommandRegistry()
