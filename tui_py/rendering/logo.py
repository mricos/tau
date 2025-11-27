"""
Logo class for tau TUI.

A general-purpose dynamic rendering element that is BPM-aware.
Captures the T-to-Tau transition with fine-grained animation control,
design tokens, and compositable rendering for placement anywhere on screen.
"""

import curses
import math
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable
from enum import Enum, auto


# =============================================================================
# DESIGN TOKENS - Artistic/style configuration
# =============================================================================

@dataclass
class LogoColorScheme:
    """Color scheme tokens for the logo."""
    primary: int = 4        # Main logo color (Orange/MODE)
    secondary: int = 9      # Tagline color (Green/SUCCESS)
    tertiary: int = 7       # Subtitle/muted (Gray)
    accent: int = 1         # Highlight/attention (Amber)
    info: int = 12          # Informational (Blue)


@dataclass
class LogoTypography:
    """Typography tokens for logo text elements."""
    tagline: str = "Terminal Audio Workstation"
    subtitle: str = "Neural Network Kernel Tuning"
    version: str = "v0.0.1"

    # Spacing
    tagline_gap: int = 1      # Lines between logo and tagline
    subtitle_gap: int = 0     # Lines between tagline and subtitle
    version_gap: int = 0      # Lines between subtitle and version


@dataclass
class LogoAnimation:
    """Animation timing tokens."""
    # Morph timing (T <-> tau)
    morph_duration_ms: int = 800
    morph_hold_ms: int = 1000

    # Fade timing
    fade_in_ms: int = 200
    fade_out_ms: int = 200

    # BPM sync settings
    beat_pulse_duration_ms: int = 100   # Duration of beat pulse effect
    beat_scale_factor: float = 1.1      # Scale on beat (1.0 = no change)
    beat_brightness_boost: float = 0.3  # Brightness increase on beat

    # Shimmer effect
    shimmer_wavelength: float = 8.0
    shimmer_speed: float = 0.5
    shimmer_enabled: bool = True


@dataclass
class LogoDesignTokens:
    """Complete design token set for the logo."""
    colors: LogoColorScheme = field(default_factory=LogoColorScheme)
    typography: LogoTypography = field(default_factory=LogoTypography)
    animation: LogoAnimation = field(default_factory=LogoAnimation)

    # Layout
    min_width: int = 35       # Minimum width for full logo
    min_height: int = 15      # Minimum height for full logo
    padding_x: int = 2        # Horizontal padding
    padding_y: int = 1        # Vertical padding


# =============================================================================
# LOGO ART - ASCII art frames
# =============================================================================

# Small logo for constrained terminals
LOGO_SMALL = [
    "  TAU  ",
    "  ╦╔═╗╦ ╦  ",
    "  ║╠═╣║ ║  ",
    "  ╩╩ ╩╚═╝  ",
]

# Medium logo - block style
LOGO_MEDIUM = [
    "  ████████╗ █████╗ ██╗   ██╗  ",
    "  ╚══██╔══╝██╔══██╗██║   ██║  ",
    "     ██║   ███████║██║   ██║  ",
    "     ██║   ██╔══██║██║   ██║  ",
    "     ██║   ██║  ██║╚██████╔╝  ",
    "     ╚═╝   ╚═╝  ╚═╝ ╚═════╝   ",
]

# T morph frames (T -> tau/7 shape)
# The T progressively angles its stem to form tau (τ)
T_MORPH_FRAMES = [
    # Frame 0: Full T
    [
        "  ████████╗ ",
        "  ╚══██╔══╝ ",
        "     ██║    ",
        "     ██║    ",
        "     ██║    ",
        "     ╚═╝    ",
    ],
    # Frame 1: T loosening
    [
        "  ████████╗ ",
        "     ██╔══╝ ",
        "     ██║    ",
        "     ██║    ",
        "     ██║    ",
        "     ╚═╝    ",
    ],
    # Frame 2: Stem starting to angle
    [
        "  ████████╗ ",
        "     ██╔╝   ",
        "     ██║    ",
        "     ██║    ",
        "    ██╔╝    ",
        "    ╚═╝     ",
    ],
    # Frame 3: More angled
    [
        "  ████████╗ ",
        "      ██╔╝  ",
        "     ██╔╝   ",
        "     ██║    ",
        "    ██╔╝    ",
        "    ╚═╝     ",
    ],
    # Frame 4: Tau shape
    [
        "  ████████╗ ",
        "      ██╔╝  ",
        "     ██╔╝   ",
        "    ██╔╝    ",
        "   ██╔╝     ",
        "   ╚═╝      ",
    ],
    # Frame 5: Final tau (τ) - stem reaches toward A
    [
        "  ████████╗ ",
        "       ██╔╝ ",
        "      ██╔╝  ",
        "     ██╔╝   ",
        "    ██╔╝    ",
        "   ╚═╝      ",
    ],
]

# A and U remain static during morph
AU_STATIC = [
    " █████╗ ██╗   ██╗  ",
    "██╔══██╗██║   ██║  ",
    "███████║██║   ██║  ",
    "██╔══██║██║   ██║  ",
    "██║  ██║╚██████╔╝  ",
    "╚═╝  ╚═╝ ╚═════╝   ",
]


class LogoVariant(Enum):
    """Available logo style variants."""
    SMALL = auto()
    MEDIUM = auto()
    T_ONLY = auto()       # Just the T (for morph)
    TAU_ONLY = auto()     # Just tau symbol


class MorphDirection(Enum):
    """Direction of T <-> tau morph."""
    TO_TAU = auto()       # T -> tau
    TO_T = auto()         # tau -> T


# =============================================================================
# BPM SYNC - Beat-aware timing
# =============================================================================

@dataclass
class BPMState:
    """
    BPM synchronization state.

    Allows the logo to pulse, flash, or animate in sync with detected tempo.
    """
    bpm: float = 120.0              # Current BPM (default 120)
    beat_phase: float = 0.0         # Current phase within beat (0.0-1.0)
    last_beat_time: float = 0.0     # Time of last beat
    enabled: bool = False           # Is BPM sync active

    # Beat subdivision
    subdivision: int = 1            # 1 = quarter, 2 = eighth, 4 = sixteenth

    # Sync source
    source: str = "manual"          # "manual", "detected", "external"

    def set_bpm(self, bpm: float, source: str = "manual"):
        """Set BPM value."""
        self.bpm = max(1.0, min(300.0, bpm))  # Clamp to reasonable range
        self.source = source
        self.enabled = True

    def beat_interval_ms(self) -> float:
        """Get milliseconds per beat (considering subdivision)."""
        if self.bpm <= 0:
            return 1000.0
        return (60000.0 / self.bpm) / self.subdivision

    def update(self, current_time: float) -> bool:
        """
        Update beat phase. Returns True if a new beat occurred.

        Call this each frame with current time.
        """
        if not self.enabled or self.bpm <= 0:
            return False

        beat_interval_sec = self.beat_interval_ms() / 1000.0
        elapsed = current_time - self.last_beat_time

        # Update phase
        self.beat_phase = (elapsed / beat_interval_sec) % 1.0

        # Check for new beat
        if elapsed >= beat_interval_sec:
            self.last_beat_time = current_time
            return True

        return False

    def get_pulse_intensity(self, decay_rate: float = 4.0) -> float:
        """
        Get current beat pulse intensity (0.0-1.0).

        Starts at 1.0 on beat, decays exponentially.
        decay_rate controls how fast the pulse fades (higher = faster).
        """
        if not self.enabled:
            return 0.0

        # Exponential decay from beat
        return math.exp(-decay_rate * self.beat_phase)

    def is_on_beat(self, tolerance: float = 0.05) -> bool:
        """Check if we're within tolerance of a beat."""
        return self.beat_phase < tolerance or self.beat_phase > (1.0 - tolerance)


# =============================================================================
# LOGO STATE - Animation and rendering state
# =============================================================================

@dataclass
class LogoState:
    """
    Complete state for logo animation and rendering.
    """
    # Position (can be relative or absolute)
    x: int = 0
    y: int = 0
    anchor: str = "center"          # "center", "top-left", "top-right", etc.

    # Visibility
    opacity: float = 1.0            # 0.0 = invisible, 1.0 = fully visible
    visible: bool = True

    # Morph animation state
    morph_frame: int = 0            # Current frame index (0-5)
    morph_target: str = "t"         # Target state: "t" or "tau"
    morph_active: bool = False      # Is morph animation running
    morph_start_time: float = 0.0

    # BPM state
    bpm: BPMState = field(default_factory=BPMState)

    # Animation frame counter (for shimmer, etc.)
    frame_count: int = 0
    start_time: float = field(default_factory=time.time)

    # Variant selection
    variant: LogoVariant = LogoVariant.MEDIUM

    # Effect states
    pulse_intensity: float = 0.0    # Current beat pulse (0-1)
    shimmer_offset: float = 0.0     # Current shimmer phase


# =============================================================================
# LOGO CLASS - Main interface
# =============================================================================

class Logo:
    """
    General-purpose dynamic logo rendering element.

    Features:
    - T <-> tau morphing animation
    - BPM-synchronized effects (pulse, shimmer)
    - Opacity-based fading
    - Compositable rendering (place anywhere)
    - Design tokens for styling

    Usage:
        logo = Logo()
        logo.set_bpm(120)
        logo.trigger_morph()  # Start T -> tau animation

        # In render loop:
        logo.update(time.time())
        logo.render(scr, x, y, opacity=0.8)
    """

    def __init__(self, tokens: LogoDesignTokens = None):
        """Initialize logo with optional custom design tokens."""
        self.tokens = tokens or LogoDesignTokens()
        self.state = LogoState()

    # -------------------------------------------------------------------------
    # Configuration
    # -------------------------------------------------------------------------

    def set_bpm(self, bpm: float, source: str = "manual"):
        """Set BPM for synchronized animations."""
        self.state.bpm.set_bpm(bpm, source)

    def set_beat_subdivision(self, subdivision: int):
        """Set beat subdivision (1=quarter, 2=eighth, 4=sixteenth)."""
        self.state.bpm.subdivision = max(1, min(16, subdivision))

    def enable_bpm_sync(self, enabled: bool = True):
        """Enable/disable BPM synchronization."""
        self.state.bpm.enabled = enabled

    def set_variant(self, variant: LogoVariant):
        """Set logo variant (SMALL, MEDIUM, T_ONLY, TAU_ONLY)."""
        self.state.variant = variant

    def set_position(self, x: int, y: int, anchor: str = "center"):
        """Set logo position with anchor point."""
        self.state.x = x
        self.state.y = y
        self.state.anchor = anchor

    def set_opacity(self, opacity: float):
        """Set logo opacity (0.0-1.0)."""
        self.state.opacity = max(0.0, min(1.0, opacity))

    def set_visible(self, visible: bool):
        """Set logo visibility."""
        self.state.visible = visible

    # -------------------------------------------------------------------------
    # Animation Control
    # -------------------------------------------------------------------------

    def trigger_morph(self, direction: MorphDirection = None):
        """
        Trigger T <-> tau morph animation.

        If direction is None, toggles between T and tau.
        """
        if self.state.morph_active:
            return  # Already animating

        self.state.morph_active = True
        self.state.morph_start_time = time.time()

        if direction is None:
            # Toggle
            self.state.morph_target = "tau" if self.state.morph_target == "t" else "t"
        elif direction == MorphDirection.TO_TAU:
            self.state.morph_target = "tau"
        else:
            self.state.morph_target = "t"

    def set_morph_state(self, target: str):
        """
        Immediately set morph state without animation.

        Args:
            target: "t" or "tau"
        """
        self.state.morph_target = target
        self.state.morph_active = False
        if target == "t":
            self.state.morph_frame = 0
        else:
            self.state.morph_frame = len(T_MORPH_FRAMES) - 1

    def trigger_beat_pulse(self):
        """Manually trigger a beat pulse (for external sync)."""
        self.state.bpm.last_beat_time = time.time()
        self.state.bpm.beat_phase = 0.0

    # -------------------------------------------------------------------------
    # Update (call each frame)
    # -------------------------------------------------------------------------

    def update(self, current_time: float = None) -> dict:
        """
        Update animation state.

        Call this each frame before rendering.

        Args:
            current_time: Current time in seconds (default: time.time())

        Returns:
            Dict with events: {"beat": bool, "morph_complete": bool}
        """
        if current_time is None:
            current_time = time.time()

        events = {"beat": False, "morph_complete": False}

        # Update frame counter
        self.state.frame_count += 1

        # Update BPM state
        if self.state.bpm.enabled:
            events["beat"] = self.state.bpm.update(current_time)
            self.state.pulse_intensity = self.state.bpm.get_pulse_intensity()

        # Update shimmer
        if self.tokens.animation.shimmer_enabled:
            elapsed = current_time - self.state.start_time
            self.state.shimmer_offset = elapsed * self.tokens.animation.shimmer_speed

        # Update morph animation
        if self.state.morph_active:
            events["morph_complete"] = self._update_morph(current_time)

        return events

    def _update_morph(self, current_time: float) -> bool:
        """Update morph animation. Returns True when complete."""
        duration_sec = self.tokens.animation.morph_duration_ms / 1000.0
        elapsed = current_time - self.state.morph_start_time
        progress = min(1.0, elapsed / duration_sec)

        total_frames = len(T_MORPH_FRAMES)

        if self.state.morph_target == "tau":
            # T -> tau: frames 0 -> N
            self.state.morph_frame = int(progress * (total_frames - 1))
        else:
            # tau -> T: frames N -> 0
            self.state.morph_frame = total_frames - 1 - int(progress * (total_frames - 1))

        # Clamp
        self.state.morph_frame = max(0, min(total_frames - 1, self.state.morph_frame))

        # Check completion
        if progress >= 1.0:
            self.state.morph_active = False
            return True

        return False

    # -------------------------------------------------------------------------
    # Logo Frame Generation
    # -------------------------------------------------------------------------

    def get_frame(self) -> List[str]:
        """
        Get current logo frame as list of strings.

        Returns the appropriate logo variant with current morph state.
        """
        variant = self.state.variant

        if variant == LogoVariant.SMALL:
            return LOGO_SMALL.copy()

        elif variant == LogoVariant.T_ONLY:
            return T_MORPH_FRAMES[self.state.morph_frame].copy()

        elif variant == LogoVariant.TAU_ONLY:
            return T_MORPH_FRAMES[-1].copy()  # Final tau frame

        else:  # MEDIUM (default)
            # Combine morphing T with static AU
            t_frame = T_MORPH_FRAMES[self.state.morph_frame]
            combined = []
            for i, t_line in enumerate(t_frame):
                combined.append(t_line + AU_STATIC[i])
            return combined

    def get_dimensions(self) -> Tuple[int, int]:
        """Get (width, height) of current logo frame."""
        frame = self.get_frame()
        if not frame:
            return (0, 0)
        height = len(frame)
        width = max(len(line) for line in frame)
        return (width, height)

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def render(self, scr, x: int = None, y: int = None,
               opacity: float = None,
               show_text: bool = True,
               center: bool = True,
               screen_w: int = None,
               screen_h: int = None):
        """
        Render logo to curses screen.

        Args:
            scr: Curses screen/window
            x, y: Position (optional, uses state if not provided)
            opacity: Override opacity (optional)
            show_text: Show tagline/subtitle/version
            center: Center horizontally if x not provided
            screen_w, screen_h: Screen dimensions (for centering)
        """
        if not self.state.visible:
            return

        # Get dimensions if not provided
        if screen_h is None or screen_w is None:
            try:
                screen_h, screen_w = scr.getmaxyx()
            except:
                return

        # Determine opacity
        op = opacity if opacity is not None else self.state.opacity
        if op < 0.1:
            return

        # Get logo frame
        frame = self.get_frame()
        if not frame:
            return

        logo_w, logo_h = self.get_dimensions()

        # Calculate position
        if center and x is None:
            start_x = (screen_w - logo_w) // 2
        else:
            start_x = x if x is not None else self.state.x

        if y is None:
            if center:
                total_height = logo_h
                if show_text:
                    total_height += 4  # tagline + subtitle + version + gaps
                start_y = (screen_h - total_height) // 2
            else:
                start_y = self.state.y
        else:
            start_y = y

        # Apply anchor offset
        start_x, start_y = self._apply_anchor(start_x, start_y, logo_w, logo_h)

        # Calculate attribute based on opacity and pulse
        base_attr = self._get_base_attr(op)

        # Render logo lines
        current_y = start_y
        for line in frame:
            if 0 <= current_y < screen_h:
                self._render_line(scr, current_y, start_x, line, base_attr, op, screen_w)
            current_y += 1

        # Render text elements
        if show_text and op > 0.3:
            current_y = self._render_text_elements(scr, current_y, screen_w, op)

    def _apply_anchor(self, x: int, y: int, w: int, h: int) -> Tuple[int, int]:
        """Apply anchor offset to position."""
        anchor = self.state.anchor

        if "center" in anchor:
            x -= w // 2
            y -= h // 2
        elif "right" in anchor:
            x -= w

        if "bottom" in anchor:
            y -= h

        return (x, y)

    def _get_base_attr(self, opacity: float) -> int:
        """Get base curses attribute for given opacity and pulse state."""
        color = self.tokens.colors.primary
        base = curses.color_pair(color)

        # Apply pulse brightness boost
        if self.state.pulse_intensity > 0.1:
            return base | curses.A_BOLD

        # Apply opacity-based attribute
        if opacity < 0.3:
            return base | curses.A_DIM
        elif opacity > 0.8:
            return base | curses.A_BOLD

        return base

    def _render_line(self, scr, y: int, x: int, line: str,
                     base_attr: int, opacity: float, screen_w: int):
        """Render a single line with optional shimmer effect."""
        if self.tokens.animation.shimmer_enabled and opacity > 0.5:
            # Shimmer: per-character brightness variation
            self._render_shimmer_line(scr, y, x, line, base_attr, screen_w)
        else:
            # Simple render
            try:
                if x < 0:
                    line = line[-x:]
                    x = 0
                if x + len(line) > screen_w:
                    line = line[:screen_w - x]
                scr.addstr(y, x, line, base_attr)
            except curses.error:
                pass

    def _render_shimmer_line(self, scr, y: int, x: int, line: str,
                              base_attr: int, screen_w: int):
        """Render line with traveling shimmer wave."""
        wavelength = self.tokens.animation.shimmer_wavelength
        phase = self.state.shimmer_offset
        color = self.tokens.colors.primary

        for i, char in enumerate(line):
            char_x = x + i
            if char_x < 0 or char_x >= screen_w:
                continue

            # Sine wave determines brightness
            wave_val = math.sin((i / wavelength) * 2 * math.pi - phase)

            if wave_val > 0.0:
                attr = curses.A_BOLD | curses.color_pair(color)
            else:
                attr = curses.A_DIM | curses.color_pair(color)

            # Boost on beat pulse
            if self.state.pulse_intensity > 0.5:
                attr = curses.A_BOLD | curses.color_pair(color)

            try:
                scr.addstr(y, char_x, char, attr)
            except curses.error:
                pass

    def _render_text_elements(self, scr, y: int, screen_w: int, opacity: float) -> int:
        """Render tagline, subtitle, and version. Returns final y position."""
        typo = self.tokens.typography
        colors = self.tokens.colors

        y += typo.tagline_gap

        # Tagline
        if typo.tagline and opacity > 0.4:
            attr = self._opacity_to_attr(opacity, colors.secondary)
            x = (screen_w - len(typo.tagline)) // 2
            try:
                scr.addstr(y, max(0, x), typo.tagline, attr)
            except curses.error:
                pass
            y += 1

        y += typo.subtitle_gap

        # Subtitle
        if typo.subtitle and opacity > 0.3:
            attr = self._opacity_to_attr(opacity * 0.8, colors.tertiary) | curses.A_DIM
            x = (screen_w - len(typo.subtitle)) // 2
            try:
                scr.addstr(y, max(0, x), typo.subtitle, attr)
            except curses.error:
                pass
            y += 1

        y += typo.version_gap

        # Version
        if typo.version and opacity > 0.2:
            attr = self._opacity_to_attr(opacity * 0.7, colors.tertiary) | curses.A_DIM
            x = (screen_w - len(typo.version)) // 2
            try:
                scr.addstr(y, max(0, x), typo.version, attr)
            except curses.error:
                pass
            y += 1

        return y

    def _opacity_to_attr(self, opacity: float, color: int) -> int:
        """Convert opacity to curses attribute with color."""
        base = curses.color_pair(color)
        if opacity < 0.3:
            return base | curses.A_DIM
        elif opacity > 0.8:
            return base | curses.A_BOLD
        return base

    # -------------------------------------------------------------------------
    # Composite Rendering (for scene compositor)
    # -------------------------------------------------------------------------

    def render_composite(self, scr, height: int, width: int, opacity: float):
        """
        Render function for use with SceneCompositor.

        Matches the signature expected by SceneCompositor.set_layer_render().
        """
        self.render(scr,
                   opacity=opacity,
                   screen_h=height,
                   screen_w=width,
                   center=True,
                   show_text=True)

    def get_composite_render(self) -> Callable:
        """
        Get a render function suitable for SceneCompositor.

        Usage:
            compositor.set_layer_render('logo', logo.get_composite_render())
        """
        return self.render_composite

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------

    def get_state_snapshot(self) -> dict:
        """Get current state as dictionary (for debugging/serialization)."""
        return {
            "variant": self.state.variant.name,
            "opacity": self.state.opacity,
            "visible": self.state.visible,
            "morph_frame": self.state.morph_frame,
            "morph_target": self.state.morph_target,
            "morph_active": self.state.morph_active,
            "bpm": {
                "enabled": self.state.bpm.enabled,
                "bpm": self.state.bpm.bpm,
                "subdivision": self.state.bpm.subdivision,
                "beat_phase": self.state.bpm.beat_phase,
            },
            "pulse_intensity": self.state.pulse_intensity,
            "frame_count": self.state.frame_count,
        }


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

def create_logo(bpm: float = None, variant: LogoVariant = LogoVariant.MEDIUM) -> Logo:
    """
    Factory function to create a Logo instance.

    Args:
        bpm: Optional BPM for synchronized effects
        variant: Logo variant (SMALL, MEDIUM, T_ONLY, TAU_ONLY)

    Returns:
        Configured Logo instance
    """
    logo = Logo()
    logo.set_variant(variant)

    if bpm is not None:
        logo.set_bpm(bpm)
        logo.enable_bpm_sync(True)

    return logo


def create_splash_logo() -> Logo:
    """Create a logo configured for splash screen use."""
    return create_logo(variant=LogoVariant.MEDIUM)


def create_compact_logo(bpm: float = None) -> Logo:
    """Create a compact logo for constrained spaces."""
    return create_logo(bpm=bpm, variant=LogoVariant.SMALL)
