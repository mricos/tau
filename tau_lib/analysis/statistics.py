"""
Statistical analysis for comparing pulse trains (pulse1 vs pulse2).
Calculates count ratios, timing precision, and correlation metrics.
"""

import numpy as np
from typing import List, Tuple, Dict
from tau_lib.analysis.bpm import extract_pulse_times, compute_isi


def analyze_pulse_comparison(
    data_buffer: List[Tuple[float, List[float]]],
    pulse1_ch: int = 1,
    pulse2_ch: int = 2
) -> Dict:
    """
    Comprehensive comparison of pulse1 (beat) vs pulse2 (subdivisions).

    Returns:
        Dictionary with all statistics
    """
    pulse1_times = extract_pulse_times(data_buffer, pulse1_ch)
    pulse2_times = extract_pulse_times(data_buffer, pulse2_ch)

    result = {}

    # Count ratios
    result['count_ratios'] = compute_count_ratios(pulse1_times, pulse2_times)

    # Timing precision
    result['timing_precision'] = {
        'pulse1': compute_timing_precision(pulse1_times),
        'pulse2': compute_timing_precision(pulse2_times),
    }

    # Correlation metrics
    result['correlation'] = compute_correlation(pulse1_times, pulse2_times)

    return result


# ========== Count Ratios ==========

def compute_count_ratios(pulse1_times: List[float], pulse2_times: List[float]) -> Dict:
    """
    Calculate count ratios and expected subdivision ratio.

    Returns:
        {
            'pulse1_count': int,
            'pulse2_count': int,
            'ratio': float,
            'expected_ratio': int,  # Closest integer ratio (2:1, 3:1, 4:1, etc.)
            'deviation_pct': float,
        }
    """
    count1 = len(pulse1_times)
    count2 = len(pulse2_times)

    if count1 == 0:
        return {
            'pulse1_count': 0,
            'pulse2_count': count2,
            'ratio': 0.0,
            'expected_ratio': 0,
            'deviation_pct': 0.0,
        }

    ratio = count2 / count1

    # Find closest integer ratio
    expected_ratio = round(ratio)
    if expected_ratio < 1:
        expected_ratio = 1

    # Calculate deviation
    deviation_pct = abs(ratio - expected_ratio) / expected_ratio * 100 if expected_ratio > 0 else 0.0

    return {
        'pulse1_count': count1,
        'pulse2_count': count2,
        'ratio': ratio,
        'expected_ratio': expected_ratio,
        'deviation_pct': deviation_pct,
    }


# ========== Timing Precision ==========

def compute_timing_precision(spike_times: List[float]) -> Dict:
    """
    Calculate timing precision metrics for a pulse train.

    Returns:
        {
            'mean_isi': float,       # Mean inter-spike interval
            'std_isi': float,        # Standard deviation of ISI
            'jitter': float,         # Alias for std_isi (ms)
            'cv': float,             # Coefficient of variation (σ/μ)
            'mad': float,            # Mean absolute deviation
        }
    """
    isis = compute_isi(spike_times)

    if not isis:
        return {
            'mean_isi': 0.0,
            'std_isi': 0.0,
            'jitter': 0.0,
            'cv': 0.0,
            'mad': 0.0,
        }

    mean_isi = np.mean(isis)
    std_isi = np.std(isis)
    cv = std_isi / mean_isi if mean_isi > 0 else 0.0

    # Mean absolute deviation
    mad = np.mean(np.abs(np.array(isis) - mean_isi))

    return {
        'mean_isi': mean_isi,
        'std_isi': std_isi,
        'jitter': std_isi * 1000,  # Convert to milliseconds
        'cv': cv,
        'mad': mad,
    }


# ========== Correlation ==========

def compute_correlation(pulse1_times: List[float], pulse2_times: List[float]) -> Dict:
    """
    Calculate correlation metrics between pulse trains.

    Returns:
        {
            'cross_corr': float,      # Cross-correlation peak
            'phase_alignment': float, # % of pulse2 aligned with pulse1 grid
            'subdivision_detection': Dict, # Analysis of subdivision patterns
        }
    """
    if not pulse1_times or not pulse2_times:
        return {
            'cross_corr': 0.0,
            'phase_alignment': 0.0,
            'subdivision_detection': {},
        }

    # Simple cross-correlation: overlap of pulse2 with pulse1
    overlap_count = 0
    window = 0.05  # 50ms window

    for p2 in pulse2_times:
        for p1 in pulse1_times:
            if abs(p2 - p1) < window:
                overlap_count += 1
                break

    cross_corr = overlap_count / len(pulse2_times) if pulse2_times else 0.0

    # Phase alignment: check how many pulse2s fall on the pulse1 grid
    phase_alignment = compute_phase_alignment(pulse1_times, pulse2_times)

    # Subdivision detection: analyze intervals between pulse1s
    subdivision_detection = detect_subdivisions(pulse1_times, pulse2_times)

    return {
        'cross_corr': cross_corr,
        'phase_alignment': phase_alignment,
        'subdivision_detection': subdivision_detection,
    }


def compute_phase_alignment(pulse1_times: List[float], pulse2_times: List[float]) -> float:
    """
    Calculate what % of pulse2s are aligned with the pulse1 grid.

    A pulse2 is "aligned" if it falls within ±10% of the expected subdivision point.
    """
    if len(pulse1_times) < 2 or not pulse2_times:
        return 0.0

    # Calculate mean pulse1 interval (beat period)
    pulse1_isis = compute_isi(pulse1_times)
    mean_period = np.mean(pulse1_isis)

    if mean_period <= 0:
        return 0.0

    aligned_count = 0
    tolerance = mean_period * 0.1  # 10% tolerance

    for p2 in pulse2_times:
        # Find nearest pulse1 before p2
        prev_p1 = max([p1 for p1 in pulse1_times if p1 <= p2], default=None)

        if prev_p1 is None:
            continue

        # Calculate phase within beat period
        phase = (p2 - prev_p1) % mean_period

        # Check if aligned to subdivision grid (0, 1/2, 1/3, 1/4 of period)
        for div in [1, 2, 3, 4, 6, 8]:
            expected_phase = mean_period / div
            for multiple in range(div):
                target_phase = expected_phase * multiple
                if abs(phase - target_phase) < tolerance:
                    aligned_count += 1
                    break

    return aligned_count / len(pulse2_times) * 100  # Return as percentage


def detect_subdivisions(pulse1_times: List[float], pulse2_times: List[float]) -> Dict:
    """
    Detect subdivision patterns: how pulse2s divide the pulse1 intervals.

    Returns:
        {
            'mean_subdivisions_per_beat': float,
            'subdivision_histogram': Dict[int, int],  # {2: count, 3: count, 4: count, ...}
        }
    """
    if len(pulse1_times) < 2 or not pulse2_times:
        return {
            'mean_subdivisions_per_beat': 0.0,
            'subdivision_histogram': {},
        }

    subdivision_counts = []

    # For each pulse1 interval, count pulse2s within it
    for i in range(len(pulse1_times) - 1):
        start = pulse1_times[i]
        end = pulse1_times[i + 1]

        # Count pulse2s in this interval (excluding endpoints)
        count = sum(1 for p2 in pulse2_times if start < p2 < end)
        subdivision_counts.append(count)

    mean_subdivisions = np.mean(subdivision_counts) if subdivision_counts else 0.0

    # Histogram of subdivision counts
    from collections import Counter
    histogram = dict(Counter(subdivision_counts))

    return {
        'mean_subdivisions_per_beat': mean_subdivisions,
        'subdivision_histogram': histogram,
    }
