#!/usr/bin/env python3
"""
tau - REPL for tau-engine audio daemon

Interactive command-line interface for controlling tau-engine.
Provides readline support, command completion, and real-time feedback.

Usage:
    tau                    # Start REPL (auto-starts tau-engine if needed)
    tau -c "SAMPLE 1 LOAD audio.wav"  # Execute command and exit
    tau -s script.tau      # Run script file
"""

import os
import sys
import socket
import subprocess
import time
import atexit
import readline
from pathlib import Path
from typing import Optional, List


class TauREPL:
    """Interactive REPL for tau-engine."""

    def __init__(self, socket_path: str = "~/tau/runtime/tau.sock", auto_start: bool = True):
        """
        Initialize tau REPL.

        Args:
            socket_path: Path to tau Unix socket
            auto_start: Auto-start tau-engine if not running
        """
        self.socket_path = Path(socket_path).expanduser()
        self.engine_process: Optional[subprocess.Popen] = None
        self.running = True
        self.history_file = Path("~/.tau_history").expanduser()

        # Command categories for completion
        self.commands = {
            'INIT': [],
            'STATUS': [],
            'QUIT': [],
            'MASTER': ['<gain>'],
            'CH': ['<1-4>', 'GAIN', 'PAN', 'FILTER'],
            'SAMPLE': ['<1-16>', 'LOAD', 'TRIG', 'STOP', 'GAIN', 'CHAN', 'LOOP', 'SEEK'],
            'VOICE': ['<1-8>', 'ON', 'OFF', 'WAVE', 'FREQ', 'GAIN', 'CHAN', 'SPIKE', 'TAU'],
            'SUBSCRIBE': ['<socket_path>'],
        }

        # Setup readline completion
        self._setup_completion()

        # Auto-start tau-engine if needed
        if auto_start and not self.check_connection():
            self._start_engine()

    def _setup_completion(self):
        """Setup readline tab completion."""
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self._completer)
        readline.set_completer_delims(' \t\n')

        # Load history
        if self.history_file.exists():
            try:
                readline.read_history_file(str(self.history_file))
            except:
                pass

        # Save history on exit
        atexit.register(self._save_history)

    def _save_history(self):
        """Save command history."""
        try:
            readline.write_history_file(str(self.history_file))
        except:
            pass

    def _completer(self, text: str, state: int) -> Optional[str]:
        """Tab completion function."""
        line = readline.get_line_buffer()
        tokens = line.split()

        # Completing first word (command)
        if not tokens or (len(tokens) == 1 and not line.endswith(' ')):
            matches = [cmd for cmd in self.commands.keys() if cmd.startswith(text.upper())]
        else:
            # Completing arguments
            cmd = tokens[0].upper()
            if cmd in self.commands:
                matches = [arg for arg in self.commands[cmd] if arg.startswith(text.upper())]
            else:
                matches = []

        try:
            return matches[state]
        except IndexError:
            return None

    def _start_engine(self) -> None:
        """Start tau-engine daemon in the background."""
        # Find tau-engine binary
        # Look in: project_root/engine, ~/tau/engine, /usr/local/bin
        project_root = Path(__file__).parent.parent
        engine_paths = [
            project_root / "engine" / "tau-engine",
            Path("~/tau/engine/tau-engine").expanduser(),
            Path("/usr/local/bin/tau-engine"),
        ]

        engine_binary = None
        for path in engine_paths:
            if path.exists():
                engine_binary = path
                break

        if not engine_binary:
            print(f"✗ tau-engine binary not found. Searched:")
            for p in engine_paths:
                print(f"  - {p}")
            print("\nBuild tau-engine first:")
            print("  cd engine && ./build.sh")
            sys.exit(1)

        # Ensure runtime directory exists
        runtime_dir = self.socket_path.parent
        runtime_dir.mkdir(parents=True, exist_ok=True)

        print(f"Starting tau-engine... ", end='', flush=True)

        # Start tau-engine as background daemon
        self.engine_process = subprocess.Popen(
            [str(engine_binary)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # Register cleanup handler
        atexit.register(self._cleanup_engine)

        # Wait for socket to appear (up to 2 seconds)
        for _ in range(20):
            time.sleep(0.1)
            if self.socket_path.exists():
                break

        if not self.socket_path.exists():
            print("✗ failed (socket not created)")
            sys.exit(1)

        # Give engine time to start accepting connections
        time.sleep(0.2)
        print("✓")

    def _cleanup_engine(self) -> None:
        """Clean up auto-started tau-engine process."""
        if self.engine_process:
            try:
                self.engine_process.terminate()
                self.engine_process.wait(timeout=2)
            except:
                pass

    def _send_command(self, cmd: str) -> str:
        """
        Send command to tau-engine and receive response.

        Args:
            cmd: Command string

        Returns:
            Response string from tau-engine

        Raises:
            ConnectionError: If connection fails
        """
        if not self.socket_path.exists():
            raise ConnectionError(f"Tau socket not found: {self.socket_path}")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        client_path = f"/tmp/tau-repl-{os.getpid()}.sock"

        try:
            # Bind to temporary client socket
            sock.bind(client_path)

            # Send command to tau-engine
            sock.sendto(cmd.encode(), str(self.socket_path))

            # Receive response with timeout
            sock.settimeout(1.0)
            response, _ = sock.recvfrom(4096)
            return response.decode().strip()

        except socket.timeout:
            raise ConnectionError(f"Command timed out: {cmd}")
        finally:
            sock.close()
            Path(client_path).unlink(missing_ok=True)

    def check_connection(self) -> bool:
        """Check if tau-engine is running and responding."""
        try:
            result = self._send_command("STATUS")
            return result.startswith("OK")
        except ConnectionError:
            return False

    def execute_command(self, cmd: str) -> None:
        """Execute a single command and print response."""
        cmd = cmd.strip()

        if not cmd:
            return

        # Handle REPL-specific commands
        if cmd.lower() in ('exit', 'quit', 'q'):
            self.running = False
            return

        if cmd.lower() == 'help':
            self.print_help()
            return

        # Send to tau-engine
        try:
            response = self._send_command(cmd)

            # Colorize response
            if response.startswith("OK"):
                print(f"\033[32m{response}\033[0m")  # Green
            elif response.startswith("ERROR"):
                print(f"\033[31m{response}\033[0m")  # Red
            else:
                print(response)

        except ConnectionError as e:
            print(f"\033[31m✗ Connection error: {e}\033[0m")
        except Exception as e:
            print(f"\033[31m✗ Error: {e}\033[0m")

    def print_help(self):
        """Print help message."""
        help_text = """
tau-engine REPL - Interactive audio engine control

COMMANDS:
  STATUS                          Check engine status
  MASTER <gain>                   Set master gain (0.0-10.0)

  CH <1-4> GAIN <gain>           Set channel gain
  CH <1-4> PAN <pan>             Set channel pan (-1.0 to 1.0)
  CH <1-4> FILTER <type> <cutoff> <q>  Set channel filter (type: 0=off, 1=LP, 2=HP, 3=BP)

  SAMPLE <1-16> LOAD <path>      Load audio file to sample slot
  SAMPLE <1-16> TRIG             Trigger sample playback
  SAMPLE <1-16> STOP             Stop sample playback
  SAMPLE <1-16> GAIN <gain>      Set sample gain (0.0-10.0)
  SAMPLE <1-16> CHAN <0-3>       Assign sample to channel
  SAMPLE <1-16> LOOP <0|1>       Enable/disable looping
  SAMPLE <1-16> SEEK <seconds>   Seek to position in seconds

  VOICE <1-8> ON                 Turn voice on
  VOICE <1-8> OFF                Turn voice off
  VOICE <1-8> WAVE <0|1>         Set waveform (0=sine, 1=pulse)
  VOICE <1-8> FREQ <hz>          Set frequency
  VOICE <1-8> GAIN <gain>        Set voice gain (0.0-2.0)
  VOICE <1-8> CHAN <0-3>         Assign voice to channel
  VOICE <1-8> SPIKE              Inject spike to LIF modulator
  VOICE <1-8> TAU <tau_a> <tau_b>  Set LIF time constants

  QUIT                           Shutdown tau-engine

REPL COMMANDS:
  help                           Show this help
  exit, quit, q                  Exit REPL (engine keeps running)

EXAMPLES:
  SAMPLE 1 LOAD ~/audio/kick.wav
  SAMPLE 1 LOOP 1
  SAMPLE 1 TRIG

  VOICE 1 ON
  VOICE 1 FREQ 440
  VOICE 1 GAIN 0.3

  MASTER 0.8

TIP: Use Tab for command completion, Up/Down for history
"""
        print(help_text)

    def run(self):
        """Run interactive REPL loop."""
        # Check connection
        if not self.check_connection():
            print("✗ Cannot connect to tau-engine")
            print(f"  Socket: {self.socket_path}")
            print("\nMake sure tau-engine is running, or allow auto-start.")
            sys.exit(1)

        print(f"\033[1mtau-engine REPL\033[0m")
        print(f"Connected: {self.socket_path}")
        print("Type 'help' for commands, 'exit' to quit\n")

        while self.running:
            try:
                cmd = input("\033[1;36mtau>\033[0m ")
                self.execute_command(cmd)
            except EOFError:
                # Ctrl+D
                print()
                break
            except KeyboardInterrupt:
                # Ctrl+C
                print()
                continue

        print("\nGoodbye! (tau-engine still running)")

    def run_script(self, script_path: Path):
        """Run commands from a script file."""
        if not script_path.exists():
            print(f"✗ Script not found: {script_path}")
            sys.exit(1)

        print(f"Running script: {script_path}")

        with open(script_path) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                print(f"\n[{line_num}] {line}")
                self.execute_command(line)

                # Small delay between commands for stability
                time.sleep(0.01)

    def run_single_command(self, cmd: str):
        """Execute a single command and exit."""
        self.execute_command(cmd)


def main():
    """Entry point for tau REPL."""
    import argparse

    parser = argparse.ArgumentParser(
        description="tau - Interactive REPL for tau-engine audio daemon",
        epilog="Examples:\n"
               "  tau                          # Start REPL\n"
               "  tau -c 'MASTER 0.5'          # Execute command\n"
               "  tau -s script.tau            # Run script\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '-c', '--command',
        help='Execute single command and exit'
    )
    parser.add_argument(
        '-s', '--script',
        type=Path,
        help='Run commands from script file'
    )
    parser.add_argument(
        '--socket',
        default='~/tau/runtime/tau.sock',
        help='Path to tau-engine socket (default: ~/tau/runtime/tau.sock)'
    )
    parser.add_argument(
        '--no-auto-start',
        action='store_true',
        help='Do not auto-start tau-engine if not running'
    )

    args = parser.parse_args()

    # Create REPL
    repl = TauREPL(
        socket_path=args.socket,
        auto_start=not args.no_auto_start
    )

    # Execute based on mode
    if args.command:
        # Single command mode
        repl.run_single_command(args.command)
    elif args.script:
        # Script mode
        repl.run_script(args.script)
    else:
        # Interactive REPL mode
        repl.run()


if __name__ == "__main__":
    main()
