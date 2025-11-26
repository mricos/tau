"""
Splash screen and startup demo for tau TUI.
Shows immediately on startup, displays loading progress as components initialize.
"""

import curses
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from tui_py.rendering.helpers import safe_addstr, safe_addstr_smart, smart_text
from tui_py.rendering.startup import StartupState, StartupTip, STARTUP_TIPS


# ASCII art logo options
LOGO_SMALL = [
    "  ╦╔═╗╦ ╦  ",
    "  ║╠═╣║ ║  ",
    "  ╩╩ ╩╚═╝  ",
]

LOGO_MEDIUM = [
    "  ████████╗ █████╗ ██╗   ██╗  ",
    "  ╚══██╔══╝██╔══██╗██║   ██║  ",
    "     ██║   ███████║██║   ██║  ",
    "     ██║   ██╔══██║██║   ██║  ",
    "     ██║   ██║  ██║╚██████╔╝  ",
    "     ╚═╝   ╚═╝  ╚═╝ ╚═════╝   ",
]

TAGLINE = "Terminal Audio Workstation"
SUBTITLE = "Neural Network Kernel Tuning"

QUICK_TIPS = [
    "Press ':' to enter CLI mode",
    "Press '?' for quick help",
    "Press Space to play/pause",
    "Press 1-8 to toggle lanes",
    "Press < > to zoom in/out",
    "Type 'quickstart' for tutorial",
]

LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# Color scheme
COLOR_LOGO = 4          # Orange (MODE palette)
COLOR_TAGLINE = 9       # Green (SUCCESS)
COLOR_SUBTITLE = 7      # Gray
COLOR_TIP = 1           # Amber
COLOR_LOADING = 12      # Blue (INFO)
COLOR_STEP = 7          # Gray for completed steps
COLOR_STEP_ACTIVE = 9   # Green for current step


@dataclass
class SplashState:
    """State for splash screen."""
    visible: bool = True  # Start visible by default
    loading_progress: float = 0.0
    loading_message: str = "Starting..."
    steps_completed: List[str] = field(default_factory=list)
    current_step: str = ""
    animation_frame: int = 0
    current_tip: int = 0
    ready: bool = False
    error: Optional[str] = None
    ready_time: Optional[float] = None

    # Customization
    logo_style: str = "medium"
    tips: List[str] = field(default_factory=lambda: QUICK_TIPS.copy())
    show_steps: bool = True
    auto_dismiss: bool = True
    auto_dismiss_delay: float = 2.0  # seconds after ready

    # Fade transition state
    fading: bool = False
    fade_progress: float = 0.0  # 0.0 = fully visible, 1.0 = fully faded
    fade_start_time: Optional[float] = None
    fade_duration: float = 0.5  # seconds for fade transition

    # Startup tips system (first-class)
    startup: Optional[StartupState] = None
    show_tips_page: bool = False  # Show dedicated tips page after loading
    tips_page_index: int = 0      # Current tip in tips page
    require_enter: bool = True    # Require Enter key (not any key)

    def should_dismiss(self) -> bool:
        """Check if splash should auto-dismiss."""
        if not self.auto_dismiss or not self.ready:
            return False
        if self.ready_time is None:
            return False
        return (time.time() - self.ready_time) >= self.auto_dismiss_delay

    def show(self):
        """Show splash screen."""
        self.visible = True
        self.loading_progress = 0.0
        self.loading_message = "Starting..."
        self.steps_completed = []
        self.current_step = ""
        self.ready = False
        self.error = None

    def hide(self):
        """Hide splash screen."""
        self.visible = False

    # Maximum steps to keep (prevent unbounded growth)
    MAX_STEPS = 20

    def set_step(self, message: str, progress: float = None):
        """Set current loading step."""
        if self.current_step:
            self.steps_completed.append(self.current_step)
            # Trim to prevent unbounded growth
            if len(self.steps_completed) > self.MAX_STEPS:
                self.steps_completed = self.steps_completed[-self.MAX_STEPS:]
        self.current_step = message
        self.loading_message = message
        if progress is not None:
            self.loading_progress = min(1.0, max(0.0, progress))

    def complete_step(self, message: str = None):
        """Mark current step complete and optionally start new one."""
        if self.current_step:
            self.steps_completed.append(self.current_step)
        if message:
            self.current_step = message
            self.loading_message = message
        else:
            self.current_step = ""

    def set_ready(self):
        """Mark loading complete."""
        if self.current_step:
            self.steps_completed.append(self.current_step)
        self.current_step = ""
        self.loading_progress = 1.0
        self.loading_message = "Ready!"
        self.ready = True
        self.ready_time = time.time()

    def set_error(self, error: str):
        """Set error state."""
        self.error = error
        self.loading_message = f"Error: {error}"

    def tick(self):
        """Advance animation frame."""
        self.animation_frame = (self.animation_frame + 1) % len(LOADING_FRAMES)
        # Rotate tips occasionally
        if self.animation_frame == 0:
            self.current_tip = (self.current_tip + 1) % len(self.tips)

    def init_startup_tips(self, show_tips: bool = True, tips_count: int = 3, require_enter: bool = True):
        """Initialize the startup tips system."""
        self.startup = StartupState()
        self.startup.config.show_tips = show_tips
        self.startup.total_tips_to_show = tips_count
        self.startup.config.require_enter = require_enter
        self.require_enter = require_enter
        self.show_tips_page = show_tips

    def enter_tips_page(self):
        """Transition from loading to tips page."""
        if self.startup and self.startup.config.show_tips:
            self.show_tips_page = True
            self.tips_page_index = 0

    def get_current_startup_tip(self) -> Optional[StartupTip]:
        """Get the current tip to display."""
        if self.startup:
            return self.startup.get_current_tip()
        return None

    def advance_tip_page(self) -> bool:
        """
        Advance to next tip. Returns True if all tips shown.
        """
        if not self.startup:
            return True
        return self.startup.acknowledge_tip()

    def should_show_tips(self) -> bool:
        """Check if tips page should be shown."""
        return (
            self.show_tips_page and
            self.startup is not None and
            self.startup.config.show_tips and
            self.startup.tips_acknowledged < self.startup.total_tips_to_show
        )

    def start_fade(self):
        """Begin fade-out transition."""
        self.fading = True
        self.fade_progress = 0.0
        self.fade_start_time = time.time()

    def update_fade(self) -> bool:
        """Update fade progress. Returns True if fade is complete."""
        if not self.fading or self.fade_start_time is None:
            return False
        elapsed = time.time() - self.fade_start_time
        self.fade_progress = min(1.0, elapsed / self.fade_duration)
        if self.fade_progress >= 1.0:
            self.fading = False
            self.visible = False
            return True
        return False

    def is_fade_complete(self) -> bool:
        """Check if fade transition is complete."""
        return self.fade_progress >= 1.0


class SplashRenderer:
    """Renders the splash screen."""

    def __init__(self, splash_state: SplashState):
        self.splash = splash_state

    def render(self, scr, screen_h: int, screen_w: int):
        """Render splash screen centered on display."""
        if not self.splash.visible:
            return

        # Clear screen
        scr.erase()

        # Calculate fade modifier
        fade = self.splash.fade_progress
        fade_dim = curses.A_DIM if fade > 0.2 else 0

        # Don't render most elements at high fade
        if fade >= 0.8:
            # Just clear screen during final fade
            scr.refresh()
            return

        # Select logo based on screen size
        if screen_w >= 35 and screen_h >= 15:
            logo = LOGO_MEDIUM
        else:
            logo = LOGO_SMALL

        # Calculate layout
        logo_height = len(logo)
        steps_to_show = min(5, len(self.splash.steps_completed) + 1)
        total_height = logo_height + 8 + steps_to_show  # logo + tagline + loading + steps + tip
        start_y = max(1, (screen_h - total_height) // 2)

        y = start_y

        # Draw logo (fades last)
        if fade < 0.7:
            logo_attr = curses.color_pair(COLOR_LOGO)
            if fade > 0.3:
                logo_attr |= curses.A_DIM
            else:
                logo_attr |= curses.A_BOLD
            for line in logo:
                x = (screen_w - len(line)) // 2
                safe_addstr(scr, y, max(0, x), line[:screen_w], logo_attr)
                y += 1
        else:
            y += logo_height

        y += 1

        # Draw tagline (fades mid)
        if fade < 0.5:
            tagline_attr = curses.color_pair(COLOR_TAGLINE)
            if fade > 0.2:
                tagline_attr |= curses.A_DIM
            else:
                tagline_attr |= curses.A_BOLD
            x = (screen_w - len(TAGLINE)) // 2
            safe_addstr(scr, y, max(0, x), TAGLINE, tagline_attr)
        y += 1

        # Draw subtitle (fades early)
        if fade < 0.4:
            x = (screen_w - len(SUBTITLE)) // 2
            safe_addstr(scr, y, max(0, x), SUBTITLE,
                       curses.color_pair(COLOR_SUBTITLE) | curses.A_DIM)
        y += 2

        # Draw loading bar (fades early)
        if fade < 0.3:
            self._render_loading_bar(scr, y, screen_w, fade_dim)
        y += 2

        # Draw step history (fades very early)
        if fade < 0.2 and self.splash.show_steps:
            y = self._render_steps(scr, y, screen_w)

        # Draw current tip at bottom (fades very early)
        if fade < 0.15 and self.splash.tips and not self.splash.error:
            tip_y = screen_h - 3
            tip = self.splash.tips[self.splash.current_tip]
            self._render_tip(scr, tip_y, screen_w, tip)

        # Draw dismiss hint if ready (fades early)
        if fade < 0.2 and self.splash.ready:
            if self.splash.require_enter:
                hint = "Press Enter to continue..."
            else:
                hint = "Press any key to continue..."
            hint_y = screen_h - 2
            x = (screen_w - len(hint)) // 2
            safe_addstr(scr, hint_y, max(0, x), hint,
                       curses.A_BLINK | curses.color_pair(COLOR_SUBTITLE))

        scr.refresh()

    def _render_loading_bar(self, scr, y: int, screen_w: int, fade_attr: int = 0):
        """Render loading bar and current message."""
        bar_width = min(40, screen_w - 10)
        filled = int(bar_width * self.splash.loading_progress)
        empty = bar_width - filled

        # Spinner + bar + percentage
        spinner = LOADING_FRAMES[self.splash.animation_frame]
        bar = f"{spinner} [{'█' * filled}{'░' * empty}] {int(self.splash.loading_progress * 100):3d}%"

        x = (screen_w - len(bar)) // 2

        if self.splash.error:
            attr = curses.color_pair(11)  # Red for error
        elif self.splash.ready:
            attr = curses.color_pair(COLOR_TAGLINE)  # Green for ready
        else:
            attr = curses.color_pair(COLOR_LOADING)

        safe_addstr(scr, y, max(0, x), bar, attr | fade_attr)

    def _render_steps(self, scr, y: int, screen_w: int) -> int:
        """Render completed steps and current step."""
        max_steps = 5
        steps = self.splash.steps_completed[-max_steps:]

        # Calculate available width for step text
        x = (screen_w - 44) // 2  # Align left of center block
        x = max(2, x)
        step_max_width = screen_w - x - 1  # Leave 1 char margin

        # Show recent completed steps (dimmed)
        for step in steps:
            prefix = "  ✓ "
            # Use smart_text for the step content
            step_text = smart_text(step, screen_w, x + len(prefix), margin=1)
            line = prefix + step_text
            safe_addstr(scr, y, x, line, curses.color_pair(COLOR_STEP) | curses.A_DIM)
            y += 1

        # Show current step (highlighted)
        if self.splash.current_step:
            spinner = LOADING_FRAMES[self.splash.animation_frame]
            prefix = f"  {spinner} "
            # Use smart_text for current step (may have long filenames)
            step_text = smart_text(self.splash.current_step, screen_w, x + len(prefix), margin=1)
            line = prefix + step_text
            safe_addstr(scr, y, x, line, curses.color_pair(COLOR_STEP_ACTIVE))
            y += 1

        return y + 1

    def _render_tip(self, scr, y: int, screen_w: int, tip: str):
        """Render a tip."""
        prefix = "TIP: "
        full_tip = prefix + tip
        x = (screen_w - len(full_tip)) // 2

        safe_addstr(scr, y, max(0, x), prefix,
                   curses.color_pair(COLOR_TIP) | curses.A_DIM)
        safe_addstr(scr, y, max(0, x + len(prefix)), tip,
                   curses.color_pair(COLOR_TIP))

    def render_tips_page(self, scr, screen_h: int, screen_w: int):
        """Render dedicated tips/tutorial page after loading."""
        if not self.splash.startup:
            return

        scr.erase()

        tip = self.splash.get_current_startup_tip()
        if not tip:
            return

        # Calculate layout
        y = screen_h // 4

        # Header
        header = "Did You Know?"
        x = (screen_w - len(header)) // 2
        safe_addstr(scr, y, max(0, x), header,
                   curses.color_pair(COLOR_TAGLINE) | curses.A_BOLD)
        y += 2

        # Draw box around tip
        box_width = min(60, screen_w - 4)
        box_x = (screen_w - box_width) // 2
        box_height = 8

        # Top border
        safe_addstr(scr, y, box_x, "┌" + "─" * (box_width - 2) + "┐",
                   curses.color_pair(COLOR_SUBTITLE))
        y += 1

        # Tip title
        title_line = f"│ {tip.title}"
        title_line = title_line + " " * (box_width - len(title_line) - 1) + "│"
        safe_addstr(scr, y, box_x, smart_text(title_line, screen_w, box_x),
                   curses.color_pair(COLOR_LOGO) | curses.A_BOLD)
        y += 1

        # Separator
        safe_addstr(scr, y, box_x, "├" + "─" * (box_width - 2) + "┤",
                   curses.color_pair(COLOR_SUBTITLE))
        y += 1

        # Tip content (wrap if needed)
        content = tip.content
        content_width = box_width - 4  # 2 chars padding each side
        words = content.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= content_width:
                current_line = current_line + " " + word if current_line else word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        for line in lines[:3]:  # Max 3 lines of content
            content_line = f"│  {line}"
            content_line = content_line + " " * (box_width - len(content_line) - 1) + "│"
            safe_addstr(scr, y, box_x, content_line, curses.color_pair(7))
            y += 1

        # Fill remaining space
        for _ in range(3 - len(lines[:3])):
            empty_line = "│" + " " * (box_width - 2) + "│"
            safe_addstr(scr, y, box_x, empty_line, curses.color_pair(COLOR_SUBTITLE))
            y += 1

        # Shortcut or command line
        if tip.shortcut:
            shortcut_line = f"│  Shortcut: {tip.shortcut}"
        elif tip.command:
            shortcut_line = f"│  Command: {tip.command}"
        else:
            shortcut_line = "│"
        shortcut_line = shortcut_line + " " * (box_width - len(shortcut_line) - 1) + "│"
        safe_addstr(scr, y, box_x, shortcut_line,
                   curses.color_pair(COLOR_TIP))
        y += 1

        # Bottom border
        safe_addstr(scr, y, box_x, "└" + "─" * (box_width - 2) + "┘",
                   curses.color_pair(COLOR_SUBTITLE))
        y += 2

        # Progress indicator
        tips_shown = self.splash.startup.tips_acknowledged + 1
        total_tips = self.splash.startup.total_tips_to_show
        progress = f"Tip {tips_shown} of {total_tips}"
        x = (screen_w - len(progress)) // 2
        safe_addstr(scr, y, max(0, x), progress, curses.color_pair(COLOR_SUBTITLE))
        y += 2

        # Navigation hint
        hint = "Press Enter to continue..."
        x = (screen_w - len(hint)) // 2
        safe_addstr(scr, y, max(0, x), hint,
                   curses.A_BLINK | curses.color_pair(COLOR_SUBTITLE))

        # Skip hint at bottom
        skip_hint = "(Press Esc to skip all tips)"
        safe_addstr(scr, screen_h - 2, (screen_w - len(skip_hint)) // 2,
                   skip_hint, curses.color_pair(7) | curses.A_DIM)

        scr.refresh()


def render_splash(scr, splash_state: SplashState, screen_h: int, screen_w: int):
    """Convenience function to render splash screen."""
    renderer = SplashRenderer(splash_state)
    renderer.render(scr, screen_h, screen_w)
