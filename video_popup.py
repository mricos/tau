"""
Video popup overlay for tau - full-screen ASCII video viewer.
"""

import curses
from typing import Optional
from .rendering.video import render_video_expanded, frame_to_ascii_stippled
from .rendering.helpers import safe_addstr


class VideoPopup:
    """
    Video popup overlay for expanded viewing.

    Displays video in a centered popup with stippled ASCII art.
    """

    def __init__(self, video_lane: Optional['VideoLane'] = None, resolution: tuple = (80, 40)):
        """
        Initialize video popup.

        Args:
            video_lane: VideoLane to display
            resolution: (width, height) for popup
        """
        self.video_lane = video_lane
        self.width, self.height = resolution
        self.visible = False

    def toggle(self):
        """Toggle popup visibility."""
        self.visible = not self.visible

    def set_video_lane(self, video_lane: 'VideoLane'):
        """Set video lane to display."""
        self.video_lane = video_lane

    def render(self, scr, transport: 'Transport', terminal_height: int, terminal_width: int):
        """
        Render popup overlay.

        Args:
            scr: curses screen
            transport: Transport for current position
            terminal_height: Terminal height
            terminal_width: Terminal width
        """
        if not self.visible or not self.video_lane:
            return

        # Calculate popup position (centered)
        popup_y = max(0, (terminal_height - self.height) // 2)
        popup_x = max(0, (terminal_width - self.width) // 2)

        # Clamp to terminal bounds
        popup_height = min(self.height, terminal_height - popup_y - 1)
        popup_width = min(self.width, terminal_width - popup_x - 1)

        # Draw border
        self._draw_border(scr, popup_y, popup_x, popup_height, popup_width)

        # Get current frame (from cached thumbnails)
        # For expanded view, we need higher resolution
        # Option 1: Use cached thumbnail (fast but low quality)
        # Option 2: Decode frame on-demand (slow but high quality)

        # For now, use cached thumbnail and upscale with stippling
        small_frame = self.video_lane.get_frame_at_time(transport.position)

        if small_frame:
            # Get full-resolution frame if possible (requires re-decoding)
            try:
                full_frame = self._decode_frame_at_time(transport.position)
                if full_frame is not None:
                    # Convert to stippled ASCII
                    stippled_frame = frame_to_ascii_stippled(
                        full_frame,
                        popup_width - 4,  # Leave margin for border
                        popup_height - 4
                    )
                    # Render expanded frame
                    render_video_expanded(
                        scr, stippled_frame,
                        popup_y + 2, popup_x + 2,
                        popup_width - 4, popup_height - 4,
                        color=5
                    )
                else:
                    # Fallback to small thumbnail (upscaled)
                    self._render_upscaled_thumbnail(
                        scr, small_frame,
                        popup_y + 2, popup_x + 2,
                        popup_width - 4, popup_height - 4
                    )
            except Exception as e:
                # Fallback to small thumbnail
                self._render_upscaled_thumbnail(
                    scr, small_frame,
                    popup_y + 2, popup_x + 2,
                    popup_width - 4, popup_height - 4
                )

            # Show info
            self._draw_info(scr, popup_y, popup_x, popup_width, transport)

    def _draw_border(self, scr, y: int, x: int, h: int, w: int):
        """Draw popup border."""
        # Top border
        safe_addstr(scr, y, x, "┌" + "─" * (w - 2) + "┐", curses.A_BOLD)
        # Side borders
        for i in range(1, h - 1):
            safe_addstr(scr, y + i, x, "│", curses.A_BOLD)
            safe_addstr(scr, y + i, x + w - 1, "│", curses.A_BOLD)
        # Bottom border
        safe_addstr(scr, y + h - 1, x, "└" + "─" * (w - 2) + "┘", curses.A_BOLD)

    def _draw_info(self, scr, y: int, x: int, w: int, transport: 'Transport'):
        """Draw video info in popup header."""
        if not self.video_lane or not self.video_lane.metadata:
            return

        meta = self.video_lane.metadata
        duration = meta.duration
        pos = transport.position
        pct = (pos / duration * 100) if duration > 0 else 0

        # Info string
        info = f" {meta.path.name} | {pos:.2f}s/{duration:.2f}s ({pct:.0f}%) | {meta.width}x{meta.height} {meta.fps:.0f}fps "
        info = info[:w-4]  # Truncate to fit

        # Render centered in top border
        info_x = x + (w - len(info)) // 2
        safe_addstr(scr, y, info_x, info, curses.A_BOLD | curses.color_pair(5))

        # Controls hint in bottom border
        hint = " [v] close | [space] play/pause | [←→] scrub "
        hint = hint[:w-4]
        hint_x = x + (w - len(hint)) // 2
        safe_addstr(scr, y + self.height - 1, hint_x, hint, curses.A_DIM)

    def _render_upscaled_thumbnail(self, scr, small_frame, y: int, x: int, width: int, height: int):
        """Render small thumbnail upscaled (simple repeat)."""
        if not small_frame:
            return

        # Simple upscaling: repeat characters
        small_height = len(small_frame)
        small_width = len(small_frame[0]) if small_frame else 0

        y_scale = height // small_height if small_height > 0 else 1
        x_scale = width // small_width if small_width > 0 else 1

        y_scale = max(1, y_scale)
        x_scale = max(1, x_scale)

        out_y = y
        for row in small_frame:
            for _ in range(y_scale):
                if out_y >= y + height:
                    break
                # Upscale horizontally
                upscaled_row = ''.join(ch * x_scale for ch in row)
                safe_addstr(scr, out_y, x, upscaled_row[:width], curses.color_pair(5))
                out_y += 1

    def _decode_frame_at_time(self, t: float):
        """
        Decode full-resolution frame at given time (on-demand).

        Returns:
            OpenCV frame or None
        """
        if not self.video_lane or not self.video_lane.metadata:
            return None

        try:
            # Lazy import
            self.video_lane._ensure_cv2()
            cv2 = self.video_lane.cv2

            # Open video
            cap = cv2.VideoCapture(str(self.video_lane.video_path))

            # Seek to time
            fps = self.video_lane.metadata.fps
            frame_idx = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

            # Read frame
            ret, frame = cap.read()
            cap.release()

            if ret:
                return frame

        except Exception:
            pass

        return None
