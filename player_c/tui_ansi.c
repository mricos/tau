/* tui_ansi.c - Raw ANSI escape sequence backend for tui.h
 *
 * Zero dependencies beyond POSIX. No ncurses.
 * All rendering via fprintf to /dev/tty.
 * Students can read the output — every byte is visible protocol.
 *
 * Link this OR tui_ncurses.c (renamed from tui.c), never both.
 */

#include "tui.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <locale.h>

/* ── Unicode characters (UTF-8 encoded) ── */

static const char *BOX_TL = "\xe2\x94\x8c";  /* ┌ */
static const char *BOX_TR = "\xe2\x94\x90";  /* ┐ */
static const char *BOX_BL = "\xe2\x94\x94";  /* └ */
static const char *BOX_BR = "\xe2\x94\x98";  /* ┘ */
static const char *BOX_H  = "\xe2\x94\x80";  /* ─ */
static const char *BOX_V  = "\xe2\x94\x82";  /* │ */

static const char *BAR_FILLED = "\xe2\x96\x88";  /* █ */
static const char *BAR_EMPTY  = "\xe2\x96\x91";  /* ░ */

/* Sparkline: 9 levels (space + 8 blocks) */
static const char *SPARK[] = {
    " ",
    "\xe2\x96\x81",  /* ▁ */
    "\xe2\x96\x82",  /* ▂ */
    "\xe2\x96\x83",  /* ▃ */
    "\xe2\x96\x84",  /* ▄ */
    "\xe2\x96\x85",  /* ▅ */
    "\xe2\x96\x86",  /* ▆ */
    "\xe2\x96\x87",  /* ▇ */
    "\xe2\x96\x88",  /* █ */
};
#define SPARK_LEVELS 9

/* ── Terminal state ── */

static FILE *_tty = NULL;
static int _tty_fd = -1;
static struct termios _orig_termios;
static int _termios_saved = 0;
static int _rows = 24;
static int _cols = 80;

/* TDS color table: index -> ANSI foreground code */
static const char *_color_fg[] = {
    /* 0  default  */ "\033[39m",
    /* 1  yellow   */ "\033[33m",
    /* 2  green    */ "\033[32m",
    /* 3  red      */ "\033[31m",
    /* 4  blue     */ "\033[34m",
    /* 5  magenta  */ "\033[35m",
    /* 6  cyan     */ "\033[36m",
    /* 7  white    */ "\033[37m",
    /* 8  white    */ "\033[37m",
    /* 9  green    */ "\033[32m",
    /* 10 yellow   */ "\033[33m",
    /* 11 red      */ "\033[31m",
    /* 12 cyan     */ "\033[36m",
};
#define NUM_COLORS 13

/* ── Internal helpers ── */

static void _query_size(void) {
    struct winsize ws;
    if (ioctl(_tty_fd, TIOCGWINSZ, &ws) == 0) {
        _rows = ws.ws_row;
        _cols = ws.ws_col;
    }
}

static volatile sig_atomic_t _resized = 0;

static void _sigwinch_handler(int sig) {
    (void)sig;
    _resized = 1;
}

static int _in_bounds(int y, int x) {
    return y >= 0 && y < _rows && x >= 0 && x < _cols;
}

/* Move cursor to (row, col) — 0-indexed, ANSI is 1-indexed */
static void _move(int row, int col) {
    fprintf(_tty, "\033[%d;%dH", row + 1, col + 1);
}

/* Emit ANSI attribute prefix */
static void _set_attr(int attr, int color) {
    fprintf(_tty, "\033[0m");  /* reset first */
    if (color > 0 && color < NUM_COLORS)
        fputs(_color_fg[color], _tty);
    if (attr & TUI_BOLD)
        fputs("\033[1m", _tty);
    if (attr & TUI_DIM)
        fputs("\033[2m", _tty);
    if (attr & TUI_REVERSE)
        fputs("\033[7m", _tty);
}

static void _reset_attr(void) {
    fputs("\033[0m", _tty);
}

/* ══════════════════════════════════════════════════════════════════
 *  Public API
 * ══════════════════════════════════════════════════════════════════ */

/* ── Lifecycle ── */

int tui_init(void) {
    setlocale(LC_ALL, "");

    _tty = fopen("/dev/tty", "r+");
    if (!_tty) return -1;
    _tty_fd = fileno(_tty);

    /* Save terminal state */
    if (tcgetattr(_tty_fd, &_orig_termios) == 0)
        _termios_saved = 1;

    /* Enter raw mode */
    struct termios raw = _orig_termios;
    raw.c_lflag &= ~(ECHO | ICANON | ISIG);
    raw.c_iflag &= ~(IXON | ICRNL);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    tcsetattr(_tty_fd, TCSAFLUSH, &raw);

    /* Alternate screen buffer + hide cursor */
    fputs("\033[?1049h", _tty);  /* enter alternate screen */
    fputs("\033[?25l", _tty);    /* hide cursor */
    fflush(_tty);

    /* Terminal size */
    _query_size();

    /* SIGWINCH for resize detection */
    struct sigaction sa;
    sa.sa_handler = _sigwinch_handler;
    sa.sa_flags = SA_RESTART;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGWINCH, &sa, NULL);

    return 0;
}

void tui_end(void) {
    if (!_tty) return;

    /* Show cursor + leave alternate screen */
    fputs("\033[?25h", _tty);    /* show cursor */
    fputs("\033[?1049l", _tty);  /* leave alternate screen */
    _reset_attr();
    fflush(_tty);

    /* Restore terminal */
    if (_termios_saved)
        tcsetattr(_tty_fd, TCSAFLUSH, &_orig_termios);

    fclose(_tty);
    _tty = NULL;
    _tty_fd = -1;
}

/* ── Screen ── */

void tui_size(int *rows, int *cols) {
    if (_resized) {
        _query_size();
        _resized = 0;
    }
    *rows = _rows;
    *cols = _cols;
}

void tui_clear(void) {
    if (!_tty) return;
    fputs("\033[2J\033[H", _tty);  /* clear screen + home cursor */
}

void tui_refresh(void) {
    if (!_tty) return;
    fflush(_tty);
}

/* ── Drawing ── */

void tui_print(int row, int col, const char *s, int attr, int max_w) {
    tui_print_color(row, col, s, attr, 0, max_w);
}

void tui_print_color(int row, int col, const char *s, int attr, int color, int max_w) {
    if (!_tty || !_in_bounds(row, col)) return;

    int avail = _cols - col;
    if (max_w > 0 && max_w < avail) avail = max_w;

    int len = (int)strlen(s);
    if (len > avail) len = avail;
    if (len <= 0) return;

    _move(row, col);
    _set_attr(attr, color);
    fwrite(s, 1, len, _tty);
    _reset_attr();
}

/* ── Box drawing ── */

void tui_box(int y, int x, int h, int w, const char *title) {
    tui_box_color(y, x, h, w, title, 0);
}

void tui_box_color(int y, int x, int h, int w, const char *title, int color) {
    if (!_tty || h < 2 || w < 2) return;

    _set_attr(0, color);

    /* Top border: ┌──title──┐ */
    _move(y, x);
    fputs(BOX_TL, _tty);
    for (int i = 1; i < w - 1; i++) fputs(BOX_H, _tty);
    fputs(BOX_TR, _tty);

    /* Title */
    if (title && title[0]) {
        int tlen = (int)strlen(title);
        int max_t = w - 4;
        if (tlen > max_t) tlen = max_t;
        if (tlen > 0) {
            _move(y, x + 1);
            _set_attr(TUI_BOLD, color);
            fputc(' ', _tty);
            fwrite(title, 1, tlen, _tty);
            fputc(' ', _tty);
        }
    }

    /* Sides: │ ... │ */
    _set_attr(0, color);
    for (int r = 1; r < h - 1; r++) {
        if (_in_bounds(y + r, x)) {
            _move(y + r, x);
            fputs(BOX_V, _tty);
        }
        if (_in_bounds(y + r, x + w - 1)) {
            _move(y + r, x + w - 1);
            fputs(BOX_V, _tty);
        }
    }

    /* Bottom border: └──┘ */
    if (_in_bounds(y + h - 1, x)) {
        _move(y + h - 1, x);
        fputs(BOX_BL, _tty);
        for (int i = 1; i < w - 1; i++) fputs(BOX_H, _tty);
        fputs(BOX_BR, _tty);
    }

    _reset_attr();
}

/* ── Progress bar ── */

void tui_bar(int y, int x, int w, float pct) {
    tui_bar_color(y, x, w, pct, 0);
}

void tui_bar_color(int y, int x, int w, float pct, int color) {
    if (!_tty || w < 1 || !_in_bounds(y, x)) return;
    if (pct < 0.0f) pct = 0.0f;
    if (pct > 1.0f) pct = 1.0f;

    int filled = (int)(pct * w + 0.5f);

    _move(y, x);
    _set_attr(0, color);
    for (int i = 0; i < w && x + i < _cols; i++)
        fputs(i < filled ? BAR_FILLED : BAR_EMPTY, _tty);
    _reset_attr();
}

/* ── Sparkline ── */

void tui_sparkline(int y, int x, const float *values, int count, int color) {
    if (!_tty || !_in_bounds(y, x)) return;

    _move(y, x);
    _set_attr(0, color);

    for (int i = 0; i < count && x + i < _cols; i++) {
        float v = values[i];
        if (v < 0.0f) v = 0.0f;
        if (v > 1.0f) v = 1.0f;
        int level = (int)(v * (SPARK_LEVELS - 1) + 0.5f);
        if (level < 0) level = 0;
        if (level >= SPARK_LEVELS) level = SPARK_LEVELS - 1;
        fputs(SPARK[level], _tty);
    }

    _reset_attr();
}

/* ── Horizontal line ── */

void tui_hline(int y, int x, int w) {
    if (!_tty || !_in_bounds(y, x)) return;
    _move(y, x);
    for (int i = 0; i < w && x + i < _cols; i++)
        fputs(BOX_H, _tty);
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
    int head = (maxw - 3 + 1) / 2;
    int tail = maxw - 3 - head;
    memcpy(dst, src, head);
    dst[head] = '.'; dst[head+1] = '.'; dst[head+2] = '.';
    memcpy(dst + head + 3, src + len - tail, tail);
    dst[maxw] = '\0';
}

/* ── Input ──
 *
 * Reads raw bytes from /dev/tty. Parses ANSI escape sequences
 * for arrow keys, enter, etc. Students: this is how terminals
 * actually send keystrokes — multi-byte sequences starting with ESC.
 *
 * Arrow up   = ESC [ A  (3 bytes: 0x1b 0x5b 0x41)
 * Arrow down = ESC [ B
 * Arrow right= ESC [ C
 * Arrow left = ESC [ D
 */

int tui_key(int timeout_ms) {
    if (_tty_fd < 0) return TUI_KEY_NONE;

    /* Check for resize */
    if (_resized) {
        _query_size();
        _resized = 0;
        return TUI_KEY_RESIZE;
    }

    /* Wait for input with timeout using select() */
    fd_set fds;
    FD_ZERO(&fds);
    FD_SET(_tty_fd, &fds);

    struct timeval tv;
    if (timeout_ms >= 0) {
        tv.tv_sec = timeout_ms / 1000;
        tv.tv_usec = (timeout_ms % 1000) * 1000;
    }

    int ready = select(_tty_fd + 1, &fds, NULL, NULL,
                       timeout_ms >= 0 ? &tv : NULL);
    if (ready <= 0) return TUI_KEY_NONE;

    /* Read first byte */
    unsigned char c;
    if (read(_tty_fd, &c, 1) != 1) return TUI_KEY_NONE;

    /* ESC sequence? */
    if (c == 0x1b) {
        /* Check if more bytes follow quickly (escape sequence vs bare ESC) */
        fd_set fds2;
        FD_ZERO(&fds2);
        FD_SET(_tty_fd, &fds2);
        struct timeval short_tv = { .tv_sec = 0, .tv_usec = 50000 }; /* 50ms */
        if (select(_tty_fd + 1, &fds2, NULL, NULL, &short_tv) <= 0)
            return 0x1b; /* bare ESC key */

        unsigned char seq[4];
        if (read(_tty_fd, &seq[0], 1) != 1) return 0x1b;

        if (seq[0] == '[') {
            /* CSI sequence: ESC [ ... */
            if (read(_tty_fd, &seq[1], 1) != 1) return TUI_KEY_NONE;

            switch (seq[1]) {
                case 'A': return TUI_KEY_UP;
                case 'B': return TUI_KEY_DOWN;
                case 'C': return TUI_KEY_RIGHT;
                case 'D': return TUI_KEY_LEFT;
                case 'H': return TUI_KEY_ENTER;  /* Home */
                default:
                    /* Consume remaining bytes of longer sequences (e.g. ESC[1;5C) */
                    if (seq[1] >= '0' && seq[1] <= '9') {
                        unsigned char discard;
                        /* Read until we hit a letter */
                        for (int i = 0; i < 8; i++) {
                            if (read(_tty_fd, &discard, 1) != 1) break;
                            if (discard >= 0x40 && discard <= 0x7e) break;
                        }
                    }
                    return TUI_KEY_NONE;
            }
        } else if (seq[0] == 'O') {
            /* SS3 sequence: ESC O ... (some terminals send this for arrow keys) */
            if (read(_tty_fd, &seq[1], 1) != 1) return TUI_KEY_NONE;
            switch (seq[1]) {
                case 'A': return TUI_KEY_UP;
                case 'B': return TUI_KEY_DOWN;
                case 'C': return TUI_KEY_RIGHT;
                case 'D': return TUI_KEY_LEFT;
                default:  return TUI_KEY_NONE;
            }
        }

        return TUI_KEY_NONE;
    }

    /* Single-byte keys */
    switch (c) {
        case '\n':
        case '\r':    return TUI_KEY_ENTER;
        case '\t':    return TUI_KEY_TAB;
        case 127:
        case '\b':    return TUI_KEY_BACKSPACE;
        default:      return (int)c;
    }
}
