"""
Sidebar rendering module with collapsible panels.
Provides a dynamic right sidebar for the CLI output area.
"""

import curses
from dataclasses import dataclass, field
from typing import List, Callable, Any, TYPE_CHECKING
from tui_py.rendering.helpers import safe_addstr

if TYPE_CHECKING:
    from tau_lib.core.state import AppState


# Sidebar color scheme
COLOR_PANEL_HEADER = 4      # Panel headers (MODE palette - orange)
COLOR_PANEL_CONTENT = 7     # Panel content (gray)
COLOR_PANEL_VALUE = 1       # Values/data (amber)
COLOR_PANEL_BORDER = 7      # Border color (gray)
COLOR_HIGHLIGHT = 9         # Highlighted/selected (green)
BG = 0


@dataclass
class SidebarPanel:
    """A collapsible panel in the sidebar."""
    id: str
    title: str
    collapsed: bool = False
    content_fn: Callable[['AppState'], List[tuple]] = None  # Returns [(label, value), ...]
    min_height: int = 1  # Header only when collapsed
    max_height: int = 8  # Max expanded height

    def get_height(self) -> int:
        """Get current height based on collapse state."""
        if self.collapsed:
            return 1  # Just the header
        return self.max_height

    def toggle(self):
        """Toggle collapsed state."""
        self.collapsed = not self.collapsed


@dataclass
class SidebarState:
    """State for the sidebar."""
    visible: bool = False
    width: int = 24  # Default sidebar width
    min_width: int = 20
    max_width: int = 40
    panels: List[SidebarPanel] = field(default_factory=list)
    selected_panel: int = 0  # For keyboard navigation

    def toggle_visibility(self):
        """Toggle sidebar visibility."""
        self.visible = not self.visible

    def toggle_panel(self, panel_id: str = None):
        """Toggle a panel's collapsed state."""
        if panel_id:
            for p in self.panels:
                if p.id == panel_id:
                    p.toggle()
                    return
        elif self.panels and 0 <= self.selected_panel < len(self.panels):
            self.panels[self.selected_panel].toggle()

    def select_next(self):
        """Select next panel."""
        if self.panels:
            self.selected_panel = (self.selected_panel + 1) % len(self.panels)

    def select_prev(self):
        """Select previous panel."""
        if self.panels:
            self.selected_panel = (self.selected_panel - 1) % len(self.panels)

    def get_total_height(self) -> int:
        """Get total height of all panels."""
        return sum(p.get_height() for p in self.panels)


def create_default_panels(state: 'AppState') -> List[SidebarPanel]:
    """Create default sidebar panels."""

    def kernel_content(st: 'AppState') -> List[tuple]:
        k = st.kernel
        return [
            ("tau_a", f"{k.tau_a:.3f}s"),
            ("tau_r", f"{k.tau_r:.3f}s"),
            ("thresh", f"{k.threshold:.2f}"),
            ("refrac", f"{k.refractory:.3f}s"),
        ]

    def transport_content(st: 'AppState') -> List[tuple]:
        t = st.transport
        return [
            ("pos", f"{t.position:.2f}s"),
            ("dur", f"{t.duration:.2f}s"),
            ("zoom", f"{t.span:.2f}s"),
            ("play", "YES" if t.playing else "no"),
        ]

    def lanes_content(st: 'AppState') -> List[tuple]:
        items = []
        for i in range(10):
            lane = st.lanes.get_lane(i)
            if lane:
                vis = "+" if lane.is_visible() else "-"
                items.append((f"L{i}", f"{vis}{lane.name[:6]}"))
        return items

    def status_content(st: 'AppState') -> List[tuple]:
        items = [
            ("video", "ON" if st.features.video_enabled else "off"),
            ("audio", "ON" if st.transport.tau else "off"),
        ]
        if st.data_buffer:
            items.append(("samples", f"{len(st.data_buffer)}"))
        if st.markers.count() > 0:
            items.append(("markers", f"{st.markers.count()}"))
        return items

    return [
        SidebarPanel(
            id="kernel",
            title="Kernel",
            collapsed=False,
            content_fn=kernel_content,
            max_height=5,
        ),
        SidebarPanel(
            id="transport",
            title="Transport",
            collapsed=True,
            content_fn=transport_content,
            max_height=5,
        ),
        SidebarPanel(
            id="lanes",
            title="Lanes",
            collapsed=True,
            content_fn=lanes_content,
            max_height=6,
        ),
        SidebarPanel(
            id="status",
            title="Status",
            collapsed=True,
            content_fn=status_content,
            max_height=5,
        ),
    ]


class SidebarRenderer:
    """Renders the sidebar with collapsible panels."""

    def __init__(self, state: 'AppState', sidebar_state: SidebarState):
        self.state = state
        self.sidebar = sidebar_state

    def render(self, scr, x: int, y: int, height: int) -> int:
        """
        Render sidebar at position.

        Args:
            scr: curses screen
            x: X position (left edge of sidebar)
            y: Y position (top)
            height: Available height

        Returns:
            int: Actual width used
        """
        if not self.sidebar.visible:
            return 0

        width = self.sidebar.width
        y_cursor = y

        # Draw vertical border
        for row in range(y, y + height):
            safe_addstr(scr, row, x, "│", curses.color_pair(COLOR_PANEL_BORDER) | curses.A_DIM)

        # Content starts after border
        content_x = x + 2
        content_width = width - 3

        # Render each panel
        for i, panel in enumerate(self.sidebar.panels):
            if y_cursor >= y + height:
                break

            panel_height = panel.get_height()
            available = y + height - y_cursor

            if available < 1:
                break

            # Render panel
            lines_used = self._render_panel(
                scr, panel, i,
                content_x, y_cursor,
                content_width,
                min(panel_height, available)
            )
            y_cursor += lines_used

        return width

    def _render_panel(self, scr, panel: SidebarPanel, panel_idx: int,
                      x: int, y: int, width: int, height: int) -> int:
        """Render a single panel."""
        is_selected = (panel_idx == self.sidebar.selected_panel)

        # Header with collapse indicator
        collapse_char = "▶" if panel.collapsed else "▼"
        header = f"{collapse_char} {panel.title}"

        # Highlight selected panel header
        header_attr = curses.color_pair(COLOR_PANEL_HEADER)
        if is_selected:
            header_attr |= curses.A_REVERSE

        safe_addstr(scr, y, x, header[:width], header_attr)

        if panel.collapsed or height <= 1:
            return 1

        # Render content
        content = panel.content_fn(self.state) if panel.content_fn else []
        y_cursor = y + 1

        for label, value in content:
            if y_cursor >= y + height:
                break

            # Format: "label: value" with truncation
            line = f"  {label}: {value}"
            safe_addstr(scr, y_cursor, x, line[:width],
                       curses.color_pair(COLOR_PANEL_CONTENT))
            y_cursor += 1

        return y_cursor - y


def render_two_column_list(scr, items: List[str], x: int, y: int,
                           width: int, height: int, col_gap: int = 2) -> int:
    """
    Render a list in two columns (for wrapping long lists).

    Args:
        scr: curses screen
        items: List of strings to display
        x: X position
        y: Y position
        width: Total width available
        height: Max height available
        col_gap: Gap between columns

    Returns:
        int: Lines used
    """
    if not items:
        return 0

    col_width = (width - col_gap) // 2
    max_items = height * 2  # 2 columns

    items_to_show = items[:max_items]
    lines_needed = (len(items_to_show) + 1) // 2

    for i, item in enumerate(items_to_show):
        row = i // 2
        col = i % 2

        if row >= height:
            break

        item_x = x + (col * (col_width + col_gap))
        safe_addstr(scr, y + row, item_x, item[:col_width], curses.A_DIM)

    return min(lines_needed, height)
