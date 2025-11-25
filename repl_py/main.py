#!/usr/bin/env python3
"""
tau - Terminal Audio Workstation

Entry point dispatcher:
  tau           → REPL (repl_py)
  tau tui       → TUI workstation (tui_py)
  tau -c CMD    → Execute command
  tau -s FILE   → Run script
"""

import sys


def main():
    """Dispatch to REPL or TUI based on arguments."""
    # Check if TUI mode requested
    if len(sys.argv) > 1 and sys.argv[1] == "tui":
        # Remove 'tui' argument and launch TUI
        sys.argv.pop(1)
        from tui_py.app import main as tui_main
        tui_main()
    else:
        # Default: Launch REPL
        from repl_py.repl import main as repl_main
        repl_main()


if __name__ == "__main__":
    main()
