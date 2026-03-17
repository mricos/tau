#!/usr/bin/env bash
# Build tau-player (C version)
#
# Usage:
#   ./build.sh            # ncurses backend (default)
#   ./build.sh ncurses    # ncurses backend (explicit)
#   ./build.sh ansi       # raw ANSI backend (no deps)

set -e
cd "$(dirname "$0")"

BACKEND="${1:-ncurses}"
CFLAGS="-std=c11 -O2 -Wall -Wextra"
SRC="player.c scanner.c transport.c"

case "$BACKEND" in
    ncurses)
        echo "Building tau-player [ncurses backend]..."
        clang $CFLAGS $SRC tui_ncurses.c -lncurses -o tau-player
        ;;
    ansi)
        echo "Building tau-player [raw ANSI backend]..."
        clang $CFLAGS $SRC tui_ansi.c -o tau-player
        ;;
    *)
        echo "Usage: $0 [ncurses|ansi]" >&2
        exit 1
        ;;
esac

echo "OK: tau-player ($BACKEND)"
ls -lh tau-player
