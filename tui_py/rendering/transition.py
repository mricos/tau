"""
Startup transition state machine for tau TUI.

Manages the transition sequence:
1. Tips fade out (200ms)
2. Logo fades in (200ms)
3. Logo on + Main fades in (3s) - both visible, main fades in behind logo
4. Logo fades out (200ms) - main fully visible
"""

import time
from typing import Optional


class StartupTransitionState:
    """
    Complete state machine for startup transitions.

    Sequence:
    1. Tips fade out (200ms)
    2. Logo fades in (200ms)
    3. Logo on + Main fades in (3s) - both pages visible
    4. Logo fades out (200ms) - main fully revealed
    """

    def __init__(self):
        self.phase = "idle"  # idle, tips_out, logo_in, logo_on, logo_out, done
        self.phase_start: Optional[float] = None

        # Timing configuration
        self.tips_out_duration = 0.2      # Tips fade out fast (200ms)
        self.logo_in_duration = 0.2       # Logo appears fast (200ms)
        self.logo_on_duration = 3.0       # Logo on, main fades in behind (3s)
        self.logo_out_duration = 0.2      # Logo fades out fast (200ms)

        self.main_ready = False

    def trigger_tips_exit(self):
        """User pressed Enter on tips page - start the sequence."""
        if self.phase == "idle":
            self.phase = "tips_out"
            self.phase_start = time.time()

    def _get_phase_progress(self) -> float:
        """Get progress (0.0-1.0) within current phase."""
        if self.phase_start is None:
            return 0.0

        elapsed = time.time() - self.phase_start

        if self.phase == "tips_out":
            return min(1.0, elapsed / self.tips_out_duration)
        elif self.phase == "logo_in":
            return min(1.0, elapsed / self.logo_in_duration)
        elif self.phase == "logo_on":
            return min(1.0, elapsed / self.logo_on_duration)
        elif self.phase == "logo_out":
            return min(1.0, elapsed / self.logo_out_duration)
        return 0.0

    def update(self):
        """Update state machine. Call each frame."""
        if self.phase == "done" or self.phase == "idle":
            return

        progress = self._get_phase_progress()

        if progress >= 1.0:
            # Advance to next phase
            if self.phase == "tips_out":
                self.phase = "logo_in"
                self.phase_start = time.time()
            elif self.phase == "logo_in":
                self.phase = "logo_on"
                self.phase_start = time.time()
            elif self.phase == "logo_on":
                self.phase = "logo_out"
                self.phase_start = time.time()
            elif self.phase == "logo_out":
                self.phase = "done"
                self.main_ready = True

    def get_tips_opacity(self) -> float:
        """Get opacity for tips page."""
        if self.phase == "idle":
            return 1.0
        elif self.phase == "tips_out":
            return 1.0 - self._get_phase_progress()
        return 0.0

    def get_logo_opacity(self) -> float:
        """Get opacity for logo."""
        if self.phase in ("idle", "tips_out"):
            return 0.0
        elif self.phase == "logo_in":
            return self._get_phase_progress()
        elif self.phase == "logo_on":
            return 1.0  # Full opacity while main fades in behind
        elif self.phase == "logo_out":
            return 1.0 - self._get_phase_progress()
        return 0.0

    def get_main_opacity(self) -> float:
        """Get opacity for main interface."""
        # Main fades in during logo_on (3 seconds)
        if self.phase == "logo_on":
            return self._get_phase_progress()  # 0.0 -> 1.0 over 3 seconds
        elif self.phase == "logo_out":
            return 1.0  # Fully visible, logo fades out
        elif self.phase == "done":
            return 1.0
        return 0.0

    def is_transitioning(self) -> bool:
        """Check if any transition is in progress."""
        return self.phase not in ("idle", "done")

    def is_main_ready(self) -> bool:
        """Check if main layout is ready to take over."""
        return self.main_ready
