"""
CLI command parser for ASCII Scope SNN.
Parses prefix-style commands: verb target value
Example: gain ch1 1.5
"""

import re
from typing import Tuple, Optional, List, Any


class CommandParseError(Exception):
    """Raised when command parsing fails."""
    pass


def parse_channel_target(target: str) -> Optional[int]:
    """
    Parse channel target (ch0, ch1, ch2, ch3).

    Returns:
        Channel ID (0-3) or None if not a channel target
    """
    match = re.match(r'ch(\d+)$', target.lower())
    if match:
        ch_id = int(match.group(1))
        if 0 <= ch_id <= 3:
            return ch_id
    return None


def parse_value_with_unit(value_str: str) -> Tuple[float, Optional[str]]:
    """
    Parse value with optional unit suffix.

    Examples:
        "1.5" -> (1.5, None)
        "10ms" -> (0.01, "s")  # Convert to seconds
        "120Hz" -> (120.0, "Hz")
        "1.5x" -> (1.5, "x")  # Multiplier

    Returns:
        (value, unit) where unit is normalized
    """
    value_str = value_str.strip()

    # Check for multiplier suffix
    if value_str.endswith('x'):
        return (float(value_str[:-1]), 'x')

    # Check for time units
    if value_str.endswith('ms'):
        return (float(value_str[:-2]) / 1000.0, 's')
    if value_str.endswith('us') or value_str.endswith('μs'):
        return (float(value_str[:-2]) / 1e6, 's')
    if value_str.endswith('s'):
        return (float(value_str[:-1]), 's')

    # Check for frequency
    if value_str.endswith('Hz'):
        return (float(value_str[:-2]), 'Hz')

    # Plain number
    return (float(value_str), None)


def parse_command(cmd_str: str) -> Tuple[str, List[Any]]:
    """
    Parse command string into (verb, args).

    Examples:
        "play" -> ("play", [])
        "seek 1.5" -> ("seek", [1.5])
        "gain ch1 1.5" -> ("gain", ["ch1", 1.5])
        "mark label1" -> ("mark", ["label1"])
        "mark 1.5 label1" -> ("mark", [1.5, "label1"])

    Returns:
        (verb, args) where args is list of parsed arguments

    Raises:
        CommandParseError if parsing fails
    """
    cmd_str = cmd_str.strip()
    if not cmd_str:
        raise CommandParseError("Empty command")

    parts = cmd_str.split()
    verb = parts[0].lower()
    args = []

    # Parse remaining parts
    i = 1
    while i < len(parts):
        part = parts[i]

        # Try to parse as number (with optional unit)
        try:
            value, unit = parse_value_with_unit(part)
            args.append(value if unit != 'x' else (value, unit))
            i += 1
            continue
        except ValueError:
            pass

        # Check if it's a channel target
        ch_id = parse_channel_target(part)
        if ch_id is not None:
            args.append(('channel', ch_id))
            i += 1
            continue

        # Otherwise treat as string argument
        args.append(part)
        i += 1

    return (verb, args)


def format_args_for_display(args: List[Any]) -> str:
    """Format arguments for display in help/error messages."""
    formatted = []
    for arg in args:
        if isinstance(arg, tuple):
            if arg[0] == 'channel':
                formatted.append(f"ch{arg[1]}")
            elif arg[0] == 'x':
                formatted.append(f"{arg[1]}x")
            else:
                formatted.append(str(arg))
        else:
            formatted.append(str(arg))
    return " ".join(formatted)
