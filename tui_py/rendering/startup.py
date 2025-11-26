"""
Structured startup information and tutorial tips for tau TUI.

First-class citizen for startup experience - all tips, steps, and tutorial
content defined here in structured data.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class TipCategory(Enum):
    """Categories for organizing tips."""
    NAVIGATION = "navigation"
    PLAYBACK = "playback"
    CLI = "cli"
    LANES = "lanes"
    ZOOM = "zoom"
    VIDEO = "video"
    PROJECT = "project"
    KEYBOARD = "keyboard"
    ADVANCED = "advanced"


@dataclass
class StartupTip:
    """A single tip or 'did you know' item."""
    title: str                          # Short title (e.g., "CLI Mode")
    content: str                         # Full tip text
    category: TipCategory               # Category for filtering
    shortcut: Optional[str] = None      # Associated keyboard shortcut
    command: Optional[str] = None       # Associated CLI command
    priority: int = 50                  # 0-100, higher = shown earlier
    requires_feature: Optional[str] = None  # Feature flag required (e.g., "video")

    def format_short(self) -> str:
        """Format as short one-liner."""
        if self.shortcut:
            return f"{self.title}: Press '{self.shortcut}'"
        elif self.command:
            return f"{self.title}: Type '{self.command}'"
        return f"{self.title}: {self.content[:40]}..."

    def format_full(self) -> str:
        """Format with full details."""
        lines = [self.title, self.content]
        if self.shortcut:
            lines.append(f"Shortcut: {self.shortcut}")
        if self.command:
            lines.append(f"Command: {self.command}")
        return "\n".join(lines)


@dataclass
class StartupStep:
    """A single initialization step shown during loading."""
    id: str                             # Unique identifier
    message: str                        # Display message
    progress: float                     # Progress value (0.0-1.0) when complete
    detail: Optional[str] = None        # Optional detail text


@dataclass
class StartupConfig:
    """Configuration for startup behavior."""
    show_tips: bool = True              # Show tips during startup
    require_enter: bool = True          # Require Enter (not any key) to advance
    tips_per_page: int = 1              # Tips to show per page
    auto_advance: bool = False          # Auto-advance after delay (overridden if require_enter)
    auto_advance_delay: float = 3.0     # Seconds before auto-advance
    show_tutorial_on_first_run: bool = True  # Extended tutorial on first run
    tip_rotation_interval: float = 2.0  # Seconds between tip rotation


# ============================================================
# STARTUP TIPS DATABASE
# ============================================================

STARTUP_TIPS: List[StartupTip] = [
    # Navigation
    StartupTip(
        title="CLI Mode",
        content="Enter CLI mode to type commands and search. All tau functionality is accessible through commands.",
        category=TipCategory.CLI,
        shortcut=":",
        priority=100,
    ),
    StartupTip(
        title="Quick Help",
        content="See keyboard shortcuts and available commands at a glance.",
        category=TipCategory.KEYBOARD,
        shortcut="?",
        priority=95,
    ),
    StartupTip(
        title="Play/Pause",
        content="Toggle audio playback. Works in any mode.",
        category=TipCategory.PLAYBACK,
        shortcut="Space",
        priority=90,
    ),

    # Lanes
    StartupTip(
        title="Toggle Lanes",
        content="Show or hide individual data lanes. Each lane displays a different aspect of your audio analysis.",
        category=TipCategory.LANES,
        shortcut="1-8",
        priority=85,
    ),
    StartupTip(
        title="Events Lane",
        content="Lane 9 shows timestamped events. Add events with the 'event' command or by pressing 'e'.",
        category=TipCategory.LANES,
        shortcut="9",
        priority=70,
    ),
    StartupTip(
        title="Logs Lane",
        content="Lane 0 shows system logs and command output. Toggle visibility with '0'.",
        category=TipCategory.LANES,
        shortcut="0",
        priority=65,
    ),

    # Zoom
    StartupTip(
        title="Zoom Controls",
        content="Zoom in to see more detail, zoom out to see the full waveform.",
        category=TipCategory.ZOOM,
        shortcut="< >",
        priority=80,
    ),
    StartupTip(
        title="Fit to Screen",
        content="Automatically fit the entire waveform to the current screen width.",
        category=TipCategory.ZOOM,
        command="fit",
        priority=60,
    ),

    # Playback
    StartupTip(
        title="Scrub Position",
        content="Click or use arrow keys to move the playhead position.",
        category=TipCategory.PLAYBACK,
        shortcut="Left/Right",
        priority=75,
    ),
    StartupTip(
        title="Jump to Start",
        content="Return to the beginning of the audio file.",
        category=TipCategory.PLAYBACK,
        shortcut="Home",
        priority=55,
    ),

    # CLI Commands
    StartupTip(
        title="Load Audio",
        content="Load any audio file for analysis. Supports WAV, MP3, FLAC, and more.",
        category=TipCategory.CLI,
        command="load <filename>",
        priority=85,
    ),
    StartupTip(
        title="Quickstart Tutorial",
        content="Run the interactive tutorial to learn tau basics step by step.",
        category=TipCategory.CLI,
        command="quickstart",
        priority=92,
    ),
    StartupTip(
        title="Command Help",
        content="Get detailed help on any command including all options and examples.",
        category=TipCategory.CLI,
        command="help <command>",
        priority=70,
    ),

    # Project
    StartupTip(
        title="Save Session",
        content="Save your current session state including position, zoom, and lane visibility.",
        category=TipCategory.PROJECT,
        command="save",
        priority=50,
    ),
    StartupTip(
        title="Project Info",
        content="View information about the current project and session.",
        category=TipCategory.PROJECT,
        command="info",
        priority=45,
    ),

    # Video
    StartupTip(
        title="Video Mode",
        content="Enable ASCII video visualization of your waveform data.",
        category=TipCategory.VIDEO,
        command="video on",
        requires_feature="video",
        priority=40,
    ),
    StartupTip(
        title="Video Palettes",
        content="Switch between different ASCII art rendering styles.",
        category=TipCategory.VIDEO,
        command="palette <name>",
        requires_feature="video",
        priority=35,
    ),

    # Advanced
    StartupTip(
        title="Kernel Parameters",
        content="Adjust neural network kernel parameters (tau_a, tau_r) for different analysis characteristics.",
        category=TipCategory.ADVANCED,
        command="kernel",
        priority=30,
    ),
    StartupTip(
        title="OSC Integration",
        content="Connect to external applications via OSC for real-time parameter control.",
        category=TipCategory.ADVANCED,
        command="osc connect <host> <port>",
        priority=25,
    ),
    StartupTip(
        title="Export Data",
        content="Export analysis data in various formats for external processing.",
        category=TipCategory.ADVANCED,
        command="export",
        priority=20,
    ),
]


# ============================================================
# INITIALIZATION STEPS
# ============================================================

INIT_STEPS: List[StartupStep] = [
    StartupStep("project", "Initializing project...", 0.1),
    StartupStep("state", "Creating application state...", 0.2),
    StartupStep("video", "Detecting video features...", 0.25),
    StartupStep("cli", "Setting up CLI...", 0.3),
    StartupStep("commands", "Registering commands...", 0.4),
    StartupStep("input", "Setting up input handler...", 0.5),
    StartupStep("config", "Loading configuration...", 0.55),
    StartupStep("audio", "Loading audio...", 0.7),
    StartupStep("session", "Restoring session...", 0.85),
    StartupStep("ready", "Ready!", 1.0),
]


# ============================================================
# STARTUP STATE
# ============================================================

@dataclass
class StartupState:
    """
    Complete state for startup sequence.

    Combines loading progress, tips display, and tutorial state.
    """
    # Configuration
    config: StartupConfig = field(default_factory=StartupConfig)

    # Loading state
    current_step_index: int = 0
    steps: List[StartupStep] = field(default_factory=lambda: INIT_STEPS.copy())
    step_details: Dict[str, str] = field(default_factory=dict)

    # Tips state
    available_tips: List[StartupTip] = field(default_factory=list)
    current_tip_index: int = 0
    tip_display_time: float = 0.0

    # Navigation state
    waiting_for_enter: bool = False
    tips_acknowledged: int = 0
    total_tips_to_show: int = 3  # Tips to show before main interface

    # Feature flags (for filtering tips)
    features: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize available tips based on features."""
        self.refresh_tips()

    def refresh_tips(self):
        """Refresh available tips based on current features."""
        self.available_tips = [
            tip for tip in STARTUP_TIPS
            if tip.requires_feature is None or self.features.get(tip.requires_feature, False)
        ]
        # Sort by priority (highest first)
        self.available_tips.sort(key=lambda t: -t.priority)

    def set_feature(self, feature: str, enabled: bool):
        """Set a feature flag and refresh tips."""
        self.features[feature] = enabled
        self.refresh_tips()

    def get_current_tip(self) -> Optional[StartupTip]:
        """Get current tip to display."""
        if not self.config.show_tips or not self.available_tips:
            return None
        return self.available_tips[self.current_tip_index % len(self.available_tips)]

    def advance_tip(self):
        """Move to next tip."""
        if self.available_tips:
            self.current_tip_index = (self.current_tip_index + 1) % len(self.available_tips)
            self.tip_display_time = 0.0

    def acknowledge_tip(self) -> bool:
        """
        Acknowledge current tip (user pressed Enter).

        Returns True if all required tips acknowledged and ready to proceed.
        """
        self.tips_acknowledged += 1
        self.advance_tip()
        return self.tips_acknowledged >= self.total_tips_to_show

    def get_current_step(self) -> Optional[StartupStep]:
        """Get current initialization step."""
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def set_step_detail(self, step_id: str, detail: str):
        """Set detail text for a step (e.g., filename being loaded)."""
        self.step_details[step_id] = detail

    def get_step_message(self) -> str:
        """Get formatted message for current step."""
        step = self.get_current_step()
        if not step:
            return ""

        detail = self.step_details.get(step.id, step.detail)
        if detail:
            return f"{step.message} {detail}"
        return step.message

    def complete_step(self) -> float:
        """
        Complete current step and advance.

        Returns the progress value.
        """
        step = self.get_current_step()
        progress = step.progress if step else 1.0
        self.current_step_index += 1
        return progress

    def is_loading_complete(self) -> bool:
        """Check if all init steps are done."""
        return self.current_step_index >= len(self.steps)

    def should_show_tips(self) -> bool:
        """Check if tips phase should be shown."""
        return (
            self.config.show_tips and
            self.is_loading_complete() and
            self.tips_acknowledged < self.total_tips_to_show
        )


def get_tips_by_category(category: TipCategory) -> List[StartupTip]:
    """Get all tips in a category."""
    return [tip for tip in STARTUP_TIPS if tip.category == category]


def get_random_tip(exclude_indices: List[int] = None) -> Optional[StartupTip]:
    """Get a random tip, optionally excluding certain indices."""
    import random
    indices = list(range(len(STARTUP_TIPS)))
    if exclude_indices:
        indices = [i for i in indices if i not in exclude_indices]
    if not indices:
        return None
    return STARTUP_TIPS[random.choice(indices)]
