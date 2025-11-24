"""
Entry point for running tau as a module: python -m tau

Usage:
    tau                    # Start REPL (default)
    tau -tui [audio.wav]   # Start TUI workstation
    tau --tui [audio.wav]  # Same as above
    tau -c "SAMPLE 1 LOAD audio.wav"  # Execute command
    tau -s script.tau      # Run script
"""

import sys


def main():
    """
    Dispatch to REPL or TUI based on arguments.

    Default: REPL for direct tau-engine control
    With -tui/--tui: Full TUI workstation
    """
    # Check if TUI mode requested
    if len(sys.argv) > 1 and sys.argv[1] in ('-tui', '--tui'):
        # Remove -tui flag and launch TUI
        sys.argv.pop(1)
        from .main import main as tui_main
        tui_main()
    else:
        # Default: Launch REPL
        from .repl import main as repl_main
        repl_main()


if __name__ == "__main__":
    main()
