"""
Tetra Device Configuration
Cross-platform audio device discovery and configuration management.

This module provides:
- Device enumeration via tau-engine (miniaudio backend)
- Friendly name aliases from ~/.config/tetra/devices.toml
- Per-app configuration from ~/.config/tetra/apps/<app>.toml
- Shared profiles from ~/.config/tetra/profiles/

Config Structure:
    ~/.config/tetra/
    ├── devices.toml          # Global device aliases
    ├── apps/
    │   ├── tau.toml          # tau's config
    │   ├── screentool.toml   # screentool's config
    │   └── ...
    └── profiles/
        ├── parking-garage.toml
        └── ...

Usage:
    from tau_lib.core.devices import TetraDevices

    devices = TetraDevices()

    # List available devices
    capture_devices = devices.list_capture_devices()
    playback_devices = devices.list_playback_devices()

    # Resolve friendly name to device
    device = devices.resolve_capture("podcaster")

    # Get/set app config
    config = devices.get_app_config("screentool")
    devices.set_app_config("tau", {"recording": {"capture_device": "blackhole"}})

    # List what apps are using tetra
    apps = devices.list_apps()
"""

import os
import re
import socket
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib

try:
    import tomli_w as toml_writer
except ImportError:
    toml_writer = None


# Default paths
TETRA_CONFIG_DIR = Path.home() / ".config" / "tetra"
DEVICES_TOML = TETRA_CONFIG_DIR / "devices.toml"
APPS_DIR = TETRA_CONFIG_DIR / "apps"
PROFILES_DIR = TETRA_CONFIG_DIR / "profiles"

# Default tau-engine socket
DEFAULT_TAU_SOCKET = Path.home() / "tau" / "runtime" / "tau.sock"


@dataclass
class AudioDevice:
    """Represents an audio device from tau-engine."""
    index: int
    name: str
    is_default: bool = False
    is_current: bool = False
    device_type: str = "capture"  # "capture" or "playback"

    def __str__(self):
        markers = []
        if self.is_default:
            markers.append("default")
        if self.is_current:
            markers.append("current")
        marker_str = f" [{', '.join(markers)}]" if markers else ""
        return f"[{self.index}] {self.name}{marker_str}"


@dataclass
class DeviceConfig:
    """Device configuration with resolved device info."""
    capture_device: Optional[str] = None
    playback_device: Optional[str] = None
    sample_rate: int = 48000
    channels: int = 2
    bit_depth: int = 32

    # Resolved device info (filled in by resolve())
    capture_index: Optional[int] = None
    capture_name: Optional[str] = None
    playback_index: Optional[int] = None
    playback_name: Optional[str] = None


class TetraDevices:
    """
    Tetra device configuration manager.

    Provides device enumeration, friendly name resolution, and
    per-app configuration management.
    """

    def __init__(self, socket_path: Optional[Path] = None):
        """
        Initialize device manager.

        Args:
            socket_path: Path to tau-engine socket (default: ~/tau/runtime/tau.sock)
        """
        self.socket_path = socket_path or DEFAULT_TAU_SOCKET
        self._aliases: Dict[str, Dict[str, str]] = {}
        self._defaults: Dict[str, Any] = {}
        self._load_device_aliases()

    def _load_device_aliases(self):
        """Load device aliases from devices.toml."""
        if not DEVICES_TOML.exists():
            return

        try:
            with open(DEVICES_TOML, 'rb') as f:
                config = tomllib.load(f)

            self._aliases = {
                'capture': config.get('capture', {}),
                'playback': config.get('playback', {}),
            }
            self._defaults = config.get('defaults', {})
        except Exception as e:
            print(f"Warning: Failed to load {DEVICES_TOML}: {e}")

    def _send_command(self, cmd: str, timeout: float = 2.0) -> str:
        """Send command to tau-engine and return response."""
        if not self.socket_path.exists():
            raise ConnectionError(f"tau-engine socket not found: {self.socket_path}")

        # Create client socket
        client_path = f"/tmp/tau-devices-{os.getpid()}.sock"
        try:
            os.unlink(client_path)
        except OSError:
            pass

        client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            client.bind(client_path)
            client.settimeout(timeout)
            client.sendto(cmd.encode(), str(self.socket_path))
            response = client.recv(16384).decode()
            return response
        finally:
            client.close()
            try:
                os.unlink(client_path)
            except OSError:
                pass

    def _parse_devices_response(self, response: str) -> tuple[List[AudioDevice], List[AudioDevice]]:
        """Parse DEVICES command response."""
        capture_devices = []
        playback_devices = []

        for line in response.strip().split('\n'):
            if line.startswith('CAPTURE '):
                # Format: CAPTURE <idx> <is_default> <is_current> <name>
                parts = line.split(' ', 4)
                if len(parts) >= 5:
                    capture_devices.append(AudioDevice(
                        index=int(parts[1]),
                        is_default=parts[2] == '1',
                        is_current=parts[3] == '1',
                        name=parts[4],
                        device_type='capture'
                    ))
            elif line.startswith('PLAYBACK '):
                parts = line.split(' ', 4)
                if len(parts) >= 5:
                    playback_devices.append(AudioDevice(
                        index=int(parts[1]),
                        is_default=parts[2] == '1',
                        is_current=parts[3] == '1',
                        name=parts[4],
                        device_type='playback'
                    ))

        return capture_devices, playback_devices

    def list_devices(self) -> tuple[List[AudioDevice], List[AudioDevice]]:
        """
        List all available audio devices.

        Returns:
            Tuple of (capture_devices, playback_devices)
        """
        response = self._send_command("DEVICES")
        return self._parse_devices_response(response)

    def list_capture_devices(self) -> List[AudioDevice]:
        """List available capture (input) devices."""
        capture, _ = self.list_devices()
        return capture

    def list_playback_devices(self) -> List[AudioDevice]:
        """List available playback (output) devices."""
        _, playback = self.list_devices()
        return playback

    def resolve_device(self, identifier: str, device_type: str = "capture") -> Optional[AudioDevice]:
        """
        Resolve a device identifier to an AudioDevice.

        Args:
            identifier: Device name, alias, index, or "default"
            device_type: "capture" or "playback"

        Returns:
            AudioDevice if found, None otherwise
        """
        devices = self.list_capture_devices() if device_type == "capture" else self.list_playback_devices()

        if not devices:
            return None

        # Check if it's an alias
        aliases = self._aliases.get(device_type, {})
        if identifier in aliases:
            identifier = aliases[identifier]

        # "default" - return the default device
        if identifier.lower() == "default":
            for dev in devices:
                if dev.is_default:
                    return dev
            return devices[0] if devices else None

        # Numeric index
        if identifier.isdigit():
            idx = int(identifier)
            for dev in devices:
                if dev.index == idx:
                    return dev
            return None

        # Name/pattern match (case-insensitive substring)
        pattern = identifier.lower()
        for dev in devices:
            if pattern in dev.name.lower():
                return dev

        return None

    def resolve_capture(self, identifier: str) -> Optional[AudioDevice]:
        """Resolve a capture device identifier."""
        return self.resolve_device(identifier, "capture")

    def resolve_playback(self, identifier: str) -> Optional[AudioDevice]:
        """Resolve a playback device identifier."""
        return self.resolve_device(identifier, "playback")

    def select_device(self, identifier: str, device_type: str = "capture") -> Optional[AudioDevice]:
        """
        Select a device in tau-engine.

        Args:
            identifier: Device name, alias, index, or "default"
            device_type: "capture" or "playback"

        Returns:
            Selected AudioDevice, or None if not found
        """
        device = self.resolve_device(identifier, device_type)
        if not device:
            return None

        cmd = f"DEVICE {device_type} {device.index}"
        response = self._send_command(cmd)

        if response.startswith("OK"):
            return device
        return None

    def get_aliases(self, device_type: str = "capture") -> Dict[str, str]:
        """Get device aliases for a device type."""
        return self._aliases.get(device_type, {})

    def set_alias(self, alias: str, pattern: str, device_type: str = "capture"):
        """
        Set a device alias.

        Args:
            alias: Friendly name
            pattern: Device name pattern to match
            device_type: "capture" or "playback"
        """
        if device_type not in self._aliases:
            self._aliases[device_type] = {}
        self._aliases[device_type][alias] = pattern
        self._save_device_aliases()

    def _save_device_aliases(self):
        """Save device aliases to devices.toml."""
        TETRA_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        config = {
            'capture': self._aliases.get('capture', {}),
            'playback': self._aliases.get('playback', {}),
            'defaults': self._defaults,
        }

        if toml_writer:
            with open(DEVICES_TOML, 'wb') as f:
                toml_writer.dump(config, f)
        else:
            # Manual TOML writing
            with open(DEVICES_TOML, 'w') as f:
                f.write("# Tetra Device Configuration\n\n")
                for section, values in config.items():
                    if isinstance(values, dict) and values:
                        f.write(f"[{section}]\n")
                        for k, v in values.items():
                            if isinstance(v, str):
                                f.write(f'{k} = "{v}"\n')
                            else:
                                f.write(f'{k} = {v}\n')
                        f.write("\n")

    # --- App Configuration ---

    def list_apps(self) -> List[str]:
        """List apps that have tetra configuration."""
        if not APPS_DIR.exists():
            return []
        return [f.stem for f in APPS_DIR.glob("*.toml")]

    def get_app_config(self, app_name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for an app.

        Args:
            app_name: App name (e.g., "tau", "screentool")

        Returns:
            Config dict or None if not found
        """
        config_path = APPS_DIR / f"{app_name}.toml"
        if not config_path.exists():
            return None

        with open(config_path, 'rb') as f:
            return tomllib.load(f)

    def set_app_config(self, app_name: str, config: Dict[str, Any]):
        """
        Set configuration for an app.

        Args:
            app_name: App name
            config: Config dict to save
        """
        APPS_DIR.mkdir(parents=True, exist_ok=True)
        config_path = APPS_DIR / f"{app_name}.toml"

        # Merge with existing config
        existing = self.get_app_config(app_name) or {}

        def deep_merge(base: dict, update: dict) -> dict:
            result = base.copy()
            for k, v in update.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k] = deep_merge(result[k], v)
                else:
                    result[k] = v
            return result

        merged = deep_merge(existing, config)
        merged['app'] = app_name

        if toml_writer:
            with open(config_path, 'wb') as f:
                toml_writer.dump(merged, f)
        else:
            # Manual TOML writing (basic)
            with open(config_path, 'w') as f:
                f.write(f"# {app_name} Configuration\n\n")
                for key, value in merged.items():
                    if isinstance(value, dict):
                        f.write(f"\n[{key}]\n")
                        for k, v in value.items():
                            if isinstance(v, str):
                                f.write(f'{k} = "{v}"\n')
                            else:
                                f.write(f'{k} = {v}\n')
                    elif isinstance(value, str):
                        f.write(f'{key} = "{value}"\n')
                    else:
                        f.write(f'{key} = {value}\n')

    # --- Profiles ---

    def list_profiles(self) -> List[str]:
        """List available profiles."""
        if not PROFILES_DIR.exists():
            return []
        return [f.stem for f in PROFILES_DIR.glob("*.toml")]

    def get_profile(self, profile_name: str) -> Optional[Dict[str, Any]]:
        """Get a profile configuration."""
        profile_path = PROFILES_DIR / f"{profile_name}.toml"
        if not profile_path.exists():
            return None

        with open(profile_path, 'rb') as f:
            return tomllib.load(f)

    def save_profile(self, profile_name: str, config: Dict[str, Any],
                     created_by: str = "tau"):
        """
        Save a profile.

        Args:
            profile_name: Profile name
            config: Profile configuration
            created_by: App that created this profile
        """
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        profile_path = PROFILES_DIR / f"{profile_name}.toml"

        config['name'] = profile_name
        config['created_by'] = created_by

        if toml_writer:
            with open(profile_path, 'wb') as f:
                toml_writer.dump(config, f)
        else:
            with open(profile_path, 'w') as f:
                f.write(f"# Profile: {profile_name}\n\n")
                for key, value in config.items():
                    if isinstance(value, dict):
                        f.write(f"\n[{key}]\n")
                        for k, v in value.items():
                            if isinstance(v, str):
                                f.write(f'{k} = "{v}"\n')
                            else:
                                f.write(f'{k} = {v}\n')
                    elif isinstance(value, str):
                        f.write(f'{key} = "{value}"\n')
                    else:
                        f.write(f'{key} = {value}\n')


# Convenience functions

def list_devices(socket_path: Optional[Path] = None) -> tuple[List[AudioDevice], List[AudioDevice]]:
    """List all audio devices."""
    return TetraDevices(socket_path).list_devices()


def resolve_capture(identifier: str, socket_path: Optional[Path] = None) -> Optional[AudioDevice]:
    """Resolve a capture device identifier."""
    return TetraDevices(socket_path).resolve_capture(identifier)


def resolve_playback(identifier: str, socket_path: Optional[Path] = None) -> Optional[AudioDevice]:
    """Resolve a playback device identifier."""
    return TetraDevices(socket_path).resolve_playback(identifier)


# CLI for testing
if __name__ == "__main__":
    import sys

    devices = TetraDevices()

    if len(sys.argv) < 2:
        print("Usage: python devices.py <command>")
        print("Commands: list, aliases, apps, profiles, resolve <name>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        try:
            capture, playback = devices.list_devices()
            print("CAPTURE DEVICES:")
            for dev in capture:
                print(f"  {dev}")
            print("\nPLAYBACK DEVICES:")
            for dev in playback:
                print(f"  {dev}")
        except ConnectionError as e:
            print(f"Error: {e}")
            print("Is tau-engine running?")

    elif cmd == "aliases":
        print("CAPTURE ALIASES:")
        for alias, pattern in devices.get_aliases("capture").items():
            print(f"  {alias} → {pattern}")
        print("\nPLAYBACK ALIASES:")
        for alias, pattern in devices.get_aliases("playback").items():
            print(f"  {alias} → {pattern}")

    elif cmd == "apps":
        apps = devices.list_apps()
        print("APPS WITH TETRA CONFIG:")
        for app in apps:
            config = devices.get_app_config(app)
            desc = config.get('description', '') if config else ''
            print(f"  {app}: {desc}")

    elif cmd == "profiles":
        profiles = devices.list_profiles()
        print("AVAILABLE PROFILES:")
        for profile in profiles:
            config = devices.get_profile(profile)
            desc = config.get('description', '') if config else ''
            created_by = config.get('created_by', '') if config else ''
            print(f"  {profile}: {desc} (by {created_by})")

    elif cmd == "resolve" and len(sys.argv) >= 3:
        identifier = sys.argv[2]
        device = devices.resolve_capture(identifier)
        if device:
            print(f"Resolved '{identifier}' → {device}")
        else:
            print(f"Device not found: {identifier}")

    else:
        print(f"Unknown command: {cmd}")
