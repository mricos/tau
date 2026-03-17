"""PlayerApp: curses-based media player with adaptive layout."""

import curses
import sys
from pathlib import Path

from tui_py.rendering.helpers import (
    safe_addstr, draw_progress_bar, draw_box, truncate_middle, format_time,
    init_colors,
)
from player_py.scanner import scan_directory
from player_py.playlist import Playlist, SortMode
from player_py.transport import PlayerTransport
from player_py.analysis import AnalysisScreen


class PlayerApp:
    def __init__(self, directory: Path):
        self.directory = directory.expanduser().resolve()
        self.transport = PlayerTransport()
        self.playlist = Playlist()
        self.browser_cursor: int = 0
        self.browser_scroll: int = 0
        self.split_ratio: float = 0.35
        self.running = True
        self.analysis = AnalysisScreen()
        self.show_analysis: bool = False

    def scan(self):
        files = scan_directory(self.directory)
        self.playlist = Playlist(files)

    def load_current(self):
        track = self.playlist.current()
        if track:
            self.transport.load(track.path)

    def play_current(self):
        self.load_current()
        self.transport.play()

    # ── Key bindings ──

    def _action_quit(self):
        self.running = False

    def _action_toggle(self):
        if self.transport.has_track:
            self.transport.toggle()
        else:
            self.play_current()

    def _action_next(self):
        if self.playlist.next():
            self.play_current()

    def _action_prev(self):
        if self.playlist.prev():
            self.play_current()

    def _action_stop(self):
        self.transport.stop()

    def _action_seek_fwd(self):
        self.transport.seek_relative(5.0)

    def _action_seek_back(self):
        self.transport.seek_relative(-5.0)

    def _action_cursor_up(self):
        self.browser_cursor = max(0, self.browser_cursor - 1)

    def _action_cursor_down(self):
        self.browser_cursor = min(len(self.playlist.tracks) - 1, self.browser_cursor + 1)

    def _action_select(self):
        self.playlist.select(self.browser_cursor)
        self.play_current()

    def _action_cycle_repeat(self):
        self.playlist.cycle_repeat()

    def _action_vol_up(self):
        self.transport.set_volume(self.transport.volume + 0.05)

    def _action_vol_down(self):
        self.transport.set_volume(self.transport.volume - 0.05)

    def _action_widen_list(self):
        self.split_ratio = min(0.8, self.split_ratio + 0.05)

    def _action_narrow_list(self):
        self.split_ratio = max(0.15, self.split_ratio - 0.05)

    def _action_toggle_analysis(self):
        track = self.playlist.current()
        if track and track.vox_id:
            self.show_analysis = not self.show_analysis
            if self.show_analysis:
                self.analysis.load(track.path, track.vox_id, track.vox_voice)

    def _action_export_training(self):
        if self.show_analysis and self.analysis.bundle:
            out = self.analysis.handle_export(self.directory)
            # Briefly flash exported path — visible next render cycle
            self._export_msg = out if out else "No data to export"

    def _action_filter_annotated(self):
        self.playlist.filter_annotated()
        self.browser_cursor = 0

    def _action_cycle_sort(self):
        current = self.playlist.current()
        self.playlist.cycle_sort()
        if current:
            for i, t in enumerate(self.playlist.tracks):
                if t.path == current.path:
                    self.browser_cursor = i
                    self.playlist.current_index = i
                    break

    _KEYMAP: dict  # populated after class body

    def _handle_key(self, key: int):
        action = self._KEYMAP.get(key)
        if action:
            action(self)

    # ── Main loop ──

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
            elif self.show_analysis:
                self._render_with_analysis(scr, h, w)
            else:
                self._render_standard(scr, h, w)

            scr.refresh()

            if self.transport.update():
                if self.playlist.next():
                    self.play_current()

            key = scr.getch()
            if key != -1:
                self._handle_key(key)

    # ── Mini Mode (< 40 cols or < 10 rows) ──

    def _render_mini(self, scr, h: int, w: int):
        track = self.playlist.current()
        name = track.display_label if track else "(no tracks)"

        row = 0
        safe_addstr(scr, row, 0, truncate_middle(name, w), curses.A_BOLD)
        row += 1

        pos_str = format_time(self.transport.position)
        dur_str = format_time(self.transport.duration) if self.transport.duration > 0 else "?:??"
        safe_addstr(scr, row, 0, f"{pos_str} / {dur_str}"[:w])
        row += 1

        if row < h:
            draw_progress_bar(scr, row, 0, min(w, 40), self.transport.progress)
            row += 1

        if row < h:
            play_ch = "||" if self.transport.playing else ">>"
            rep = self.playlist.repeat.value
            safe_addstr(scr, row, 0, f"|<  {play_ch}  >|  []  r:{rep}  [{self.transport.backend}]"[:w])

    # ── Analysis Mode ──

    def _render_with_analysis(self, scr, h: int, w: int):
        # Left: file browser (narrow), Right: analysis (wide)
        list_w = max(20, min(int(w * 0.25), 40))
        panel_w = w - list_w

        sort_label = f"Files [{self.playlist.sort.value}]"
        draw_box(scr, 0, 0, h, list_w, sort_label)
        self._render_browser(scr, h, list_w)

        # Update cursor time from transport
        self.analysis.set_cursor(self.transport.position)
        self.analysis.render(scr, 0, list_w, h, panel_w)

    # ── Standard Mode (>= 40 cols, >= 10 rows) ──

    def _render_standard(self, scr, h: int, w: int):
        list_w = max(20, min(w - 20, int(w * self.split_ratio)))
        panel_w = w - list_w

        sort_label = f"Files [{self.playlist.sort.value}]"
        draw_box(scr, 0, 0, h, list_w, sort_label)
        self._render_browser(scr, h, list_w)

        draw_box(scr, 0, list_w, h, panel_w, "Now Playing")
        self._render_now_playing(scr, h, list_w, panel_w)

    def _render_browser(self, scr, h: int, list_w: int):
        max_lines = h - 2
        tracks = self.playlist.tracks

        if self.browser_cursor < self.browser_scroll:
            self.browser_scroll = self.browser_cursor
        if self.browser_cursor >= self.browser_scroll + max_lines:
            self.browser_scroll = self.browser_cursor - max_lines + 1

        inner_w = list_w - 3
        for i in range(max_lines):
            idx = self.browser_scroll + i
            if idx >= len(tracks):
                break

            t = tracks[idx]
            prefix = " * " if idx == self.playlist.current_index else "   "
            flags = f" [{t.vox_flags}]" if t.vox_flags else ""
            label = t.display_label + flags
            line = prefix + truncate_middle(label, max(1, inner_w - len(prefix)))

            attr = curses.A_NORMAL
            if idx == self.browser_cursor:
                attr = curses.A_REVERSE
            if idx == self.playlist.current_index:
                attr |= curses.A_BOLD

            safe_addstr(scr, 1 + i, 1, line[:inner_w], attr)

    def _render_now_playing(self, scr, h: int, x: int, panel_w: int):
        ix = x + 2
        iw = panel_w - 4
        track = self.playlist.current()

        row = 2
        if track:
            safe_addstr(scr, row, ix, truncate_middle(track.display_label, iw), curses.A_BOLD)
            row += 1
            # Metadata line: artist - album (if available)
            meta_parts = []
            if track.artist:
                meta_parts.append(track.artist)
            if track.album:
                meta_parts.append(track.album)
            if meta_parts:
                safe_addstr(scr, row, ix, truncate_middle(" / ".join(meta_parts), iw), curses.A_DIM)
            row += 1
        else:
            safe_addstr(scr, row, ix, "(no tracks)")
            row += 1

        row += 1
        if row < h - 3:
            draw_progress_bar(scr, row, ix, min(iw, 40), self.transport.progress)
            row += 1
        if row < h - 2:
            pos_str = format_time(self.transport.position)
            dur_str = format_time(self.transport.duration) if self.transport.duration > 0 else "?:??"
            safe_addstr(scr, row, ix, f"{pos_str} / {dur_str}")
            row += 1
        if row < h - 2:
            safe_addstr(scr, row, ix, f"vol: {int(self.transport.volume * 100)}%")
            row += 1

        row += 1
        if row < h - 1:
            play_ch = ">||" if self.transport.playing else " >> "
            rep = self.playlist.repeat.value
            safe_addstr(scr, row, ix, f"|<   {play_ch}   >|   []   r:{rep}"[:iw])

        if row + 2 < h - 1:
            idx = self.playlist.current_index + 1
            total = len(self.playlist.tracks)
            status = f"Track {idx}/{total}  [{self.transport.backend}]  </>:resize  o:sort"
            safe_addstr(scr, h - 2, ix, status[:iw], curses.A_DIM)


# Keymap: key code -> unbound method
# Defined outside class body so curses constants are resolved at import time.
PlayerApp._KEYMAP = {
    ord('q'):           PlayerApp._action_quit,
    ord(' '):           PlayerApp._action_toggle,
    ord('n'):           PlayerApp._action_next,
    ord('p'):           PlayerApp._action_prev,
    ord('s'):           PlayerApp._action_stop,
    curses.KEY_RIGHT:   PlayerApp._action_seek_fwd,
    ord('l'):           PlayerApp._action_seek_fwd,
    curses.KEY_LEFT:    PlayerApp._action_seek_back,
    ord('h'):           PlayerApp._action_seek_back,
    curses.KEY_UP:      PlayerApp._action_cursor_up,
    ord('k'):           PlayerApp._action_cursor_up,
    curses.KEY_DOWN:    PlayerApp._action_cursor_down,
    ord('j'):           PlayerApp._action_cursor_down,
    curses.KEY_ENTER:   PlayerApp._action_select,
    ord('\n'):          PlayerApp._action_select,
    10:                 PlayerApp._action_select,
    ord('r'):           PlayerApp._action_cycle_repeat,
    ord('+'):           PlayerApp._action_vol_up,
    ord('='):           PlayerApp._action_vol_up,
    ord('-'):           PlayerApp._action_vol_down,
    ord('>'):           PlayerApp._action_widen_list,
    ord('.'):           PlayerApp._action_widen_list,
    ord('<'):           PlayerApp._action_narrow_list,
    ord(','):           PlayerApp._action_narrow_list,
    ord('o'):           PlayerApp._action_cycle_sort,
    ord('a'):           PlayerApp._action_toggle_analysis,
    ord('e'):           PlayerApp._action_export_training,
    ord('A'):           PlayerApp._action_filter_annotated,
}


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
