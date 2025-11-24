"""
Data loading for ASCII Scope SNN.
Handles loading tscale output files (TSV format: time, audio, pulse1, pulse2).
"""

import sys
import os
from typing import List, Tuple


def parse_line(line: str, max_channels: int = 4) -> Tuple[float, List[float]]:
    """
    Parse a line of TSV data.

    Returns:
        (time, [values...]) or None if parse fails
    """
    try:
        parts = line.strip().split()
        if len(parts) < 2:
            return None

        t = float(parts[0])
        vals = [float(p) for p in parts[1:1+max_channels]]

        return (t, vals)
    except Exception:
        return None


def load_data_file(path: str, max_channels: int = 4) -> List[Tuple[float, List[float]]]:
    """
    Load all data from a file into memory.

    Args:
        path: File path to load (or "-" for stdin)
        max_channels: Maximum number of channels to load

    Returns:
        List of (time, [values]) tuples
    """
    data_buffer = []
    last_t = None

    is_stdin = path in ("-", "/dev/stdin")

    if is_stdin:
        # Read from stdin
        for line in sys.stdin:
            rec = parse_line(line, max_channels)
            if not rec:
                continue
            t, vs = rec

            # Ensure monotonic time
            if last_t is not None and t < last_t:
                t = last_t + 1e-12
            last_t = t

            data_buffer.append((t, vs))
    else:
        # Read from file
        if not os.path.exists(path):
            raise FileNotFoundError(f"Data file not found: {path}")

        with open(path, 'r') as f:
            for line in f:
                rec = parse_line(line, max_channels)
                if not rec:
                    continue
                t, vs = rec

                # Ensure monotonic time
                if last_t is not None and t < last_t:
                    t = last_t + 1e-12
                last_t = t

                data_buffer.append((t, vs))

    return data_buffer


def compute_duration(data_buffer: List[Tuple[float, List[float]]]) -> float:
    """Compute total duration from data buffer."""
    if not data_buffer:
        return 0.0
    return data_buffer[-1][0] - data_buffer[0][0]


def get_data_in_window(
    data_buffer: List[Tuple[float, List[float]]],
    left_t: float,
    right_t: float
) -> List[Tuple[float, List[float]]]:
    """
    Get data points within time window [left_t, right_t].

    Uses binary search for efficiency on large datasets.
    """
    if not data_buffer:
        return []

    # Binary search for left boundary
    left_idx = 0
    right_idx = len(data_buffer)

    # Find first index >= left_t
    while left_idx < right_idx:
        mid = (left_idx + right_idx) // 2
        if data_buffer[mid][0] < left_t:
            left_idx = mid + 1
        else:
            right_idx = mid

    start_idx = max(0, left_idx - 1)  # Include one point before for continuity

    # Find last index <= right_t
    left_idx = start_idx
    right_idx = len(data_buffer)

    while left_idx < right_idx:
        mid = (left_idx + right_idx) // 2
        if data_buffer[mid][0] <= right_t:
            left_idx = mid + 1
        else:
            right_idx = mid

    end_idx = min(len(data_buffer), left_idx + 1)  # Include one point after

    return data_buffer[start_idx:end_idx]
