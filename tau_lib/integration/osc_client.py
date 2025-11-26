"""
OSC (Open Sound Control) client integration.
Maps all controls to OSC addresses for remote control.

Requires: pip install python-osc

OSC Address Scheme:
  /snn/transport/*   - Playback controls
  /snn/params/*      - Kernel parameters
  /snn/lanes/*       - Lane visibility/expand
  /snn/markers/*     - Marker management
  /snn/display/*     - Display settings
"""

import threading
import time
from typing import Optional, Callable, Dict, Any

try:
    from pythonosc import udp_client, dispatcher, osc_server
    OSC_AVAILABLE = True
except ImportError:
    OSC_AVAILABLE = False
    # OSC support disabled - python-osc not installed


class OSCClient:
    """
    OSC client for sending/receiving control messages.
    """

    def __init__(self, send_host: str = "127.0.0.1", send_port: int = 7400,
                 recv_port: int = 7401):
        """
        Initialize OSC client.

        Args:
            send_host: Host to send OSC messages to
            send_port: Port to send OSC messages to
            recv_port: Port to receive OSC messages on
        """
        if not OSC_AVAILABLE:
            self.enabled = False
            return

        self.enabled = True
        self.send_host = send_host
        self.send_port = send_port
        self.recv_port = recv_port

        # OSC client for sending
        self.client = udp_client.SimpleUDPClient(send_host, send_port)

        # OSC server for receiving
        self.dispatcher = dispatcher.Dispatcher()
        self.server = None
        self.server_thread = None

        # Command handlers
        self.handlers: Dict[str, Callable] = {}

    def send(self, address: str, *args):
        """
        Send OSC message.

        Args:
            address: OSC address (e.g., "/snn/transport/play")
            *args: Arguments to send
        """
        if not self.enabled:
            return

        try:
            self.client.send_message(address, list(args) if args else [])
        except Exception:
            pass  # Silent fail for OSC send errors

    def register_handler(self, address: str, handler: Callable):
        """
        Register handler for incoming OSC messages.

        Args:
            address: OSC address pattern (supports wildcards)
            handler: Function to call with (address, *args)
        """
        if not self.enabled:
            return

        self.handlers[address] = handler
        self.dispatcher.map(address, handler)

    def start_server(self):
        """Start OSC server in background thread."""
        if not self.enabled or self.server:
            return

        try:
            self.server = osc_server.ThreadingOSCUDPServer(
                ("0.0.0.0", self.recv_port), self.dispatcher
            )

            self.server_thread = threading.Thread(
                target=self.server.serve_forever,
                daemon=True
            )
            self.server_thread.start()

        except Exception:
            self.enabled = False

    def stop_server(self):
        """Stop OSC server."""
        if self.server:
            self.server.shutdown()
            self.server = None
            self.server_thread = None

    def send_state_update(self, path: str, value: Any):
        """
        Send state update message.

        Args:
            path: State path (e.g., "transport.position")
            value: State value
        """
        address = f"/snn/state/{path}"
        self.send(address, value)


class OSCMapper:
    """
    Maps application controls to OSC addresses.
    Integrates with CommandTree for automatic mapping.
    """

    def __init__(self, command_tree, app_state):
        """
        Initialize OSC mapper.

        Args:
            command_tree: CommandTree instance
            app_state: Application state
        """
        self.command_tree = command_tree
        self.state = app_state
        self.client = None

    def enable(self, send_host: str = "127.0.0.1", send_port: int = 7400,
               recv_port: int = 7401):
        """
        Enable OSC client with specified configuration.

        Args:
            send_host: Host to send to
            send_port: Port to send to
            recv_port: Port to receive on
        """
        if not OSC_AVAILABLE:
            return False

        self.client = OSCClient(send_host, send_port, recv_port)

        # Register handlers for all commands
        self._register_command_handlers()

        # Start server
        self.client.start_server()

        return True

    def _register_command_handlers(self):
        """Register OSC handlers for all commands in command tree."""
        for cmd in self.command_tree.list_commands(include_hidden=True):
            osc_addr = cmd.get_osc_address()

            def make_handler(command):
                def handler(address, *args):
                    try:
                        result = command.invoke(list(args))
                        # Send response
                        if result is not None:
                            self.client.send(f"{address}/reply", result)
                    except Exception as e:
                        error_msg = str(e)
                        self.client.send(f"{address}/error", error_msg)
                return handler

            self.client.register_handler(osc_addr, make_handler(cmd))

    def send_state_updates(self):
        """Send periodic state updates via OSC."""
        if not self.client or not self.client.enabled:
            return

        # Transport state
        t = self.state.transport
        self.client.send("/snn/state/transport/position", t.position)
        self.client.send("/snn/state/transport/playing", 1 if t.playing else 0)
        self.client.send("/snn/state/transport/span", t.span)

        # Kernel params
        k = self.state.kernel
        self.client.send("/snn/state/params/tau_a", k.tau_a)
        self.client.send("/snn/state/params/tau_r", k.tau_r)
        self.client.send("/snn/state/params/threshold", k.threshold)
        self.client.send("/snn/state/params/refractory", k.refractory)

    def disable(self):
        """Disable OSC client."""
        if self.client:
            self.client.stop_server()
            self.client = None


def create_osc_spec_document(command_tree, output_path: str):
    """
    Create OSC control specification document.

    Args:
        command_tree: CommandTree instance
        output_path: Output file path
    """
    lines = []
    lines.append("# ASCII Scope SNN - OSC Control Specification")
    lines.append("")
    lines.append("This document describes the OSC (Open Sound Control) interface")
    lines.append("for remotely controlling ASCII Scope SNN.")
    lines.append("")
    lines.append("## Connection")
    lines.append("")
    lines.append("- **Send to:** 127.0.0.1:7401 (application)")
    lines.append("- **Receive from:** 127.0.0.1:7400 (application sends state)")
    lines.append("")
    lines.append("## OSC Type Tags")
    lines.append("")
    lines.append("- `f` = float (32-bit)")
    lines.append("- `i` = integer (32-bit)")
    lines.append("- `s` = string")
    lines.append("")

    # Group by category
    for category in command_tree.list_categories():
        commands = command_tree.list_commands(category)
        if not commands:
            continue

        lines.append(f"## {category.upper()} Commands")
        lines.append("")

        for cmd in commands:
            osc_addr = cmd.get_osc_address()
            osc_sig = cmd.get_osc_signature() or "(no arguments)"

            lines.append(f"### {cmd.name}")
            lines.append(f"**Address:** `{osc_addr}`  ")
            lines.append(f"**Type Signature:** `{osc_sig}`  ")
            lines.append(f"**Description:** {cmd.help_short}  ")

            if cmd.params:
                lines.append("")
                lines.append("**Arguments:**")
                for i, p in enumerate(cmd.params, 1):
                    range_info = ""
                    if p.min_val is not None or p.max_val is not None:
                        range_info = f" (range: {p.min_val or '-∞'} to {p.max_val or '∞'})"
                    lines.append(f"{i}. `{p.name}` ({p.type.value}): {p.help}{range_info}")

            if cmd.key_binding:
                lines.append(f"**Keyboard:** {cmd.key_binding}")

            lines.append("")
            lines.append(f"**Example:**")
            if cmd.params:
                example_args = ", ".join(str(p.default or 0) for p in cmd.params)
                lines.append(f"```")
                lines.append(f"{osc_addr} {example_args}")
                lines.append(f"```")
            else:
                lines.append(f"```")
                lines.append(f"{osc_addr}")
                lines.append(f"```")

            lines.append("")

    # State updates section
    lines.append("## State Updates")
    lines.append("")
    lines.append("The application periodically sends state updates:")
    lines.append("")
    lines.append("- `/snn/state/transport/position` (f) - Playhead position in seconds")
    lines.append("- `/snn/state/transport/playing` (i) - 1 if playing, 0 if stopped")
    lines.append("- `/snn/state/transport/span` (f) - Zoom span in seconds")
    lines.append("- `/snn/state/params/tau_a` (f) - Attack time constant")
    lines.append("- `/snn/state/params/tau_r` (f) - Release time constant")
    lines.append("- `/snn/state/params/threshold` (f) - Threshold in sigma")
    lines.append("- `/snn/state/params/refractory` (f) - Refractory period")
    lines.append("")

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"OSC specification written to: {output_path}")
