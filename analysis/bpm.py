"""
BPM (Beats Per Minute) calculation from pulse trains.
Implements 4 different methods for robustness.
"""

import math
import numpy as np
from typing import List, Tuple, Optional
from collections import Counter


def extract_pulse_times(data_buffer: List[Tuple[float, List[float]]], channel_id: int, threshold: float = 0.5) -> List[float]:
    """
    Extract spike times from a channel.

    Args:
        data_buffer: [(time, [values])]
        channel_id: Which channel to extract (0-3)
        threshold: Detection threshold

    Returns:
        List of spike times
    """
    spike_times = []
    prev_val = 0.0

    for t, vals in data_buffer:
        if channel_id >= len(vals):
            continue

        val = vals[channel_id]

        # Rising edge detection
        if prev_val < threshold <= val:
            spike_times.append(t)

        prev_val = val

    return spike_times


def compute_isi(spike_times: List[float]) -> List[float]:
    """Compute inter-spike intervals."""
    if len(spike_times) < 2:
        return []
    return [spike_times[i+1] - spike_times[i] for i in range(len(spike_times) - 1)]


# ========== METHOD 1: Simple ISI Average ==========

def bpm_simple_isi(spike_times: List[float]) -> Tuple[float, float]:
    """
    Calculate BPM from mean inter-spike interval.

    Returns:
        (bpm, confidence) where confidence is based on CV (coefficient of variation)
    """
    isis = compute_isi(spike_times)
    if not isis:
        return (0.0, 0.0)

    mean_isi = np.mean(isis)
    std_isi = np.std(isis)

    bpm = 60.0 / mean_isi if mean_isi > 0 else 0.0

    # Confidence based on inverse of coefficient of variation
    cv = std_isi / mean_isi if mean_isi > 0 else 1.0
    confidence = 1.0 / (1.0 + cv)  # 0-1 scale

    return (bpm, confidence)


# ========== METHOD 2: Histogram Peak ==========

def bpm_histogram_peak(spike_times: List[float], bin_size: float = 0.005) -> Tuple[float, float]:
    """
    Calculate BPM from most common ISI (histogram peak).

    Args:
        spike_times: List of spike times
        bin_size: Histogram bin size in seconds (default 5ms)

    Returns:
        (bpm, confidence) where confidence is peak strength relative to total
    """
    isis = compute_isi(spike_times)
    if not isis:
        return (0.0, 0.0)

    # Bin ISIs
    binned = [int(isi / bin_size) * bin_size for isi in isis]
    counter = Counter(binned)

    if not counter:
        return (0.0, 0.0)

    # Find peak
    peak_isi, peak_count = counter.most_common(1)[0]

    bpm = 60.0 / peak_isi if peak_isi > 0 else 0.0

    # Confidence based on peak strength
    total = sum(counter.values())
    confidence = peak_count / total if total > 0 else 0.0

    return (bpm, confidence)


# ========== METHOD 3: Windowed Analysis ==========

def bpm_windowed(spike_times: List[float], window_size: float = 4.0) -> Tuple[float, float]:
    """
    Calculate BPM using sliding window (detects tempo changes).

    Args:
        spike_times: List of spike times
        window_size: Window size in seconds

    Returns:
        (bpm, confidence) - BPM is median of windowed estimates
    """
    if len(spike_times) < 4:
        return (0.0, 0.0)

    bpms = []

    # Sliding window
    for i in range(len(spike_times) - 1):
        window_spikes = [t for t in spike_times if spike_times[i] <= t < spike_times[i] + window_size]

        if len(window_spikes) < 2:
            continue

        # Calculate BPM for this window
        window_isis = compute_isi(window_spikes)
        if window_isis:
            mean_isi = np.mean(window_isis)
            if mean_isi > 0:
                bpms.append(60.0 / mean_isi)

    if not bpms:
        return (0.0, 0.0)

    # Median BPM (robust to outliers)
    median_bpm = np.median(bpms)

    # Confidence based on consistency (inverse of std/mean)
    std_bpm = np.std(bpms)
    mean_bpm = np.mean(bpms)
    cv = std_bpm / mean_bpm if mean_bpm > 0 else 1.0
    confidence = 1.0 / (1.0 + cv)

    return (median_bpm, confidence)


# ========== METHOD 4: Autocorrelation ==========

def bpm_autocorrelation(spike_times: List[float], fs: float = 1000.0, max_lag: float = 2.0) -> Tuple[float, float]:
    """
    Calculate BPM using autocorrelation of pulse train.

    Args:
        spike_times: List of spike times
        fs: Sampling frequency for discrete signal (Hz)
        max_lag: Maximum lag to search (seconds)

    Returns:
        (bpm, confidence) where confidence is autocorr peak strength
    """
    if len(spike_times) < 4:
        return (0.0, 0.0)

    # Create discrete pulse train
    duration = spike_times[-1] - spike_times[0]
    n_samples = int(duration * fs)

    if n_samples < 2:
        return (0.0, 0.0)

    pulse_train = np.zeros(n_samples)

    for t in spike_times:
        idx = int((t - spike_times[0]) * fs)
        if 0 <= idx < n_samples:
            pulse_train[idx] = 1.0

    # Autocorrelation
    max_lag_samples = int(max_lag * fs)
    autocorr = np.correlate(pulse_train, pulse_train, mode='full')
    autocorr = autocorr[len(autocorr)//2:]  # Take positive lags only

    # Find peak (ignore lag=0)
    if len(autocorr) < max_lag_samples:
        return (0.0, 0.0)

    search_range = autocorr[1:max_lag_samples]

    if len(search_range) == 0:
        return (0.0, 0.0)

    peak_idx = np.argmax(search_range) + 1  # +1 because we started from index 1
    peak_lag = peak_idx / fs  # Convert to seconds

    bpm = 60.0 / peak_lag if peak_lag > 0 else 0.0

    # Confidence based on peak height relative to mean
    peak_height = search_range[peak_idx - 1]
    mean_height = np.mean(search_range)
    confidence = (peak_height / mean_height - 1.0) if mean_height > 0 else 0.0
    confidence = min(1.0, max(0.0, confidence))  # Clamp to [0, 1]

    return (bpm, confidence)


# ========== Unified Interface ==========

def calculate_bpm_all_methods(data_buffer: List[Tuple[float, List[float]]], channel_id: int = 1) -> dict:
    """
    Calculate BPM using all 4 methods.

    Args:
        data_buffer: [(time, [values])]
        channel_id: Which channel to analyze (default 1 = pulse1)

    Returns:
        Dictionary with results from all methods:
        {
            'isi_average': (bpm, confidence),
            'histogram_peak': (bpm, confidence),
            'windowed': (bpm, confidence),
            'autocorrelation': (bpm, confidence),
        }
    """
    spike_times = extract_pulse_times(data_buffer, channel_id)

    results = {
        'isi_average': bpm_simple_isi(spike_times),
        'histogram_peak': bpm_histogram_peak(spike_times),
        'windowed': bpm_windowed(spike_times),
        'autocorrelation': bpm_autocorrelation(spike_times),
    }

    return results
