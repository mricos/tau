"""
User-defined command aliases with file persistence.

Aliases are stored in ~/.config/tau/aliases.toml
Format:
    [aliases]
    ll = "list_commands"
    p = "play"
"""

import os
from typing import Dict, Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

try:
    import tomli_w as toml_writer
except ImportError:
    toml_writer = None


class AliasManager:
    """Manages user-defined command aliases with persistence."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or get_default_aliases_path()
        self.aliases: Dict[str, str] = {}
        self.load()

    def load(self):
        """Load aliases from file."""
        if not os.path.exists(self.path):
            self.aliases = {}
            return

        try:
            with open(self.path, 'rb') as f:
                data = tomllib.load(f)
            self.aliases = data.get('aliases', {})
        except Exception:
            self.aliases = {}

    def save(self):
        """Save aliases to file."""
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

        data = {'aliases': self.aliases}

        if toml_writer:
            with open(self.path, 'wb') as f:
                toml_writer.dump(data, f)
        else:
            with open(self.path, 'w') as f:
                f.write("[aliases]\n")
                for alias, cmd in sorted(self.aliases.items()):
                    f.write(f'{alias} = "{cmd}"\n')

    def set(self, alias: str, command: str) -> str:
        """Set an alias. Returns status message."""
        if not alias or not command:
            return "Usage: alias <name> <command>"

        # Don't allow overwriting built-in commands
        from tau_lib.core.commands_api import COMMAND_REGISTRY
        cmd_def = COMMAND_REGISTRY.get(alias)
        if cmd_def and alias == cmd_def.name:
            return f"Cannot override built-in command: {alias}"

        old = self.aliases.get(alias)
        self.aliases[alias] = command
        self.save()

        if old:
            return f"Updated: {alias} -> {command} (was: {old})"
        return f"Added: {alias} -> {command}"

    def remove(self, alias: str) -> str:
        """Remove an alias. Returns status message."""
        if alias in self.aliases:
            cmd = self.aliases.pop(alias)
            self.save()
            return f"Removed: {alias} (was: {cmd})"
        return f"No alias: {alias}"

    def get(self, alias: str) -> Optional[str]:
        """Get command for alias, or None if not found."""
        return self.aliases.get(alias)

    def resolve(self, cmd_str: str) -> str:
        """Resolve aliases in a command string."""
        parts = cmd_str.strip().split(None, 1)
        if not parts:
            return cmd_str

        cmd_name = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        # Check user aliases first
        if cmd_name in self.aliases:
            resolved = self.aliases[cmd_name]
            if args:
                return f"{resolved} {args}"
            return resolved

        return cmd_str

    def list_all(self) -> Dict[str, str]:
        """Return all user aliases."""
        return dict(self.aliases)

    def format_list(self) -> str:
        """Format aliases for display."""
        if not self.aliases:
            return "No user aliases defined.\nUse: alias <name> <command>"

        lines = ["User aliases:"]
        for alias, cmd in sorted(self.aliases.items()):
            lines.append(f"  {alias} = {cmd}")
        lines.append(f"\nStored in: {self.path}")
        return "\n".join(lines)


def get_default_aliases_path() -> str:
    """Get default aliases file path (~/.config/tau/aliases.toml)."""
    config_dir = os.path.expanduser("~/.config/tau")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "aliases.toml")


# Global instance (initialized on first use)
_alias_manager: Optional[AliasManager] = None


def get_alias_manager() -> AliasManager:
    """Get or create the global alias manager."""
    global _alias_manager
    if _alias_manager is None:
        _alias_manager = AliasManager()
    return _alias_manager
