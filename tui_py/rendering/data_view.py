"""
Simple data view utilities for efficient waveform rendering.

Uses binary search to find visible data range - O(log n) instead of O(n).
No caching, no complexity - just slice the data you need.
"""

import bisect
from typing import List, Tuple, Optional


# Type alias for clarity
DataBuffer = List[Tuple[float, List[float]]]


class DataView:
    """
    Efficient view into time-series data buffer.

    Maintains a time index for O(log n) range lookups.
    Rebuilds index only when data buffer changes.
    """

    def __init__(self):
        self._data_id: Optional[int] = None
        self._data_len: int = 0
        self._times: List[float] = []

    def _ensure_index(self, data_buffer: DataBuffer):
        """Rebuild time index if data buffer changed."""
        if not data_buffer:
            self._times = []
            self._data_id = None
            self._data_len = 0
            return

        # Check if we need to rebuild (by identity and length)
        current_id = id(data_buffer)
        current_len = len(data_buffer)

        if current_id != self._data_id or current_len != self._data_len:
            # Rebuild time index - just extract timestamps
            self._times = [d[0] for d in data_buffer]
            self._data_id = current_id
            self._data_len = current_len

    def get_visible_range(self, data_buffer: DataBuffer,
                          left_t: float, right_t: float) -> Tuple[int, int]:
        """
        Get index range [start, end) for visible data.

        Returns (start_idx, end_idx) such that data_buffer[start:end]
        contains all samples overlapping [left_t, right_t].

        Time complexity: O(log n)
        """
        self._ensure_index(data_buffer)

        if not self._times:
            return (0, 0)

        # Binary search for range
        start = bisect.bisect_left(self._times, left_t)
        end = bisect.bisect_right(self._times, right_t)

        # Include one sample before/after for interpolation
        start = max(0, start - 1)
        end = min(len(self._times), end + 1)

        return (start, end)

    def get_visible_slice(self, data_buffer: DataBuffer,
                          left_t: float, right_t: float) -> DataBuffer:
        """
        Get slice of data buffer that overlaps time window.

        Time complexity: O(log n)
        """
        start, end = self.get_visible_range(data_buffer, left_t, right_t)
        return data_buffer[start:end]

    def get_envelope(self, data_buffer: DataBuffer,
                     left_t: float, right_t: float,
                     num_columns: int, channel_id: int,
                     gain: float = 1.0) -> List[Tuple[float, float]]:
        """
        Get (min, max) envelope data binned into screen columns.

        Args:
            data_buffer: Source data
            left_t, right_t: Time window
            num_columns: Number of screen columns to bin into
            channel_id: Which channel to extract
            gain: Amplitude multiplier

        Returns:
            List of (min_val, max_val) tuples, one per column.
            Returns (0.0, 0.0) for empty columns.
        """
        visible = self.get_visible_slice(data_buffer, left_t, right_t)

        if not visible or num_columns < 1:
            return [(0.0, 0.0)] * max(1, num_columns)

        span = max(1e-12, right_t - left_t)

        # Initialize bins with None to track empty columns
        bins_min = [None] * num_columns
        bins_max = [None] * num_columns

        for t, vals in visible:
            if channel_id >= len(vals):
                continue

            # Map time to column
            x_frac = (t - left_t) / span
            col = int(x_frac * num_columns)

            if 0 <= col < num_columns:
                val = vals[channel_id] * gain

                if bins_min[col] is None:
                    bins_min[col] = val
                    bins_max[col] = val
                else:
                    bins_min[col] = min(bins_min[col], val)
                    bins_max[col] = max(bins_max[col], val)

        # Convert None to (0.0, 0.0) for empty bins
        return [
            (0.0, 0.0) if bins_min[i] is None else (bins_min[i], bins_max[i])
            for i in range(num_columns)
        ]


# Global instance for convenience (stateless except for cached index)
_view: Optional[DataView] = None


def get_view() -> DataView:
    """Get global DataView instance."""
    global _view
    if _view is None:
        _view = DataView()
    return _view


def get_visible_slice(data_buffer: DataBuffer,
                      left_t: float, right_t: float) -> DataBuffer:
    """
    Convenience function: get visible slice of data buffer.

    Usage:
        visible = get_visible_slice(data_buffer, left_t, right_t)
        for t, vals in visible:
            ...
    """
    return get_view().get_visible_slice(data_buffer, left_t, right_t)


def get_envelope(data_buffer: DataBuffer,
                 left_t: float, right_t: float,
                 num_columns: int, channel_id: int,
                 gain: float = 1.0) -> List[Tuple[float, float]]:
    """
    Convenience function: get envelope data binned into columns.

    Usage:
        envelope = get_envelope(data_buffer, left_t, right_t, width, channel)
        for col, (min_val, max_val) in enumerate(envelope):
            ...
    """
    return get_view().get_envelope(
        data_buffer, left_t, right_t, num_columns, channel_id, gain
    )
