"""
OSC command suite for tau.

Commands:
  osc on/off     - Enable/disable OSC server on UDP port 1983
  osc status     - Show OSC connection status
  osc monitor    - Toggle monitoring of incoming OSC messages
  osc send       - Send an OSC message
  osc list       - List registered OSC addresses
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)


class OSCState:
    """
    Manages OSC server state and monitoring.

    Singleton instance created on first use.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.enabled = False
        self.monitoring = False
        self.port = 1983
        self.host = "0.0.0.0"
        self.multicast = "239.1.1.1"  # Same as midi.js
        self.server = None
        self.dispatcher = None
        self.server_thread = None
        self.socket = None
        self.message_log = []  # Recent messages for display
        self.max_log_size = 100
        self.app_state = None  # Reference to app state for output

        # MIDI CC learning support
        self.last_cc = None  # (cc_number, value) of most recent CC message
        self.cc_mappings = {}  # {param_path: cc_number} - learned mappings
        self.param_mode = None  # Reference to ParamModeManager for slider updates

        # Check if python-osc is available
        try:
            from pythonosc import dispatcher, osc_server
            self.osc_available = True
        except ImportError:
            self.osc_available = False

    def set_app_state(self, app_state):
        """Set reference to app state for output callbacks."""
        self.app_state = app_state

    def _log_message(self, msg: str):
        """Log message to both CLI output and log lane."""
        self.message_log.append(msg)
        if len(self.message_log) > self.max_log_size:
            self.message_log.pop(0)

        if self.monitoring and self.app_state:
            # Output to CLI
            if hasattr(self.app_state, 'cli') and self.app_state.cli:
                self.app_state.cli.add_output(msg)
            # Output to log lane
            if hasattr(self.app_state, 'lanes') and self.app_state.lanes:
                self.app_state.lanes.add_log(msg, "OSC")
            # Trigger screen redraw
            if hasattr(self.app_state, 'features'):
                self.app_state.features.needs_redraw = True

    def _osc_handler(self, address, *args):
        """Default handler for all OSC messages."""
        args_str = " ".join(str(a) for a in args) if args else ""
        msg = f"OSC: {address} {args_str}"
        self._log_message(msg)

        # Track MIDI CC messages for learn mode
        # Common OSC patterns for MIDI CC: /midi/cc, /cc, /control, etc.
        incoming_cc = None  # (cc_num, cc_val) for this message only

        if '/cc' in address.lower() or '/control' in address.lower():
            # Try to extract CC number from address path first
            # Format: /midi/raw/cc/<channel>/<cc_number> <value>
            # or: /midi/cc/<cc_number> <value>
            parts = address.split('/')
            cc_from_path = None
            for i, part in enumerate(parts):
                if part.lower() == 'cc' and i + 2 < len(parts):
                    # /midi/raw/cc/1/33 - CC number is 2 positions after 'cc'
                    try:
                        cc_from_path = int(parts[i + 2])
                    except ValueError:
                        pass
                    break
                elif part.lower() == 'cc' and i + 1 < len(parts):
                    # /midi/cc/33 - CC number is 1 position after 'cc'
                    try:
                        cc_from_path = int(parts[i + 1])
                    except ValueError:
                        pass
                    break

            if cc_from_path is not None and len(args) >= 1:
                # CC number from path, value from args
                try:
                    cc_val = float(args[0])
                    incoming_cc = (cc_from_path, cc_val)
                    self.last_cc = incoming_cc
                except (ValueError, IndexError):
                    pass
            elif len(args) >= 3:
                # Format: /midi/cc <channel> <cc_number> <value> (3 args)
                try:
                    cc_num = int(args[1])
                    cc_val = float(args[2])
                    incoming_cc = (cc_num, cc_val)
                    self.last_cc = incoming_cc
                except (ValueError, IndexError):
                    pass
            elif len(args) == 2:
                # Format: /midi/cc <cc_number> <value> (2 args)
                try:
                    cc_num = int(args[0])
                    cc_val = float(args[1])
                    incoming_cc = (cc_num, cc_val)
                    self.last_cc = incoming_cc
                except (ValueError, IndexError):
                    pass

        # Apply learned CC mappings only for the CC we just received
        if incoming_cc and self.app_state:
            self._apply_cc_mapping(incoming_cc[0], incoming_cc[1])

    def _apply_cc_mapping(self, cc_num: int, cc_val: float):
        """Apply incoming CC value to any mapped parameters."""
        if not self.app_state:
            return

        # Find any parameters mapped to this specific CC number
        for param_path, mapped_cc in self.cc_mappings.items():
            if mapped_cc == cc_num:
                # Apply CC value (0-127) to parameter
                self._set_param_from_cc(param_path, cc_val)

    def _set_param_from_cc(self, param_path: str, cc_val: float):
        """Set a parameter value from CC (0-127 normalized to param range)."""
        if not self.app_state or not self.param_mode:
            return

        # Normalize CC value (0-127 -> 0.0-1.0)
        normalized = cc_val / 127.0

        # Use param_mode's parameter tree to get node info (ranges, setter)
        node = self.param_mode._find_node(param_path)
        if node is None or not node.is_leaf():
            return

        try:
            # Calculate value from normalized position using node's range
            min_val, max_val = node.min_val, node.max_val
            new_val = min_val + normalized * (max_val - min_val)

            # Use node's setter to apply the value
            if node.setter:
                node.setter(self.app_state, new_val)
                self._update_slider_if_active(param_path, normalized)
                # Trigger redraw
                if hasattr(self.app_state, 'features'):
                    self.app_state.features.needs_redraw = True
        except Exception:
            pass  # Silent fail for invalid mappings

    def _update_slider_if_active(self, param_path: str, normalized: float):
        """Update param_mode slider if it's showing this parameter."""
        if not self.param_mode:
            return
        # Check if param_mode is in slider mode showing this parameter
        from tui_py.rendering.param_mode import ParamModeState
        if (self.param_mode.state == ParamModeState.SLIDER and
            self.param_mode.current_path == param_path):
            self.param_mode.slider_value = normalized

    def set_param_mode(self, param_mode):
        """Set reference to param_mode for slider updates."""
        self.param_mode = param_mode

    def learn_cc(self, param_path: str) -> str:
        """
        Learn the most recent CC for a parameter.

        Args:
            param_path: Parameter path like "kernel.tau_a"

        Returns:
            Status message
        """
        if not self.last_cc:
            return f"No CC received yet. Move a knob/fader then try again."

        cc_num, cc_val = self.last_cc
        self.cc_mappings[param_path] = cc_num
        return f"Learned CC{cc_num} -> {param_path}"

    def unlearn_cc(self, param_path: str) -> str:
        """Remove CC mapping for a parameter."""
        if param_path in self.cc_mappings:
            cc_num = self.cc_mappings.pop(param_path)
            return f"Removed CC{cc_num} mapping from {param_path}"
        return f"No CC mapping for {param_path}"

    def get_cc_mapping(self, param_path: str) -> int:
        """Get CC number mapped to a parameter, or None."""
        return self.cc_mappings.get(param_path)

    def list_cc_mappings(self) -> str:
        """List all CC mappings."""
        if not self.cc_mappings:
            return "No CC mappings. Hold Return in slider mode to learn."
        lines = ["CC Mappings:"]
        for path, cc_num in sorted(self.cc_mappings.items()):
            lines.append(f"  CC{cc_num} -> {path}")
        return "\n".join(lines)

    def clear_cc_mappings(self) -> str:
        """Clear all CC mappings."""
        count = len(self.cc_mappings)
        self.cc_mappings.clear()
        return f"Cleared {count} CC mapping(s)"

    def start(self) -> str:
        """Start OSC multicast listener on 239.1.1.1:1983."""
        if not self.osc_available:
            return "OSC unavailable - install python-osc: pip install python-osc"

        if self.enabled:
            return f"OSC already listening on {self.multicast}:{self.port}"

        try:
            import threading
            import socket
            import struct

            # Create UDP socket for multicast
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # SO_REUSEPORT not available on all platforms

            # Bind to all interfaces on the port
            self.socket.bind(('', self.port))

            # Join multicast group
            mreq = struct.pack('4sl', socket.inet_aton(self.multicast), socket.INADDR_ANY)
            self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            self.enabled = True

            # Start listener thread
            def listen_loop():
                while self.enabled:
                    try:
                        self.socket.settimeout(0.5)
                        data, addr = self.socket.recvfrom(4096)
                        self._handle_osc_packet(data)
                    except socket.timeout:
                        continue
                    except Exception:
                        if self.enabled:
                            continue
                        break

            self.server_thread = threading.Thread(target=listen_loop, daemon=True)
            self.server_thread.start()

            return f"OSC listening on multicast {self.multicast}:{self.port}"

        except OSError as e:
            self.enabled = False
            return f"OSC start failed: {e}"
        except Exception as e:
            self.enabled = False
            return f"OSC start failed: {e}"

    def _handle_osc_packet(self, data: bytes):
        """Parse and handle OSC packet."""
        try:
            from pythonosc.osc_message import OscMessage
            msg = OscMessage(data)
            self._osc_handler(msg.address, *msg.params)
        except Exception:
            # Try to parse as bundle or skip malformed packets
            pass

    def stop(self) -> str:
        """Stop OSC listener."""
        if not self.enabled:
            return "OSC not running"

        self.enabled = False

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        self.server_thread = None
        return "OSC listener stopped"

    def get_status(self) -> str:
        """Get OSC status info."""
        lines = []
        if not self.osc_available:
            lines.append("OSC: unavailable (pip install python-osc)")
        elif self.enabled:
            lines.append(f"OSC: listening on {self.host}:{self.port}")
            lines.append(f"Monitor: {'on' if self.monitoring else 'off'}")
            lines.append(f"Messages: {len(self.message_log)}")
        else:
            lines.append("OSC: off")
        return "\n".join(lines)

    def toggle_monitor(self) -> str:
        """Toggle monitoring mode."""
        self.monitoring = not self.monitoring
        status = "on" if self.monitoring else "off"
        return f"OSC monitor: {status}"

    def set_config(self, key: str, value: str) -> str:
        """Set OSC configuration."""
        if self.enabled:
            return "Stop OSC first (osc off) before changing config"

        if key == "multicast":
            self.multicast = value
            return f"OSC multicast: {self.multicast}"
        elif key == "port":
            try:
                self.port = int(value)
                return f"OSC port: {self.port}"
            except ValueError:
                return f"Invalid port: {value}"
        elif key == "host":
            self.host = value
            return f"OSC host: {self.host}"
        else:
            return f"Unknown config key: {key}. Try: multicast, port, host"

    def get_config(self) -> str:
        """Get current OSC configuration."""
        lines = [
            "OSC Configuration:",
            f"  multicast: {self.multicast}",
            f"  port: {self.port}",
            f"  host: {self.host}",
        ]
        return "\n".join(lines)

    def get_recent_messages(self, count: int = 10) -> str:
        """Get recent OSC messages."""
        if not self.message_log:
            return "No OSC messages received"

        recent = self.message_log[-count:]
        return "\n".join(recent)

    def send_message(self, address: str, *args) -> str:
        """Send an OSC message."""
        if not self.osc_available:
            return "OSC unavailable"

        try:
            from pythonosc import udp_client
            client = udp_client.SimpleUDPClient("127.0.0.1", self.port)

            # Parse args to appropriate types
            parsed_args = []
            for arg in args:
                try:
                    if '.' in str(arg):
                        parsed_args.append(float(arg))
                    else:
                        parsed_args.append(int(arg))
                except ValueError:
                    parsed_args.append(str(arg))

            client.send_message(address, parsed_args)
            return f"Sent: {address} {' '.join(str(a) for a in parsed_args)}"
        except Exception as e:
            return f"Send failed: {e}"


# Global OSC state instance
_osc_state = None

def get_osc_state() -> OSCState:
    """Get the global OSC state instance."""
    global _osc_state
    if _osc_state is None:
        _osc_state = OSCState()
    return _osc_state


def register_osc_commands(app_state):
    """Register OSC commands."""

    osc = get_osc_state()
    osc.set_app_state(app_state)

    # ========== OSC COMMANDS ==========

    def osc_cmd(action: str = "status", *args) -> str:
        """Main OSC command handler."""
        action = action.lower()

        if action in ("on", "start", "enable"):
            return osc.start()
        elif action in ("off", "stop", "disable"):
            return osc.stop()
        elif action == "status":
            return osc.get_status()
        elif action in ("monitor", "mon"):
            return osc.toggle_monitor()
        elif action == "log":
            count = int(args[0]) if args else 10
            return osc.get_recent_messages(count)
        elif action == "send":
            if len(args) < 1:
                return "Usage: osc send <address> [args...]"
            return osc.send_message(args[0], *args[1:])
        elif action == "list":
            return _list_osc_addresses()
        elif action in ("config", "cfg"):
            if len(args) >= 2:
                return osc.set_config(args[0], args[1])
            else:
                return osc.get_config()
        else:
            return f"Unknown action: {action}. Try: on, off, status, monitor, log, send, list, config"

    registry.register(CommandDef(
        name="osc",
        category=CommandCategory.SYSTEM,
        description_short="OSC multicast listener (239.1.1.1:1983)",
        description_long="Control OSC: osc on|off|status|monitor|log|send|list|config",
        params=[
            CommandParam("action", ParamType.STRING, "Action: on/off/status/monitor/log/send/list/config",
                        default="status",
                        completions=["on", "off", "status", "monitor", "log", "send", "list", "config"]),
        ],
        handler=lambda action="status", *args: osc_cmd(action, *args)
    ))

    # Convenience aliases
    registry.register(CommandDef(
        name="osc_on",
        category=CommandCategory.SYSTEM,
        description_short="Start OSC server on UDP port 1983",
        handler=lambda: osc.start()
    ))

    registry.register(CommandDef(
        name="osc_off",
        category=CommandCategory.SYSTEM,
        description_short="Stop OSC server",
        handler=lambda: osc.stop()
    ))

    registry.register(CommandDef(
        name="osc_monitor",
        category=CommandCategory.SYSTEM,
        description_short="Toggle OSC message monitoring",
        aliases=["osc_mon"],
        handler=lambda: osc.toggle_monitor()
    ))

    registry.register(CommandDef(
        name="osc_status",
        category=CommandCategory.SYSTEM,
        description_short="Show OSC server status",
        handler=lambda: osc.get_status()
    ))

    registry.register(CommandDef(
        name="osc_log",
        category=CommandCategory.SYSTEM,
        description_short="Show recent OSC messages",
        params=[
            CommandParam("count", ParamType.INT, "Number of messages to show", default=10)
        ],
        handler=lambda count=10: osc.get_recent_messages(count)
    ))

    registry.register(CommandDef(
        name="osc_send",
        category=CommandCategory.SYSTEM,
        description_short="Send an OSC message",
        params=[
            CommandParam("address", ParamType.STRING, "OSC address (e.g., /tau/play)"),
            CommandParam("value", ParamType.STRING, "Value to send", default=""),
        ],
        handler=lambda address, value="": osc.send_message(address, value) if value else osc.send_message(address)
    ))

    registry.register(CommandDef(
        name="osc_list",
        category=CommandCategory.SYSTEM,
        description_short="List available OSC addresses",
        handler=lambda: _list_osc_addresses()
    ))

    registry.register(CommandDef(
        name="osc_config",
        category=CommandCategory.SYSTEM,
        description_short="Get/set OSC configuration",
        aliases=["osc_cfg"],
        params=[
            CommandParam("key", ParamType.STRING, "Config key: multicast, port, host", default="",
                        completions=["multicast", "port", "host"]),
            CommandParam("value", ParamType.STRING, "New value", default=""),
        ],
        handler=lambda key="", value="": osc.set_config(key, value) if key and value else osc.get_config()
    ))

    # MIDI CC Learn commands
    registry.register(CommandDef(
        name="cc_learn",
        category=CommandCategory.SYSTEM,
        description_short="Learn MIDI CC for a parameter",
        description_long="Maps the most recent CC to a parameter. Use \\param in slider mode + hold Return.",
        params=[
            CommandParam("param", ParamType.STRING, "Parameter path (e.g., kernel.tau_a)",
                        completions=["kernel.tau_a", "kernel.tau_r", "kernel.threshold",
                                   "kernel.refractory", "transport.span"]),
        ],
        handler=lambda param: osc.learn_cc(param)
    ))

    registry.register(CommandDef(
        name="cc_unlearn",
        category=CommandCategory.SYSTEM,
        description_short="Remove MIDI CC mapping for a parameter",
        params=[
            CommandParam("param", ParamType.STRING, "Parameter path to unmap"),
        ],
        handler=lambda param: osc.unlearn_cc(param)
    ))

    registry.register(CommandDef(
        name="cc_list",
        category=CommandCategory.SYSTEM,
        description_short="List all MIDI CC mappings",
        aliases=["cc_mappings"],
        handler=lambda: osc.list_cc_mappings()
    ))

    registry.register(CommandDef(
        name="cc_last",
        category=CommandCategory.SYSTEM,
        description_short="Show last received MIDI CC",
        handler=lambda: f"Last CC: CC{osc.last_cc[0]}={osc.last_cc[1]}" if osc.last_cc else "No CC received yet"
    ))

    registry.register(CommandDef(
        name="cc_clear",
        category=CommandCategory.SYSTEM,
        description_short="Clear all MIDI CC mappings",
        handler=lambda: osc.clear_cc_mappings()
    ))


def _list_osc_addresses() -> str:
    """List registered OSC addresses."""
    lines = [
        "OSC Address Scheme (UDP 1983):",
        "",
        "Transport:",
        "  /tau/transport/play      - Start playback",
        "  /tau/transport/pause     - Pause playback",
        "  /tau/transport/toggle    - Toggle play/pause",
        "  /tau/transport/position  - Set position (float seconds)",
        "  /tau/transport/span      - Set zoom span (float seconds)",
        "",
        "Parameters:",
        "  /tau/params/tau_a        - Attack time constant",
        "  /tau/params/tau_r        - Release time constant",
        "  /tau/params/threshold    - Threshold in sigma",
        "  /tau/params/refractory   - Refractory period",
        "",
        "Lanes:",
        "  /tau/lanes/N/visible     - Lane N visibility (0/1)",
        "  /tau/lanes/N/gain        - Lane N gain (float)",
        "",
        "State updates sent from tau:",
        "  /tau/state/position      - Current position",
        "  /tau/state/playing       - Playing status (0/1)",
    ]
    return "\n".join(lines)
