"""Screen renderers: stateless drawing functions for each player view.

Each function takes a curses screen, state objects, and geometry.
PlayerApp owns state and routing; screens just draw.
"""

import curses

from tui_py.rendering.helpers import (
    safe_addstr, draw_progress_bar, draw_box, truncate_middle, format_time,
)
from player_py.playlist import Playlist
from player_py.transport import PlayerTransport


def render_mini(scr, h: int, w: int, playlist: Playlist, transport: PlayerTransport):
    """Minimal view for very small terminals (< 40 cols or < 10 rows)."""
    track = playlist.current()
    name = track.display_label if track else "(no tracks)"

    row = 0
    safe_addstr(scr, row, 0, truncate_middle(name, w), curses.A_BOLD)
    row += 1

    pos_str = format_time(transport.position)
    dur_str = format_time(transport.duration) if transport.duration > 0 else "?:??"
    safe_addstr(scr, row, 0, f"{pos_str} / {dur_str}"[:w])
    row += 1

    if row < h:
        draw_progress_bar(scr, row, 0, min(w, 40), transport.progress)
        row += 1

    if row < h:
        play_ch = "||" if transport.playing else ">>"
        rep = playlist.repeat.value
        safe_addstr(scr, row, 0, f"|<  {play_ch}  >|  []  r:{rep}  [{transport.backend}]"[:w])


def render_browser(scr, h: int, list_w: int,
                   playlist: Playlist, cursor: int, scroll: int) -> int:
    """File browser panel (left side). Returns updated scroll offset."""
    max_lines = h - 2
    tracks = playlist.tracks

    if cursor < scroll:
        scroll = cursor
    if cursor >= scroll + max_lines:
        scroll = cursor - max_lines + 1

    inner_w = list_w - 3
    for i in range(max_lines):
        idx = scroll + i
        if idx >= len(tracks):
            break

        t = tracks[idx]
        prefix = " * " if idx == playlist.current_index else "   "
        flags = f" [{t.vox_flags}]" if t.vox_flags else ""
        label = t.display_label + flags
        line = prefix + truncate_middle(label, max(1, inner_w - len(prefix)))

        attr = curses.A_NORMAL
        if idx == cursor:
            attr = curses.A_REVERSE
        if idx == playlist.current_index:
            attr |= curses.A_BOLD

        safe_addstr(scr, 1 + i, 1, line[:inner_w], attr)

    return scroll


def render_now_playing(scr, h: int, x: int, panel_w: int,
                       playlist: Playlist, transport: PlayerTransport):
    """Now Playing panel (right side in standard mode)."""
    ix = x + 2
    iw = panel_w - 4
    track = playlist.current()

    row = 2
    if track:
        safe_addstr(scr, row, ix, truncate_middle(track.display_label, iw), curses.A_BOLD)
        row += 1
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
        draw_progress_bar(scr, row, ix, min(iw, 40), transport.progress)
        row += 1
    if row < h - 2:
        pos_str = format_time(transport.position)
        dur_str = format_time(transport.duration) if transport.duration > 0 else "?:??"
        safe_addstr(scr, row, ix, f"{pos_str} / {dur_str}")
        row += 1
    if row < h - 2:
        safe_addstr(scr, row, ix, f"vol: {int(transport.volume * 100)}%")
        row += 1

    row += 1
    if row < h - 1:
        play_ch = ">||" if transport.playing else " >> "
        rep = playlist.repeat.value
        safe_addstr(scr, row, ix, f"|<   {play_ch}   >|   []   r:{rep}"[:iw])

    if row + 2 < h - 1:
        idx = playlist.current_index + 1
        total = len(playlist.tracks)
        status = f"Track {idx}/{total}  [{transport.backend}]  </>:resize  o:sort  a:analysis"
        safe_addstr(scr, h - 2, ix, status[:iw], curses.A_DIM)
