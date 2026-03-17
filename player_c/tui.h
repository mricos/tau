/* tui.h - Terminal UI abstraction for tau
 *
 * Unicode box drawing, TDS color system, sparklines, progress bars.
 * All ncurses calls isolated here. Consumer code never includes <curses.h>.
 *
 * Color system mirrors TDS (Tetra Design System):
 *   Pairs 1-8:  data lanes (yellow, green, red, blue, magenta, cyan, white, white)
 *   Pairs 9-12: status (success=green, warning=yellow, error=red, info=cyan)
 */

#ifndef TAU_TUI_H
#define TAU_TUI_H

/* ── Key constants (normalized) ── */

enum {
    TUI_KEY_NONE   = -1,
    TUI_KEY_UP     = 256,
    TUI_KEY_DOWN,
    TUI_KEY_LEFT,
    TUI_KEY_RIGHT,
    TUI_KEY_ENTER,
    TUI_KEY_RESIZE,
    TUI_KEY_TAB,
    TUI_KEY_BACKSPACE,
};

/* ── Attributes (bitmask, combine with |) ── */

enum {
    TUI_NORMAL  = 0,
    TUI_BOLD    = 1,
    TUI_DIM     = 2,
    TUI_REVERSE = 4,
};

/* ── TDS Color pairs ── */

enum {
    TUI_COLOR_DEFAULT  = 0,   /* terminal default */
    /* Data lanes 1-8 */
    TUI_COLOR_LANE1    = 1,   /* yellow */
    TUI_COLOR_LANE2    = 2,   /* green */
    TUI_COLOR_LANE3    = 3,   /* red */
    TUI_COLOR_LANE4    = 4,   /* blue */
    TUI_COLOR_LANE5    = 5,   /* magenta */
    TUI_COLOR_LANE6    = 6,   /* cyan */
    TUI_COLOR_LANE7    = 7,   /* white */
    TUI_COLOR_LANE8    = 8,   /* white */
    /* Status 9-12 */
    TUI_COLOR_SUCCESS  = 9,   /* green */
    TUI_COLOR_WARNING  = 10,  /* yellow */
    TUI_COLOR_ERROR    = 11,  /* red */
    TUI_COLOR_INFO     = 12,  /* cyan */
};

/* ── Lifecycle ── */

/* Initialize terminal with colors. Returns 0 on success. */
int tui_init(void);

/* Restore terminal and clean up. */
void tui_end(void);

/* ── Screen ── */

/* Get terminal dimensions. */
void tui_size(int *rows, int *cols);

/* Clear screen. */
void tui_clear(void);

/* Refresh screen. */
void tui_refresh(void);

/* ── Drawing ── */

/* Print string at (row, col). Truncates at max_w chars.
 * attr: TUI_BOLD | TUI_DIM | TUI_REVERSE  (bitmask)
 * color: TUI_COLOR_* pair (0 = default) */
void tui_print(int row, int col, const char *s, int attr, int max_w);

/* Print with color. Convenience for tui_print + color. */
void tui_print_color(int row, int col, const char *s, int attr, int color, int max_w);

/* Draw Unicode box: ┌─┐ │ │ └─┘. title may be NULL.
 * color: TUI_COLOR_* for border, 0 = default. */
void tui_box(int y, int x, int h, int w, const char *title);
void tui_box_color(int y, int x, int h, int w, const char *title, int color);

/* Unicode progress bar: █░  */
void tui_bar(int y, int x, int w, float pct);

/* Colored progress bar. */
void tui_bar_color(int y, int x, int w, float pct, int color);

/* Sparkline: maps values[0..count-1] (range 0.0-1.0) to ▁▂▃▄▅▆▇█
 * Renders at (y, x) for count columns. */
void tui_sparkline(int y, int x, const float *values, int count, int color);

/* Horizontal line: ─ repeated w times. */
void tui_hline(int y, int x, int w);

/* ── Truncation helper ── */

/* Truncate string in the middle: "longfilen...me.wav"
 * Writes result to dst (must hold maxw+1 bytes). */
void tui_truncate_middle(const char *src, char *dst, int maxw);

/* ── Input ── */

/* Get key with timeout_ms wait (-1 = blocking). Returns TUI_KEY_* or ascii. */
int tui_key(int timeout_ms);

#endif /* TAU_TUI_H */
