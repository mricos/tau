"""
Splash screen and startup demo for tau TUI.
Shows immediately on startup, displays loading progress as components initialize.
"""

import curses
import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from tui_py.rendering.helpers import safe_addstr, safe_addstr_smart, smart_text
from tui_py.rendering.startup import StartupState, StartupTip, STARTUP_TIPS
from tui_py.rendering.transition import StartupTransitionState
from tui_py.rendering.scene_buffer import opacity_to_attr
from tui_py.rendering.logo import (
    Logo, LogoVariant, MorphDirection, LogoDesignTokens,
    LOGO_SMALL, LOGO_MEDIUM, T_MORPH_FRAMES, AU_STATIC
)

# Re-export for backwards compatibility
TAU_MORPH_FRAMES = T_MORPH_FRAMES
LOGO_AU = AU_STATIC


@dataclass
class SplashAnimationConfig:
    """Configuration for splash screen animations."""
    # Progress rate limiting
    progress_max_rate: float = 0.10      # Max 10% progress per tick
    progress_tick_ms: int = 200          # Tick interval in ms
    progress_target: float = 0.70        # Target progress before steps complete

    # Logo morph animation (Tab easter egg)
    morph_enabled: bool = True
    morph_duration_ms: int = 800         # Total morph duration
    morph_hold_end_ms: int = 1000        # Hold at end before returning

    # General timing
    fade_duration: float = 0.5           # Fade out duration in seconds
    step_display_interval: float = 0.2   # Time between step displays

    # Visual effects
    shimmer_enabled: bool = True
    shimmer_wavelength: float = 8.0
    shimmer_speed: float = 0.5


@dataclass
class SplashAnimationState:
    """Runtime state for splash animations."""
    # Progress animation
    display_progress: float = 0.0        # What's shown (smoothed)
    target_progress: float = 0.0         # What we're animating toward
    last_progress_tick: float = 0.0

    # Logo morph (Tab easter egg: toggle T <-> tau)
    morph_active: bool = False           # Is morph animation running
    morph_start_time: float = 0.0
    morph_target: str = "t"              # Current target state: "t" or "tau"

    # General
    frame_count: int = 0
    start_time: float = field(default_factory=time.time)

    def trigger_morph(self):
        """Toggle between T and tau states (Tab easter egg)."""
        # If not animating, start animation to opposite state
        if not self.morph_active:
            self.morph_active = True
            self.morph_start_time = time.time()
            # Toggle target
            self.morph_target = "tau" if self.morph_target == "t" else "t"

    def get_morph_frame(self, config: SplashAnimationConfig) -> int:
        """Calculate current morph frame based on timing."""
        total_frames = len(TAU_MORPH_FRAMES)

        if not self.morph_active:
            # Return final frame based on current state
            return 0 if self.morph_target == "t" else total_frames - 1

        now = time.time()
        elapsed = (now - self.morph_start_time) * 1000  # ms
        progress = min(1.0, elapsed / config.morph_duration_ms)

        if self.morph_target == "tau":
            # Morphing T -> tau (frame 0 -> frame N)
            frame = int(progress * (total_frames - 1))
        else:
            # Morphing tau -> T (frame N -> frame 0)
            frame = total_frames - 1 - int(progress * (total_frames - 1))

        frame = max(0, min(total_frames - 1, frame))

        if progress >= 1.0:
            self.morph_active = False

        return frame

    def update_progress(self, config: SplashAnimationConfig) -> bool:
        """Update display progress with rate limiting. Returns True if changed."""
        now = time.time()
        elapsed_ms = (now - self.last_progress_tick) * 1000

        if elapsed_ms < config.progress_tick_ms:
            return False

        self.last_progress_tick = now

        if self.display_progress < self.target_progress:
            # Rate limit the progress increase
            max_increase = config.progress_max_rate
            diff = self.target_progress - self.display_progress
            increase = min(diff, max_increase)
            self.display_progress += increase
            return True
        return False

    def tick(self):
        """Advance frame counter."""
        self.frame_count += 1

TAGLINE = "Terminal Audio Workstation"
SUBTITLE = "Neural Network Kernel Tuning"
VERSION = "v0.0.1"

QUICK_TIPS = [
    "Press ':' to enter CLI mode",
    "Press '?' for quick help",
    "Press Space to play/pause",
    "Press 1-8 to toggle lanes",
    "Press < > to zoom in/out",
    "Type 'quickstart' for tutorial",
]

LOADING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def wave_shimmer(text: str, frame: int, wavelength: float = 8.0, speed: float = 0.5):
    """
    Generate per-character brightness for a shimmer wave effect.
    Returns list of (char, is_bright) tuples.

    The wave travels through the text, making characters bright/dim
    in a smooth ripple pattern.
    """
    result = []
    phase = frame * speed
    for i, char in enumerate(text):
        # Sine wave determines brightness, shifted by character position
        wave_val = math.sin((i / wavelength) * 2 * math.pi - phase)
        # Map sine (-1 to 1) to brightness threshold
        is_bright = wave_val > 0.0
        result.append((char, is_bright))
    return result


# Color scheme
COLOR_LOGO = 4          # Orange (MODE palette)
COLOR_TAGLINE = 9       # Green (SUCCESS)
COLOR_SUBTITLE = 7      # Gray
COLOR_TIP = 1           # Amber
COLOR_LOADING = 12      # Blue (INFO)
COLOR_STEP = 7          # Gray for completed steps
COLOR_STEP_ACTIVE = 9   # Green for current step


@dataclass
class StepQueue:
    """Async-friendly step display with rate limiting."""
    steps: List[str] = field(default_factory=list)
    display_index: int = 0  # How many steps are visible
    last_display_time: float = 0.0
    min_interval: float = 0.2  # 200ms between steps

    def add(self, message: str):
        """Add step to queue (non-blocking)."""
        self.steps.append(message)

    def tick(self) -> bool:
        """Call from render loop. Returns True if display updated."""
        if self.display_index >= len(self.steps):
            return False
        now = time.time()
        if now - self.last_display_time >= self.min_interval:
            self.display_index += 1
            self.last_display_time = now
            return True
        return False

    def visible_steps(self) -> List[str]:
        """Get steps to display (completed ones)."""
        # Show all but the last one as "completed", last visible one is "current"
        if self.display_index == 0:
            return []
        return self.steps[:self.display_index - 1]

    def current_step(self) -> Optional[str]:
        """Get the current step being processed."""
        if self.display_index == 0 or self.display_index > len(self.steps):
            return None
        return self.steps[self.display_index - 1]

    def all_visible(self) -> bool:
        """Check if all queued steps have been displayed."""
        return self.display_index >= len(self.steps)


@dataclass
class SplashState:
    """State for splash screen."""
    visible: bool = True  # Start visible by default
    loading_progress: float = 0.0
    loading_message: str = "Starting..."
    animation_frame: int = 0
    current_tip: int = 0
    ready: bool = False
    ready_queued: bool = False  # Ready has been requested but not yet displayed
    error: Optional[str] = None
    ready_time: Optional[float] = None

    # Step queue for async display
    step_queue: StepQueue = field(default_factory=StepQueue)

    # Animation system
    anim_config: SplashAnimationConfig = field(default_factory=SplashAnimationConfig)
    anim_state: SplashAnimationState = field(default_factory=SplashAnimationState)

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

    # Random tip on splash (pick one at init)
    random_tip_index: int = -1    # -1 means not initialized

    # Page transition system
    transition_state: Optional[StartupTransitionState] = None

    # Logo class instance (optional, for advanced rendering)
    logo: Optional[Logo] = None

    def init_transition_state(self):
        """Initialize the transition state machine for startup sequence."""
        self.transition_state = StartupTransitionState()

    def init_logo(self, bpm: float = None) -> Logo:
        """
        Initialize and return the Logo class instance.

        This enables advanced logo features like BPM sync, fine-grained
        fade control, and compositable rendering.

        Args:
            bpm: Optional BPM for synchronized effects

        Returns:
            The Logo instance (also stored in self.logo)
        """
        self.logo = Logo()
        if bpm is not None:
            self.logo.set_bpm(bpm)
            self.logo.enable_bpm_sync(True)
        return self.logo

    def get_logo(self) -> Logo:
        """Get or create the Logo instance."""
        if self.logo is None:
            self.init_logo()
        return self.logo

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
        self.step_queue = StepQueue()
        self.ready = False
        self.ready_queued = False
        self.error = None
        # Reset animation state
        self.anim_state = SplashAnimationState()
        self.anim_state.morph_start_time = time.time()
        # Pick a random tip for this splash
        if self.tips:
            self.random_tip_index = random.randint(0, len(self.tips) - 1)

    def hide(self):
        """Hide splash screen."""
        self.visible = False

    def set_step(self, message: str, progress: float = None):
        """Queue a loading step (non-blocking)."""
        self.step_queue.add(message)
        self.loading_message = message
        if progress is not None:
            # Set target progress - actual display will animate toward it
            target = min(1.0, max(0.0, progress))
            # Cap at configured target until ready
            if not self.ready_queued:
                target = min(target, self.anim_config.progress_target)
            self.anim_state.target_progress = target
            self.loading_progress = target  # Keep for compatibility

    def set_ready(self):
        """Queue ready state (non-blocking). Actual ready triggers after all steps shown."""
        self.ready_queued = True
        self.anim_state.target_progress = 1.0
        self.loading_progress = 1.0
        self.loading_message = "Ready!"

    def set_error(self, error: str):
        """Set error state."""
        self.error = error
        self.loading_message = f"Error: {error}"

    def tick(self):
        """Advance animation frame and step queue."""
        self.animation_frame = (self.animation_frame + 1) % len(LOADING_FRAMES)
        # Advance step queue display
        self.step_queue.tick()
        # Update animated progress
        self.anim_state.update_progress(self.anim_config)
        self.anim_state.tick()
        # Update Logo class if initialized
        if self.logo is not None:
            self.logo.update()
        # If ready was queued and all steps are visible, trigger actual ready
        if self.ready_queued and self.step_queue.all_visible() and not self.ready:
            self.ready = True
            self.ready_time = time.time()

    def get_display_progress(self) -> float:
        """Get the smoothly animated progress value for display."""
        return self.anim_state.display_progress

    def get_logo_frame(self) -> List[str]:
        """Get current logo frame (morphing T or static)."""
        # Use Logo class if initialized
        if self.logo is not None:
            return self.logo.get_frame()

        # Fallback to legacy behavior
        if self.anim_config.morph_enabled:
            frame_idx = self.anim_state.get_morph_frame(self.anim_config)
            t_frame = TAU_MORPH_FRAMES[frame_idx]
            # Combine morphing T with static AU
            combined = []
            for i, t_line in enumerate(t_frame):
                combined.append(t_line + LOGO_AU[i])
            return combined
        return LOGO_MEDIUM

    def trigger_tau_morph(self):
        """Trigger the T -> tau -> T easter egg animation (Tab key)."""
        # Use Logo class if initialized
        if self.logo is not None:
            self.logo.trigger_morph()
        else:
            self.anim_state.trigger_morph()

    def steps_completed(self) -> List[str]:
        """Get completed steps for display."""
        return self.step_queue.visible_steps()

    def current_step(self) -> Optional[str]:
        """Get current step for display."""
        return self.step_queue.current_step()

    def tick_only_animation(self):
        """Advance only animation frame (for tips page)."""
        self.animation_frame = (self.animation_frame + 1) % len(LOADING_FRAMES)

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

    def next_tip(self):
        """Navigate to next tip (arrow right/down)."""
        if self.startup:
            total = len(STARTUP_TIPS)
            self.startup.current_tip_index = (self.startup.current_tip_index + 1) % total

    def prev_tip(self):
        """Navigate to previous tip (arrow left/up)."""
        if self.startup:
            total = len(STARTUP_TIPS)
            self.startup.current_tip_index = (self.startup.current_tip_index - 1) % total

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

        # Select logo based on screen size (use morphing logo for medium+)
        if screen_w >= 35 and screen_h >= 15:
            logo = self.splash.get_logo_frame()
        else:
            logo = LOGO_SMALL

        # Calculate layout
        logo_height = len(logo)
        steps_to_show = min(5, len(self.splash.steps_completed()) + 1)
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
        y += 1

        # Draw version (fades early)
        if fade < 0.4:
            x = (screen_w - len(VERSION)) // 2
            safe_addstr(scr, y, max(0, x), VERSION,
                       curses.color_pair(COLOR_SUBTITLE) | curses.A_DIM)
        y += 2

        # Draw loading bar (fades early)
        if fade < 0.3:
            self._render_loading_bar(scr, y, screen_w, fade_dim)
        y += 2

        # Draw step history (fades very early)
        if fade < 0.2 and self.splash.show_steps:
            y = self._render_steps(scr, y, screen_w)

        # Draw one random tip at bottom (fades very early) - disabled for now
        # if fade < 0.15 and self.splash.tips and not self.splash.error:
        #     tip_y = screen_h - 4
        #     # Use random_tip_index if set, otherwise pick one now
        #     idx = self.splash.random_tip_index
        #     if idx < 0 or idx >= len(self.splash.tips):
        #         idx = random.randint(0, len(self.splash.tips) - 1)
        #         self.splash.random_tip_index = idx
        #     tip = self.splash.tips[idx]
        #     self._render_tip(scr, tip_y, screen_w, tip)

        # Draw dismiss hint if ready - yellow text
        if fade < 0.2 and self.splash.ready:
            hint = "Press Enter to continue"
            hint_y = screen_h - 2
            x = (screen_w - len(hint)) // 2
            safe_addstr(scr, hint_y, max(0, x), hint,
                       curses.color_pair(COLOR_TIP))

        scr.refresh()

    def _render_loading_bar(self, scr, y: int, screen_w: int, fade_attr: int = 0):
        """Render loading bar and current message."""
        bar_width = min(40, screen_w - 10)
        # Use animated progress for smooth display
        progress = self.splash.get_display_progress()
        filled = int(bar_width * progress)
        empty = bar_width - filled

        # Bar + percentage (no spinner)
        bar = f"[{'█' * filled}{'░' * empty}] {int(progress * 100):3d}%"

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
        steps = self.splash.steps_completed()[-max_steps:]

        # Calculate available width for step text
        x = (screen_w - 44) // 2  # Align left of center block
        x = max(2, x)

        # Show recent completed steps (dimmed)
        for step in steps:
            prefix = "  ✓ "
            # Use smart_text for the step content
            step_text = smart_text(step, screen_w, x + len(prefix), margin=1)
            line = prefix + step_text
            safe_addstr(scr, y, x, line, curses.color_pair(COLOR_STEP) | curses.A_DIM)
            y += 1

        # Show current step (highlighted)
        current = self.splash.current_step()
        if current:
            prefix = "  → "
            # Use smart_text for current step (may have long filenames)
            step_text = smart_text(current, screen_w, x + len(prefix), margin=1)
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

    def _render_shimmer_text(self, scr, y: int, x: int, text: str, frame: int,
                              color: int, wavelength: float = 8.0, speed: float = 0.5):
        """
        Render text with a traveling shimmer wave effect.
        Characters ripple between bright and dim states.
        """
        shimmer = wave_shimmer(text, frame, wavelength, speed)
        for i, (char, is_bright) in enumerate(shimmer):
            if is_bright:
                attr = curses.A_BOLD | curses.color_pair(color)
            else:
                attr = curses.A_DIM | curses.color_pair(color)
            safe_addstr(scr, y, x + i, char, attr)

    def render_tips_page(self, scr, screen_h: int, screen_w: int, opacity: float = 1.0):
        """
        Render dedicated tips/tutorial page after loading.

        Args:
            scr: curses screen
            screen_h, screen_w: screen dimensions
            opacity: 0.0 (invisible) to 1.0 (fully visible), default 1.0
        """
        if opacity < 0.1:
            scr.erase()
            return

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
        header_attr = opacity_to_attr(opacity, curses.color_pair(COLOR_TAGLINE))
        safe_addstr(scr, y, max(0, x), header, header_attr)
        y += 2

        # Draw single-line box around tip
        box_width = min(60, screen_w - 4)
        box_x = (screen_w - box_width) // 2
        box_attr = opacity_to_attr(opacity * 0.7, curses.color_pair(COLOR_SUBTITLE))

        # Top border
        safe_addstr(scr, y, box_x, "┌" + "─" * (box_width - 2) + "┐", box_attr)
        y += 1

        # Tip title
        title_attr = opacity_to_attr(opacity, curses.color_pair(COLOR_LOGO))
        safe_addstr(scr, y, box_x, "│", box_attr)
        safe_addstr(scr, y, box_x + 2, tip.title, title_attr)
        safe_addstr(scr, y, box_x + box_width - 1, "│", box_attr)
        y += 1

        # Separator
        safe_addstr(scr, y, box_x, "├" + "─" * (box_width - 2) + "┤", box_attr)
        y += 1

        # Tip content (wrap if needed)
        content = tip.content
        content_width = box_width - 4
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

        content_attr = opacity_to_attr(opacity * 0.9, curses.color_pair(7))
        for line in lines[:3]:
            safe_addstr(scr, y, box_x, "│", box_attr)
            safe_addstr(scr, y, box_x + 2, line, content_attr)
            safe_addstr(scr, y, box_x + box_width - 1, "│", box_attr)
            y += 1

        # Fill remaining space
        for _ in range(3 - len(lines[:3])):
            safe_addstr(scr, y, box_x, "│", box_attr)
            safe_addstr(scr, y, box_x + box_width - 1, "│", box_attr)
            y += 1

        # Shortcut or command line
        if tip.shortcut:
            shortcut_text = f"Shortcut: {tip.shortcut}"
        elif tip.command:
            shortcut_text = f"Command: {tip.command}"
        else:
            shortcut_text = ""
        safe_addstr(scr, y, box_x, "│", box_attr)
        if shortcut_text:
            shortcut_attr = opacity_to_attr(opacity * 0.9, curses.color_pair(COLOR_TIP))
            safe_addstr(scr, y, box_x + 2, shortcut_text, shortcut_attr)
        safe_addstr(scr, y, box_x + box_width - 1, "│", box_attr)
        y += 1

        # Bottom border
        safe_addstr(scr, y, box_x, "└" + "─" * (box_width - 2) + "┘", box_attr)
        y += 2

        # Progress indicator (hide at low opacity)
        if opacity > 0.4:
            current_idx = self.splash.startup.current_tip_index + 1
            total_tips = len(STARTUP_TIPS)
            progress = f"◀  Tip {current_idx} of {total_tips}  ▶"
            x = (screen_w - len(progress)) // 2
            progress_attr = opacity_to_attr(opacity * 0.8, curses.color_pair(COLOR_SUBTITLE))
            safe_addstr(scr, y, max(0, x), progress, progress_attr)
            y += 2

            # Navigation hint
            hint = "Enter to continue  ←/→ browse tips"
            x = (screen_w - len(hint)) // 2
            hint_attr = opacity_to_attr(opacity * 0.9, curses.color_pair(COLOR_TAGLINE))
            safe_addstr(scr, y, max(0, x), hint, hint_attr)

        scr.refresh()


    def render_logo_only(self, scr, screen_h: int, screen_w: int, opacity: float = 1.0):
        """
        Render just the tau logo centered on screen.

        Used during transition from tips to main layout.

        Args:
            scr: curses screen
            screen_h, screen_w: screen dimensions
            opacity: 0.0 (invisible) to 1.0 (fully visible)
        """
        if opacity < 0.1:
            scr.erase()
            return

        scr.erase()

        # Use Logo class if initialized (enables BPM sync, shimmer, etc.)
        if self.splash.logo is not None:
            self.splash.logo.render(scr,
                                   opacity=opacity,
                                   screen_h=screen_h,
                                   screen_w=screen_w,
                                   center=True,
                                   show_text=True)
            scr.refresh()
            return

        # Fallback to legacy rendering
        # Select logo based on screen size
        if screen_w >= 35 and screen_h >= 15:
            logo = self.splash.get_logo_frame()
        else:
            logo = LOGO_SMALL

        # Calculate centering
        logo_height = len(logo)
        logo_width = max(len(line) for line in logo) if logo else 0

        start_y = (screen_h - logo_height) // 2
        start_x = (screen_w - logo_width) // 2

        # Draw logo with opacity-based attributes
        logo_attr = opacity_to_attr(opacity, curses.color_pair(COLOR_LOGO))
        for i, line in enumerate(logo):
            y = start_y + i
            x = start_x
            if 0 <= y < screen_h:
                safe_addstr(scr, y, max(0, x), line[:screen_w], logo_attr)

        # Draw tagline below logo (hide at low opacity)
        if opacity > 0.3:
            tagline_y = start_y + logo_height + 1
            tagline_x = (screen_w - len(TAGLINE)) // 2
            tagline_attr = opacity_to_attr(opacity * 0.9, curses.color_pair(COLOR_TAGLINE))
            safe_addstr(scr, tagline_y, max(0, tagline_x), TAGLINE, tagline_attr)

            # Draw subtitle
            subtitle_y = tagline_y + 1
            subtitle_x = (screen_w - len(SUBTITLE)) // 2
            subtitle_attr = opacity_to_attr(opacity * 0.8, curses.color_pair(COLOR_SUBTITLE))
            safe_addstr(scr, subtitle_y, max(0, subtitle_x), SUBTITLE, subtitle_attr)

            # Draw version
            version_y = subtitle_y + 1
            version_x = (screen_w - len(VERSION)) // 2
            version_attr = opacity_to_attr(opacity * 0.7, curses.color_pair(COLOR_SUBTITLE))
            safe_addstr(scr, version_y, max(0, version_x), VERSION, version_attr)

        scr.refresh()

def render_splash(scr, splash_state: SplashState, screen_h: int, screen_w: int):
    """Convenience function to render splash screen."""
    renderer = SplashRenderer(splash_state)
    renderer.render(scr, screen_h, screen_w)
