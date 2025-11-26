"""
Performance monitor for tau TUI.
Tracks memory usage, frame rate, and system resources.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Deque
from collections import deque


@dataclass
class PerfStats:
    """Performance statistics."""
    # Memory (in MB)
    memory_mb: float = 0.0
    memory_peak_mb: float = 0.0

    # Frame timing
    frame_times: Deque[float] = field(default_factory=lambda: deque(maxlen=60))
    last_frame_time: float = 0.0
    fps: float = 0.0

    # Section timing (for finding bottlenecks)
    section_times: dict = field(default_factory=dict)

    # Object counts (for debugging leaks)
    object_counts: dict = field(default_factory=dict)

    # Update interval
    last_update: float = 0.0
    update_interval: float = 0.5  # Update stats every 0.5 seconds


class PerfMonitor:
    """
    Lightweight performance monitor.

    Usage:
        monitor = PerfMonitor()
        # In render loop:
        monitor.frame_start()
        # ... render ...
        monitor.frame_end()
        stats = monitor.get_stats()
    """

    def __init__(self):
        self.stats = PerfStats()
        self._frame_start_time = 0.0
        self._section_start_time = 0.0
        self._current_section = None
        self._process = None

        # Try to get process handle for memory tracking
        try:
            import psutil
            self._process = psutil.Process(os.getpid())
        except ImportError:
            # psutil not available, use /proc on Linux or basic method
            self._process = None

    def section_start(self, name: str):
        """Start timing a section."""
        self._current_section = name
        self._section_start_time = time.perf_counter()

    def section_end(self):
        """End timing current section."""
        if self._current_section:
            elapsed = time.perf_counter() - self._section_start_time
            self.stats.section_times[self._current_section] = elapsed * 1000  # ms
            self._current_section = None

    def frame_start(self):
        """Mark start of frame."""
        self._frame_start_time = time.perf_counter()

    def frame_end(self):
        """Mark end of frame and update stats."""
        now = time.perf_counter()
        frame_time = now - self._frame_start_time
        self.stats.frame_times.append(frame_time)
        self.stats.last_frame_time = frame_time

        # Calculate FPS from recent frames
        if len(self.stats.frame_times) > 0:
            avg_frame_time = sum(self.stats.frame_times) / len(self.stats.frame_times)
            self.stats.fps = 1.0 / avg_frame_time if avg_frame_time > 0 else 0

        # Update memory stats periodically (expensive operation)
        if now - self.stats.last_update > self.stats.update_interval:
            self._update_memory_stats()
            self.stats.last_update = now

    def _update_memory_stats(self):
        """Update memory statistics."""
        if self._process:
            try:
                mem_info = self._process.memory_info()
                self.stats.memory_mb = mem_info.rss / (1024 * 1024)
                self.stats.memory_peak_mb = max(self.stats.memory_peak_mb, self.stats.memory_mb)
            except Exception:
                self._fallback_memory()
        else:
            self._fallback_memory()

    def _fallback_memory(self):
        """Fallback memory measurement without psutil."""
        try:
            # Try /proc/self/status on Linux
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        # Value is in kB
                        kb = int(line.split()[1])
                        self.stats.memory_mb = kb / 1024
                        self.stats.memory_peak_mb = max(self.stats.memory_peak_mb, self.stats.memory_mb)
                        return
        except (FileNotFoundError, IOError):
            pass

        # macOS fallback using resource module
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            # ru_maxrss is in bytes on macOS, kilobytes on Linux
            import sys
            if sys.platform == 'darwin':
                self.stats.memory_mb = usage.ru_maxrss / (1024 * 1024)
            else:
                self.stats.memory_mb = usage.ru_maxrss / 1024
            self.stats.memory_peak_mb = max(self.stats.memory_peak_mb, self.stats.memory_mb)
        except Exception:
            pass

    def track_object(self, name: str, count: int):
        """Track object count for leak detection."""
        self.stats.object_counts[name] = count

    def get_stats(self) -> PerfStats:
        """Get current statistics."""
        return self.stats

    def format_compact(self) -> str:
        """Format stats for compact display (header bar)."""
        mem = self.stats.memory_mb
        fps = self.stats.fps
        frame_ms = self.stats.last_frame_time * 1000

        # Find slowest section
        slowest = ""
        if self.stats.section_times:
            max_section = max(self.stats.section_times.items(), key=lambda x: x[1])
            if max_section[1] > 1.0:  # Only show if > 1ms
                slowest = f" [{max_section[0]}:{max_section[1]:.0f}]"

        if mem > 0:
            return f"{mem:.0f}MB {fps:.0f}fps {frame_ms:.0f}ms{slowest}"
        else:
            return f"{fps:.0f}fps {frame_ms:.0f}ms{slowest}"

    def format_detailed(self) -> str:
        """Format stats for detailed display."""
        lines = [
            f"Memory: {self.stats.memory_mb:.1f}MB (peak: {self.stats.memory_peak_mb:.1f}MB)",
            f"FPS: {self.stats.fps:.1f} (frame: {self.stats.last_frame_time*1000:.2f}ms)",
        ]
        if self.stats.object_counts:
            lines.append("Objects:")
            for name, count in self.stats.object_counts.items():
                lines.append(f"  {name}: {count}")
        return "\n".join(lines)


# Global instance for easy access
_monitor = None


def get_monitor() -> PerfMonitor:
    """Get or create global performance monitor."""
    global _monitor
    if _monitor is None:
        _monitor = PerfMonitor()
    return _monitor
