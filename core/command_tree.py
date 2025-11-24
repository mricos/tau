"""
Command tree system with integrated help, CLI, API, and OSC mapping.
Provides a unified command definition that can be invoked via:
- CLI commands
- Python API calls
- OSC messages
- Keyboard shortcuts
"""

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Any, Dict
from enum import Enum


class ParamType(Enum):
    """Parameter types for command arguments."""
    FLOAT = "float"
    INT = "int"
    STRING = "string"
    BOOL = "bool"
    ENUM = "enum"


@dataclass
class CommandParam:
    """Definition of a command parameter."""
    name: str
    type: ParamType
    help: str
    default: Any = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    enum_values: Optional[List[str]] = None

    # OSC mapping
    osc_type: str = None  # 'f' (float), 'i' (int), 's' (string)

    def __post_init__(self):
        """Auto-determine OSC type from ParamType."""
        if self.osc_type is None:
            if self.type == ParamType.FLOAT:
                self.osc_type = 'f'
            elif self.type == ParamType.INT:
                self.osc_type = 'i'
            elif self.type == ParamType.BOOL:
                self.osc_type = 'i'  # 0/1
            else:
                self.osc_type = 's'  # String

    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate parameter value.

        Returns:
            (is_valid, error_message)
        """
        if self.type == ParamType.FLOAT:
            try:
                v = float(value)
                if self.min_val is not None and v < self.min_val:
                    return False, f"{self.name} must be >= {self.min_val}"
                if self.max_val is not None and v > self.max_val:
                    return False, f"{self.name} must be <= {self.max_val}"
                return True, None
            except ValueError:
                return False, f"{self.name} must be a number"

        elif self.type == ParamType.INT:
            try:
                v = int(value)
                if self.min_val is not None and v < self.min_val:
                    return False, f"{self.name} must be >= {self.min_val}"
                if self.max_val is not None and v > self.max_val:
                    return False, f"{self.name} must be <= {self.max_val}"
                return True, None
            except ValueError:
                return False, f"{self.name} must be an integer"

        elif self.type == ParamType.ENUM:
            if value not in self.enum_values:
                return False, f"{self.name} must be one of: {', '.join(self.enum_values)}"
            return True, None

        return True, None


@dataclass
class Command:
    """
    Command definition with help, CLI, API, and OSC mapping.
    """
    # Core definition
    name: str
    category: str
    help_short: str
    help_long: str = ""

    # Parameters
    params: List[CommandParam] = field(default_factory=list)

    # Handler function
    handler: Optional[Callable] = None

    # CLI aliases
    aliases: List[str] = field(default_factory=list)

    # OSC address (e.g., "/snn/transport/play")
    osc_address: Optional[str] = None

    # Keyboard shortcut
    key_binding: Optional[str] = None

    # Visibility
    hidden: bool = False  # Hide from help listing

    def get_osc_address(self) -> str:
        """Get OSC address for this command."""
        if self.osc_address:
            return self.osc_address
        # Auto-generate from category and name
        return f"/snn/{self.category}/{self.name}"

    def get_osc_signature(self) -> str:
        """Get OSC type signature (e.g., 'ffi' for 2 floats and 1 int)."""
        return ''.join(p.osc_type for p in self.params)

    def format_usage(self, compact: bool = False) -> str:
        """Format command usage string."""
        if compact:
            params_str = ' '.join(f"<{p.name}>" for p in self.params)
            return f"{self.name} {params_str}".strip()
        else:
            params_parts = []
            for p in self.params:
                if p.default is not None:
                    params_parts.append(f"[{p.name}={p.default}]")
                else:
                    params_parts.append(f"<{p.name}>")
            params_str = ' '.join(params_parts)
            return f"{self.name} {params_str}".strip()

    def format_help(self, show_osc: bool = False) -> List[str]:
        """Format multi-line help text."""
        lines = []

        # Usage line
        lines.append(f"Usage: {self.format_usage()}")

        # Short description
        lines.append(f"  {self.help_short}")

        # Long description if available
        if self.help_long:
            lines.append("")
            lines.append(f"  {self.help_long}")

        # Parameters
        if self.params:
            lines.append("")
            lines.append("Parameters:")
            for p in self.params:
                default_str = f" (default: {p.default})" if p.default is not None else ""
                range_str = ""
                if p.min_val is not None or p.max_val is not None:
                    range_str = f" [{p.min_val or ''} .. {p.max_val or ''}]"
                lines.append(f"  {p.name:12s} {p.help}{default_str}{range_str}")

        # Key binding
        if self.key_binding:
            lines.append(f"Shortcut: {self.key_binding}")

        # OSC address
        if show_osc and self.osc_address:
            sig = self.get_osc_signature()
            lines.append(f"OSC: {self.get_osc_address()} ({sig})")

        return lines

    def invoke(self, args: List[Any]) -> Any:
        """
        Invoke command with arguments.

        Args:
            args: List of argument values

        Returns:
            Command result
        """
        if not self.handler:
            raise RuntimeError(f"Command {self.name} has no handler")

        # Validate argument count
        required_params = [p for p in self.params if p.default is None]
        if len(args) < len(required_params):
            raise ValueError(f"Missing required parameters for {self.name}")

        # Validate and convert arguments
        validated_args = []
        for i, param in enumerate(self.params):
            if i < len(args):
                value = args[i]
                is_valid, error = param.validate(value)
                if not is_valid:
                    raise ValueError(error)

                # Convert to proper type
                if param.type == ParamType.FLOAT:
                    validated_args.append(float(value))
                elif param.type == ParamType.INT:
                    validated_args.append(int(value))
                elif param.type == ParamType.BOOL:
                    validated_args.append(bool(value))
                else:
                    validated_args.append(value)
            elif param.default is not None:
                validated_args.append(param.default)
            else:
                raise ValueError(f"Missing required parameter: {param.name}")

        # Invoke handler
        return self.handler(*validated_args)


class CommandTree:
    """
    Registry of all commands organized by category.
    Supports CLI, API, OSC, and keyboard invocation.
    """

    def __init__(self):
        self.commands: Dict[str, Command] = {}
        self.categories: Dict[str, List[Command]] = {}
        self.osc_map: Dict[str, Command] = {}  # OSC address -> Command
        self.key_map: Dict[str, Command] = {}  # Key binding -> Command

    def register(self, command: Command):
        """Register a command."""
        # Main registry
        self.commands[command.name] = command

        # By category
        if command.category not in self.categories:
            self.categories[command.category] = []
        self.categories[command.category].append(command)

        # OSC mapping
        osc_addr = command.get_osc_address()
        self.osc_map[osc_addr] = command

        # Key binding
        if command.key_binding:
            self.key_map[command.key_binding] = command

        # Aliases
        for alias in command.aliases:
            self.commands[alias] = command

    def get(self, name: str) -> Optional[Command]:
        """Get command by name or alias."""
        return self.commands.get(name)

    def get_by_osc(self, osc_address: str) -> Optional[Command]:
        """Get command by OSC address."""
        return self.osc_map.get(osc_address)

    def get_by_key(self, key: str) -> Optional[Command]:
        """Get command by key binding."""
        return self.key_map.get(key)

    def list_categories(self) -> List[str]:
        """List all command categories."""
        return sorted(self.categories.keys())

    def list_commands(self, category: Optional[str] = None, include_hidden: bool = False) -> List[Command]:
        """
        List commands, optionally filtered by category.

        Args:
            category: Category to filter by (None = all)
            include_hidden: Include hidden commands

        Returns:
            List of commands
        """
        if category:
            commands = self.categories.get(category, [])
        else:
            commands = list(self.commands.values())

        if not include_hidden:
            commands = [c for c in commands if not c.hidden]

        # Remove duplicates (from aliases)
        seen = set()
        result = []
        for cmd in commands:
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append(cmd)

        return sorted(result, key=lambda c: c.name)

    def format_help(self, category: Optional[str] = None, compact: bool = False) -> List[str]:
        """
        Format help text for commands.

        Args:
            category: Category to show help for (None = all categories)
            compact: Use compact format

        Returns:
            Lines of help text
        """
        lines = []

        if category:
            # Single category
            commands = self.list_commands(category)
            lines.append(f"=== {category.upper()} COMMANDS ===")
            lines.append("")
            for cmd in commands:
                if compact:
                    lines.append(f"  {cmd.format_usage(compact=True):30s} {cmd.help_short}")
                else:
                    lines.extend(cmd.format_help())
                    lines.append("")
        else:
            # All categories
            for cat in self.list_categories():
                commands = self.list_commands(cat)
                if not commands:
                    continue

                lines.append(f"=== {cat.upper()} ===")
                for cmd in commands:
                    lines.append(f"  {cmd.format_usage(compact=True):30s} {cmd.help_short}")
                lines.append("")

        return lines

    def export_osc_spec(self, filepath: str):
        """
        Export OSC control specification to file.

        Args:
            filepath: Output file path
        """
        lines = []
        lines.append("# ASCII Scope SNN - OSC Control Specification")
        lines.append("# Generated command tree with OSC mappings")
        lines.append("")

        for category in self.list_categories():
            lines.append(f"## {category.upper()}")
            lines.append("")

            commands = self.list_commands(category)
            for cmd in commands:
                osc_addr = cmd.get_osc_address()
                osc_sig = cmd.get_osc_signature()

                lines.append(f"### {cmd.name}")
                lines.append(f"**OSC Address:** `{osc_addr}`")
                lines.append(f"**Type Signature:** `{osc_sig}`")
                lines.append(f"**Description:** {cmd.help_short}")

                if cmd.params:
                    lines.append("")
                    lines.append("**Parameters:**")
                    for p in cmd.params:
                        lines.append(f"- `{p.name}` ({p.type.value}): {p.help}")

                lines.append("")

        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))


# Global command tree instance
COMMAND_TREE = CommandTree()
