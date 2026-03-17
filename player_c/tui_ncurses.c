/* tui.c - ncurses implementation of tui.h
 *
 * Unicode box drawing, TDS 12-color system, sparklines, progress bars.
 * All ncurses interaction confined to this file.
 */

#define _XOPEN_SOURCE_EXTENDED  /* wide-char ncurses */
#include "tui.h"
#include <curses.h>
#include <locale.h>
#include <string.h>

/* ── Unicode characters ── */

/* Box drawing */
static const char *BOX_TL = "\u250c";  /* ┌ */
static const char *BOX_TR = "\u2510";  /* ┐ */
static const char *BOX_BL = "\u2514";  /* └ */
static const char *BOX_BR = "\u2518";  /* ┘ */
static const char *BOX_H  = "\u2500";  /* ─ */
static const char *BOX_V  = "\u2502";  /* │ */

/* Progress bar */
static const char *BAR_FILLED = "\u2588";  /* █ */
static const char *BAR_EMPTY  = "\u2591";  /* ░ */

/* Sparkline levels (9 chars: space + 8 blocks) */
static const char *SPARK[] = {
    " ",
    "\u2581",  /* ▁ */
    "\u2582",  /* ▂ */
    "\u2583",  /* ▃ */
    "\u2584",  /* ▄ */
    "\u2585",  /* ▅ */
    "\u2586",  /* ▆ */
    "\u2587",  /* ▇ */
    "\u2588",  /* █ */
};
#define SPARK_LEVELS 9

/* ── Internal helpers ── */

static int _rows, _cols;

static void _update_size(void) {
    getmaxyx(stdscr, _rows, _cols);
}

static int _in_bounds(int y, int x) {
    return y >= 0 && y < _rows && x >= 0 && x < _cols;
}

static int _to_curses_attr(int attr, int color) {
    int a = A_NORMAL;
    if (attr & TUI_BOLD)    a |= A_BOLD;
    if (attr & TUI_DIM)     a |= A_DIM;
    if (attr & TUI_REVERSE) a |= A_REVERSE;
    if (color > 0 && color <= 12)
        a |= COLOR_PAIR(color);
    return a;
}

/* Safe mvaddstr that respects screen bounds */
static void _safe_mvaddstr(int y, int x, const char *s, int attr) {
    if (!_in_bounds(y, x)) return;
    attron(attr);
    mvaddstr(y, x, s);
    attroff(attr);
}

/* Safe single UTF-8 string at position */
static void _safe_mvaddutf8(int y, int x, const char *utf8, int attr) {
    if (!_in_bounds(y, x)) return;
    attron(attr);
    mvaddstr(y, x, utf8);
    attroff(attr);
}

/* ── TDS Color initialization ── */

static void _init_colors(void) {
    if (!has_colors()) return;
    start_color();
    use_default_colors();

    /* TDS color mapping: pair -> (fg, bg=-1 for transparent) */
    /* Data lanes 1-8 */
    init_pair(1, COLOR_YELLOW,  -1);   /* lane 1 */
    init_pair(2, COLOR_GREEN,   -1);   /* lane 2 */
    init_pair(3, COLOR_RED,     -1);   /* lane 3 */
    init_pair(4, COLOR_BLUE,    -1);   /* lane 4 */
    init_pair(5, COLOR_MAGENTA, -1);   /* lane 5 */
    init_pair(6, COLOR_CYAN,    -1);   /* lane 6 */
    init_pair(7, COLOR_WHITE,   -1);   /* lane 7 */
    init_pair(8, COLOR_WHITE,   -1);   /* lane 8 */
    /* Status 9-12 */
    init_pair(9,  COLOR_GREEN,  -1);   /* success */
    init_pair(10, COLOR_YELLOW, -1);   /* warning */
    init_pair(11, COLOR_RED,    -1);   /* error */
    init_pair(12, COLOR_CYAN,   -1);   /* info */
}

/* ══════════════════════════════════════════════════════════════════
 *  Public API
 * ══════════════════════════════════════════════════════════════════ */

/* ── Lifecycle ── */

int tui_init(void) {
    setlocale(LC_ALL, "");  /* enable UTF-8 */
    WINDOW *w = initscr();
    if (!w) return -1;
    cbreak();
    noecho();
    keypad(stdscr, TRUE);
    curs_set(0);
    _init_colors();
    _update_size();
    return 0;
}

void tui_end(void) {
    endwin();
}

/* ── Screen ── */

void tui_size(int *rows, int *cols) {
    _update_size();
    *rows = _rows;
    *cols = _cols;
}

void tui_clear(void) {
    erase();
}

void tui_refresh(void) {
    refresh();
}

/* ── Drawing ── */

void tui_print(int row, int col, const char *s, int attr, int max_w) {
    tui_print_color(row, col, s, attr, 0, max_w);
}

void tui_print_color(int row, int col, const char *s, int attr, int color, int max_w) {
    _update_size();
    if (row < 0 || row >= _rows || col < 0 || col >= _cols) return;

    int avail = _cols - col;
    if (max_w > 0 && max_w < avail) avail = max_w;

    int len = (int)strlen(s);
    if (len > avail) len = avail;
    if (len <= 0) return;

    int a = _to_curses_attr(attr, color);
    attron(a);
    mvaddnstr(row, col, s, len);
    attroff(a);
}

/* ── Box drawing (Unicode) ── */

void tui_box(int y, int x, int h, int w, const char *title) {
    tui_box_color(y, x, h, w, title, 0);
}

void tui_box_color(int y, int x, int h, int w, const char *title, int color) {
    _update_size();
    if (h < 2 || w < 2) return;

    int a = _to_curses_attr(0, color);

    /* Top border: ┌──title──┐ */
    _safe_mvaddutf8(y, x, BOX_TL, a);
    for (int i = 1; i < w - 1; i++)
        _safe_mvaddutf8(y, x + i, BOX_H, a);
    _safe_mvaddutf8(y, x + w - 1, BOX_TR, a);

    /* Title */
    if (title && title[0]) {
        int tlen = (int)strlen(title);
        int max_t = w - 4;
        if (tlen > max_t) tlen = max_t;
        if (tlen > 0 && _in_bounds(y, x + 2)) {
            char buf[256];
            int n = tlen < 254 ? tlen : 254;
            buf[0] = ' ';
            memcpy(buf + 1, title, n);
            buf[n + 1] = ' ';
            buf[n + 2] = '\0';
            _safe_mvaddstr(y, x + 1, buf, a | A_BOLD);
        }
    }

    /* Sides: │ ... │ */
    for (int r = 1; r < h - 1; r++) {
        _safe_mvaddutf8(y + r, x, BOX_V, a);
        _safe_mvaddutf8(y + r, x + w - 1, BOX_V, a);
    }

    /* Bottom border: └──┘ */
    _safe_mvaddutf8(y + h - 1, x, BOX_BL, a);
    for (int i = 1; i < w - 1; i++)
        _safe_mvaddutf8(y + h - 1, x + i, BOX_H, a);
    _safe_mvaddutf8(y + h - 1, x + w - 1, BOX_BR, a);
}

/* ── Progress bar (Unicode) ── */

void tui_bar(int y, int x, int w, float pct) {
    tui_bar_color(y, x, w, pct, 0);
}

void tui_bar_color(int y, int x, int w, float pct, int color) {
    _update_size();
    if (w < 1 || !_in_bounds(y, x)) return;
    if (pct < 0.0f) pct = 0.0f;
    if (pct > 1.0f) pct = 1.0f;

    int filled = (int)(pct * w + 0.5f);
    int a = _to_curses_attr(0, color);

    for (int i = 0; i < w; i++) {
        if (x + i >= _cols) break;
        _safe_mvaddutf8(y, x + i, i < filled ? BAR_FILLED : BAR_EMPTY, a);
    }
}

/* ── Sparkline ── */

void tui_sparkline(int y, int x, const float *values, int count, int color) {
    _update_size();
    int a = _to_curses_attr(0, color);

    for (int i = 0; i < count; i++) {
        if (x + i >= _cols) break;
        float v = values[i];
        if (v < 0.0f) v = 0.0f;
        if (v > 1.0f) v = 1.0f;

        /* Map 0.0-1.0 to levels 0-8 */
        int level = (int)(v * (SPARK_LEVELS - 1) + 0.5f);
        if (level < 0) level = 0;
        if (level >= SPARK_LEVELS) level = SPARK_LEVELS - 1;

        _safe_mvaddutf8(y, x + i, SPARK[level], a);
    }
}

/* ── Horizontal line (Unicode) ── */

void tui_hline(int y, int x, int w) {
    _update_size();
    for (int i = 0; i < w; i++) {
        if (x + i >= _cols) break;
        _safe_mvaddutf8(y, x + i, BOX_H, A_NORMAL);
    }
}

/* ── Truncation ── */

void tui_truncate_middle(const char *src, char *dst, int maxw) {
    int len = (int)strlen(src);
    if (len <= maxw) {
        memcpy(dst, src, len + 1);
        return;
    }
    if (maxw < 5) {
        memcpy(dst, src, maxw);
        dst[maxw] = '\0';
        return;
    }
    /* "front...back" — favor start slightly */
    int head = (maxw - 3 + 1) / 2;
    int tail = maxw - 3 - head;
    memcpy(dst, src, head);
    dst[head] = '.'; dst[head+1] = '.'; dst[head+2] = '.';
    memcpy(dst + head + 3, src + len - tail, tail);
    dst[maxw] = '\0';
}

/* ── Input ── */

int tui_key(int timeout_ms) {
    timeout(timeout_ms);
    int ch = getch();

    switch (ch) {
        case ERR:           return TUI_KEY_NONE;
        case KEY_UP:        return TUI_KEY_UP;
        case KEY_DOWN:      return TUI_KEY_DOWN;
        case KEY_LEFT:      return TUI_KEY_LEFT;
        case KEY_RIGHT:     return TUI_KEY_RIGHT;
        case KEY_ENTER:
        case '\n':
        case '\r':          return TUI_KEY_ENTER;
        case KEY_RESIZE:    return TUI_KEY_RESIZE;
        case '\t':          return TUI_KEY_TAB;
        case KEY_BACKSPACE:
        case 127:           return TUI_KEY_BACKSPACE;
        default:            return ch;
    }
}
