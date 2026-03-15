"""PlayerApp: curses-based media player with adaptive layout."""

import curses
import sys
from pathlib import Path

from tui_py.rendering.helpers import (
    safe_addstr, draw_progress_bar, draw_box, truncate_middle, format_time,
    init_colors,
)
from player_py.scanner import scan_directory, group_by_directory, MediaFile
from player_py.playlist import Playlist, RepeatMode
from player_py.transport import PlayerTransport


class PlayerApp:
    def __init__(self, directory: Path):
        self.directory = directory.expanduser().resolve()
        self.transport = PlayerTransport()
        self.playlist = Playlist()
        self.browser_cursor: int = 0
        self.browser_scroll: int = 0
        self.running = True

    def scan(self):
        files = scan_directory(self.directory)
        self.playlist = Playlist(files)
        self.groups = group_by_directory(files)

    def load_current(self):
        track = self.playlist.current()
        if track:
            self.transport.load(track.path)

    def play_current(self):
        self.load_current()
        self.transport.play()

    def run(self, scr):
        scr.timeout(50)
        curses.curs_set(0)
        init_colors()

        self.scan()
        if not self.playlist.empty:
            self.browser_cursor = 0

        while self.running:
            h, w = scr.getmaxyx()
            scr.erase()

            if w < 40 or h < 10:
                self._render_mini(scr, h, w)
            elif w >= 120:
                self._render_standard(scr, h, w, wide=True)
            else:
                self._render_standard(scr, h, w)

            scr.refresh()

            # Update transport
            if self.transport.update():
                # Track ended — auto-advance
                nxt = self.playlist.next()
                if nxt:
                    self.play_current()

            key = scr.getch()
            if key == -1:
                continue
            self._handle_key(key, h)

    def _handle_key(self, key: int, h: int):
        if key == ord('q'):
            self.running = False
        elif key == ord(' '):
            if self.transport.has_track:
                self.transport.toggle()
            else:
                self.play_current()
        elif key == ord('n'):
            trk = self.playlist.next()
            if trk:
                self.play_current()
        elif key == ord('p'):
            trk = self.playlist.prev()
            if trk:
                self.play_current()
        elif key == ord('s'):
            self.transport.stop()
        elif key in (curses.KEY_RIGHT, ord('l')):
            self.transport.seek_relative(5.0)
        elif key in (curses.KEY_LEFT, ord('h')):
            self.transport.seek_relative(-5.0)
        elif key in (curses.KEY_UP, ord('k')):
            self.browser_cursor = max(0, self.browser_cursor - 1)
        elif key in (curses.KEY_DOWN, ord('j')):
            self.browser_cursor = min(len(self.playlist.tracks) - 1, self.browser_cursor + 1)
        elif key in (curses.KEY_ENTER, ord('\n'), 10):
            self.playlist.select(self.browser_cursor)
            self.play_current()
        elif key == ord('r'):
            self.playlist.cycle_repeat()
        elif key == ord('+') or key == ord('='):
            self.transport.set_volume(self.transport.volume + 0.05)
        elif key == ord('-'):
            self.transport.set_volume(self.transport.volume - 0.05)

    # ── Mini Mode (< 40 cols or < 10 rows) ──

    def _render_mini(self, scr, h: int, w: int):
        track = self.playlist.current()
        name = track.name if track else "(no tracks)"
        parent = track.parent_dir + '/' if track and track.parent_dir else ""

        row = 0
        safe_addstr(scr, row, 0, truncate_middle(name, w), curses.A_BOLD)
        row += 1
        if parent:
            safe_addstr(scr, row, 0, truncate_middle(parent, w), curses.A_DIM)
        row += 1

        # Time
        pos_str = format_time(self.transport.position)
        dur_str = format_time(self.transport.duration) if self.transport.duration > 0 else "?:??"
        time_str = f"{pos_str} / {dur_str}"
        safe_addstr(scr, row, 0, time_str[:w])
        row += 1

        # Progress bar
        if row < h:
            bar_w = min(w, 40)
            draw_progress_bar(scr, row, 0, bar_w, self.transport.progress)
            row += 1

        # Transport controls
        if row < h:
            play_ch = "||" if self.transport.playing else ">>"
            rep = self.playlist.repeat.value
            controls = f"|<  {play_ch}  >|  []  r:{rep}  [{self.transport.backend}]"
            safe_addstr(scr, row, 0, controls[:w])

    # ── Standard Mode (>= 40 cols, >= 10 rows) ──

    def _render_standard(self, scr, h: int, w: int, wide: bool = False):
        list_w = max(20, int(w * 0.35))
        panel_w = w - list_w

        # File browser (left panel)
        draw_box(scr, 0, 0, h, list_w, "Files")
        self._render_browser(scr, h, list_w, wide)

        # Now Playing (right panel)
        draw_box(scr, 0, list_w, h, panel_w, "Now Playing")
        self._render_now_playing(scr, h, list_w, panel_w, wide)

    def _render_browser(self, scr, h: int, list_w: int, wide: bool):
        max_lines = h - 2  # inside box
        tracks = self.playlist.tracks

        # Adjust scroll so cursor is visible
        if self.browser_cursor < self.browser_scroll:
            self.browser_scroll = self.browser_cursor
        if self.browser_cursor >= self.browser_scroll + max_lines:
            self.browser_scroll = self.browser_cursor - max_lines + 1

        inner_w = list_w - 3  # box borders + padding
        for i in range(max_lines):
            idx = self.browser_scroll + i
            if idx >= len(tracks):
                break

            t = tracks[idx]
            row = 1 + i

            # Build display line
            prefix = " * " if idx == self.playlist.current_index else "   "
            label = t.name
            if wide and t.parent_dir:
                label = f"{t.parent_dir}/{t.name}"

            line = prefix + truncate_middle(label, max(1, inner_w - len(prefix)))

            attr = curses.A_NORMAL
            if idx == self.browser_cursor:
                attr = curses.A_REVERSE
            if idx == self.playlist.current_index:
                attr |= curses.A_BOLD

            safe_addstr(scr, row, 1, line[:inner_w], attr)

    def _render_now_playing(self, scr, h: int, x: int, panel_w: int, wide: bool):
        inner_x = x + 2
        inner_w = panel_w - 4
        track = self.playlist.current()

        row = 2
        if track:
            safe_addstr(scr, row, inner_x, truncate_middle(track.name, inner_w), curses.A_BOLD)
            row += 1
            if track.parent_dir:
                safe_addstr(scr, row, inner_x, truncate_middle(track.parent_dir + '/', inner_w), curses.A_DIM)
            row += 1
            if wide:
                safe_addstr(scr, row, inner_x, truncate_middle(str(track.path), inner_w), curses.A_DIM)
                row += 1
        else:
            safe_addstr(scr, row, inner_x, "(no tracks)")
            row += 1

        row += 1

        # Progress bar
        if row < h - 3:
            bar_w = min(inner_w, 40)
            draw_progress_bar(scr, row, inner_x, bar_w, self.transport.progress)
            row += 1

        # Time
        if row < h - 2:
            pos_str = format_time(self.transport.position)
            dur_str = format_time(self.transport.duration) if self.transport.duration > 0 else "?:??"
            safe_addstr(scr, row, inner_x, f"{pos_str} / {dur_str}")
            row += 1

        # Volume
        if row < h - 2:
            vol_pct = int(self.transport.volume * 100)
            safe_addstr(scr, row, inner_x, f"vol: {vol_pct}%")
            row += 1

        row += 1

        # Transport controls
        if row < h - 1:
            play_ch = ">||" if self.transport.playing else " >> "
            rep = self.playlist.repeat.value
            controls = f"|<   {play_ch}   >|   []   r:{rep}"
            safe_addstr(scr, row, inner_x, controls[:inner_w])

        # Track info + backend status
        if row + 2 < h - 1:
            idx = self.playlist.current_index + 1
            total = len(self.playlist.tracks)
            status = f"Track {idx}/{total}  [{self.transport.backend}]"
            safe_addstr(scr, h - 2, inner_x, status, curses.A_DIM)


def main():
    if len(sys.argv) > 1:
        directory = Path(sys.argv[1])
    else:
        directory = Path.cwd()

    if not directory.is_dir():
        print(f"Not a directory: {directory}", file=sys.stderr)
        sys.exit(1)

    app = PlayerApp(directory)

    try:
        curses.wrapper(app.run)
    finally:
        app.transport.cleanup()


if __name__ == "__main__":
    main()
