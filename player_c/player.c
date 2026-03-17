/* player.c - tau-player: terminal media player
 *
 * Usage: tau-player [directory]
 *
 * Keys:
 *   j/k, up/down  - browse files
 *   Enter          - play selected
 *   Space          - play/pause
 *   n/p            - next/prev track
 *   h/l, left/right - seek -/+5s
 *   s              - stop
 *   +/-            - volume
 *   </> or ,/.     - resize panels
 *   o              - cycle sort (path / name)
 *   r              - cycle repeat (none / all / one)
 *   q              - quit
 */

#include "tui.h"
#include "scanner.h"
#include "transport.h"
#include <stdio.h>
#include <string.h>

/* ── Sort / Repeat enums ── */

enum sort_mode  { SORT_PATH, SORT_NAME, SORT_COUNT };
enum repeat_mode { REP_NONE, REP_ALL, REP_ONE, REP_COUNT };

static const char *sort_labels[]   = { "path", "name" };
static const char *repeat_labels[] = { "none", "all", "one" };

/* ── App state ── */

typedef struct {
    media_list_t  files;
    transport_t   transport;
    int           cursor;
    int           scroll;
    int           current;     /* playing track index, -1 if none */
    float         split;       /* left panel ratio */
    int           sort;
    int           repeat;
    int           running;
} player_t;

/* ── Helpers ── */

static void format_time(double secs, char *buf, int buflen) {
    int m = (int)secs / 60;
    int s = (int)secs % 60;
    snprintf(buf, buflen, "%d:%02d", m, s);
}

/* ── Play helpers ── */

static void play_track(player_t *p, int idx) {
    if (idx < 0 || idx >= p->files.count) return;
    p->current = idx;
    transport_load(&p->transport, p->files.files[idx].path);
    transport_play(&p->transport);
}

static void next_track(player_t *p) {
    if (p->files.count == 0) return;
    if (p->repeat == REP_ONE) {
        play_track(p, p->current);
        return;
    }
    int next = p->current + 1;
    if (next >= p->files.count) {
        if (p->repeat == REP_ALL) next = 0;
        else return;
    }
    play_track(p, next);
}

static void prev_track(player_t *p) {
    if (p->files.count == 0) return;
    int prev = p->current - 1;
    if (prev < 0) prev = 0;
    play_track(p, prev);
}

/* ── Rendering ── */

static void render_browser(player_t *p, int h, int list_w) {
    int max_lines = h - 2;
    int inner_w = list_w - 3;
    char buf[512];

    /* Keep cursor in scroll view */
    if (p->cursor < p->scroll)
        p->scroll = p->cursor;
    if (p->cursor >= p->scroll + max_lines)
        p->scroll = p->cursor - max_lines + 1;

    for (int i = 0; i < max_lines; i++) {
        int idx = p->scroll + i;
        if (idx >= p->files.count) break;

        media_file_t *f = &p->files.files[idx];
        const char *marker = (idx == p->current) ? " * " : "   ";

        char label[512];
        tui_truncate_middle(f->name, label, inner_w - 3);
        snprintf(buf, sizeof(buf), "%s%s", marker, label);

        int attr = TUI_NORMAL;
        if (idx == p->cursor)  attr |= TUI_REVERSE;
        if (idx == p->current) attr |= TUI_BOLD;

        /* Highlight playing track with lane1 color */
        if (idx == p->current)
            tui_print_color(1 + i, 1, buf, attr, TUI_COLOR_LANE1, inner_w);
        else
            tui_print(1 + i, 1, buf, attr, inner_w);
    }
}

static void render_now_playing(player_t *p, int h, int x, int panel_w) {
    int ix = x + 2;
    int iw = panel_w - 4;
    char buf[512];
    int row = 2;

    if (p->current >= 0 && p->current < p->files.count) {
        media_file_t *f = &p->files.files[p->current];
        tui_truncate_middle(f->name, buf, iw);
        tui_print_color(row++, ix, buf, TUI_BOLD, TUI_COLOR_LANE1, iw);
        if (f->parent[0]) {
            snprintf(buf, sizeof(buf), "%s/", f->parent);
            tui_print(row, ix, buf, TUI_DIM, iw);
        }
        row++;
    } else {
        tui_print(row++, ix, "(no tracks)", TUI_DIM, iw);
    }

    row++;

    /* Progress bar — green when playing, default when stopped */
    if (row < h - 3) {
        int bar_w = iw < 40 ? iw : 40;
        float pct = 0.0f;
        if (p->transport.duration > 0.0)
            pct = (float)(p->transport.position / p->transport.duration);
        int bar_color = p->transport.playing ? TUI_COLOR_SUCCESS : 0;
        tui_bar_color(row++, ix, bar_w, pct, bar_color);
    }

    /* Time */
    if (row < h - 2) {
        char pos[16], dur[16];
        format_time(p->transport.position, pos, sizeof(pos));
        if (p->transport.duration > 0.0)
            format_time(p->transport.duration, dur, sizeof(dur));
        else
            snprintf(dur, sizeof(dur), "?:??");
        snprintf(buf, sizeof(buf), "%s / %s", pos, dur);
        tui_print(row++, ix, buf, TUI_NORMAL, iw);
    }

    /* Volume */
    if (row < h - 2) {
        snprintf(buf, sizeof(buf), "vol: %d%%", (int)(p->transport.volume * 100));
        tui_print(row++, ix, buf, TUI_NORMAL, iw);
    }

    row++;

    /* Transport controls */
    if (row < h - 1) {
        const char *play_ch = p->transport.playing ? ">||" : " >> ";
        snprintf(buf, sizeof(buf), "|<   %s   >|   []   r:%s",
                 play_ch, repeat_labels[p->repeat]);
        tui_print(row, ix, buf, TUI_NORMAL, iw);
    }

    /* Status line */
    if (row + 2 < h - 1) {
        snprintf(buf, sizeof(buf), "Track %d/%d  [%s]  </>:resize  o:sort",
                 p->current + 1, p->files.count, p->transport.backend);
        tui_print_color(h - 2, ix, buf, TUI_DIM, TUI_COLOR_INFO, iw);
    }
}

static void render(player_t *p) {
    int h, w;
    tui_size(&h, &w);
    tui_clear();

    if (w < 40 || h < 10) {
        /* Mini mode */
        if (p->current >= 0 && p->current < p->files.count) {
            char buf[256];
            tui_truncate_middle(p->files.files[p->current].name, buf, w);
            tui_print_color(0, 0, buf, TUI_BOLD, TUI_COLOR_LANE1, w);
            char pos[16], dur[16];
            format_time(p->transport.position, pos, sizeof(pos));
            format_time(p->transport.duration, dur, sizeof(dur));
            snprintf(buf, sizeof(buf), "%s / %s", pos, dur);
            tui_print(1, 0, buf, TUI_NORMAL, w);
            tui_bar_color(2, 0, w < 40 ? w : 40,
                    p->transport.duration > 0
                    ? (float)(p->transport.position / p->transport.duration) : 0.0f,
                    TUI_COLOR_SUCCESS);
        } else {
            tui_print(0, 0, "(no tracks)", TUI_NORMAL, w);
        }
    } else {
        /* Standard two-panel layout */
        int list_w = (int)(w * p->split);
        if (list_w < 20) list_w = 20;
        if (list_w > w - 20) list_w = w - 20;
        int panel_w = w - list_w;

        char title[64];
        snprintf(title, sizeof(title), "Files [%s]", sort_labels[p->sort]);
        tui_box_color(0, 0, h, list_w, title, TUI_COLOR_INFO);
        render_browser(p, h, list_w);

        tui_box_color(0, list_w, h, panel_w, "Now Playing", TUI_COLOR_LANE1);
        render_now_playing(p, h, list_w, panel_w);
    }

    tui_refresh();
}

/* ── Key handling ── */

static void handle_key(player_t *p, int key) {
    switch (key) {
    case 'q':
        p->running = 0;
        break;
    case ' ':
        if (p->transport.loaded_path[0])
            transport_toggle(&p->transport);
        else
            play_track(p, p->cursor);
        break;
    case 'n':
        next_track(p);
        break;
    case 'p':
        prev_track(p);
        break;
    case 's':
        transport_stop(&p->transport);
        break;
    case TUI_KEY_RIGHT: case 'l':
        transport_seek_rel(&p->transport, 5.0);
        break;
    case TUI_KEY_LEFT: case 'h':
        transport_seek_rel(&p->transport, -5.0);
        break;
    case TUI_KEY_UP: case 'k':
        if (p->cursor > 0) p->cursor--;
        break;
    case TUI_KEY_DOWN: case 'j':
        if (p->cursor < p->files.count - 1) p->cursor++;
        break;
    case TUI_KEY_ENTER:
        play_track(p, p->cursor);
        break;
    case 'r':
        p->repeat = (p->repeat + 1) % REP_COUNT;
        break;
    case '+': case '=':
        transport_set_volume(&p->transport, p->transport.volume + 0.05f);
        break;
    case '-':
        transport_set_volume(&p->transport, p->transport.volume - 0.05f);
        break;
    case '>': case '.':
        p->split += 0.05f;
        if (p->split > 0.8f) p->split = 0.8f;
        break;
    case '<': case ',':
        p->split -= 0.05f;
        if (p->split < 0.15f) p->split = 0.15f;
        break;
    case 'o': {
        char cur_path[MAX_PATH_LEN] = "";
        if (p->current >= 0 && p->current < p->files.count)
            strncpy(cur_path, p->files.files[p->current].path, MAX_PATH_LEN);

        p->sort = (p->sort + 1) % SORT_COUNT;
        if (p->sort == SORT_NAME)
            sort_by_name(&p->files);
        else
            sort_by_path(&p->files);

        if (cur_path[0]) {
            for (int i = 0; i < p->files.count; i++) {
                if (strcmp(p->files.files[i].path, cur_path) == 0) {
                    p->current = i;
                    p->cursor = i;
                    break;
                }
            }
        }
        break;
    }
    }
}

/* ── Main ── */

int main(int argc, char **argv) {
    const char *dir = (argc > 1) ? argv[1] : ".";

    player_t p = {0};
    p.split = 0.35f;
    p.current = -1;
    p.running = 1;
    transport_init(&p.transport);

    int n = scan_directory(dir, &p.files);
    if (n == 0) {
        fprintf(stderr, "No media files found in: %s\n", dir);
        return 1;
    }
    p.cursor = 0;

    if (tui_init() != 0) {
        fprintf(stderr, "Failed to initialize terminal\n");
        return 1;
    }

    while (p.running) {
        render(&p);

        if (transport_update(&p.transport)) {
            next_track(&p);
        }

        int key = tui_key(50);
        if (key != TUI_KEY_NONE)
            handle_key(&p, key);
    }

    tui_end();
    transport_cleanup(&p.transport);
    return 0;
}
