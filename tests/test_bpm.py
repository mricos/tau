"""Tests for tau_lib.analysis.bpm — pulse extraction and BPM calculation."""

import pytest
import numpy as np
from tau_lib.analysis.bpm import (
    extract_pulse_times,
    compute_isi,
    bpm_simple_isi,
    bpm_histogram_peak,
    bpm_windowed,
    bpm_autocorrelation,
    calculate_bpm_all_methods,
)


def _make_pulse_train(bpm: float, duration: float = 10.0, channel: int = 0, num_channels: int = 4):
    """Generate a synthetic data_buffer with pulses at given BPM."""
    interval = 60.0 / bpm
    dt = 0.001  # 1ms resolution
    buffer = []
    t = 0.0
    next_pulse = 0.0
    while t < duration:
        vals = [0.0] * num_channels
        if t >= next_pulse:
            vals[channel] = 1.0
            next_pulse += interval
        buffer.append((t, vals))
        t += dt
    return buffer


def _spike_times_at_bpm(bpm: float, duration: float = 10.0):
    """Generate evenly spaced spike times for a given BPM."""
    interval = 60.0 / bpm
    times = []
    t = 0.0
    while t < duration:
        times.append(t)
        t += interval
    return times


# --- extract_pulse_times ---

class TestExtractPulseTimes:
    def test_basic_extraction(self):
        buf = _make_pulse_train(120.0, duration=5.0, channel=1)
        times = extract_pulse_times(buf, channel_id=1, threshold=0.5)
        assert len(times) > 0

    def test_correct_count(self):
        """120 BPM = 2 beats/sec, 5 seconds = 10 beats."""
        buf = _make_pulse_train(120.0, duration=5.0, channel=0)
        times = extract_pulse_times(buf, channel_id=0, threshold=0.5)
        assert len(times) == 10

    def test_empty_buffer(self):
        assert extract_pulse_times([], 0) == []

    def test_no_spikes(self):
        buf = [(t * 0.001, [0.0]) for t in range(1000)]
        assert extract_pulse_times(buf, 0, threshold=0.5) == []

    def test_channel_out_of_range(self):
        buf = [(0.0, [1.0]), (0.001, [0.0]), (0.002, [1.0])]
        assert extract_pulse_times(buf, channel_id=5) == []

    def test_threshold_sensitivity(self):
        buf = _make_pulse_train(60.0, duration=3.0, channel=0)
        high_thresh = extract_pulse_times(buf, 0, threshold=2.0)
        low_thresh = extract_pulse_times(buf, 0, threshold=0.5)
        assert len(high_thresh) == 0
        assert len(low_thresh) > 0


# --- compute_isi ---

class TestComputeISI:
    def test_basic(self):
        assert compute_isi([0.0, 0.5, 1.0]) == [0.5, 0.5]

    def test_empty(self):
        assert compute_isi([]) == []

    def test_single(self):
        assert compute_isi([1.0]) == []

    def test_uneven(self):
        isis = compute_isi([0.0, 0.3, 1.0])
        assert pytest.approx(isis[0], abs=1e-9) == 0.3
        assert pytest.approx(isis[1], abs=1e-9) == 0.7


# --- bpm_simple_isi ---

class TestBPMSimpleISI:
    def test_120bpm(self):
        times = _spike_times_at_bpm(120.0, duration=10.0)
        bpm, conf = bpm_simple_isi(times)
        assert pytest.approx(bpm, abs=1.0) == 120.0
        assert conf > 0.9  # very consistent

    def test_60bpm(self):
        times = _spike_times_at_bpm(60.0, duration=10.0)
        bpm, conf = bpm_simple_isi(times)
        assert pytest.approx(bpm, abs=1.0) == 60.0

    def test_empty(self):
        bpm, conf = bpm_simple_isi([])
        assert bpm == 0.0
        assert conf == 0.0

    def test_single_spike(self):
        bpm, conf = bpm_simple_isi([1.0])
        assert bpm == 0.0

    def test_jittery_reduces_confidence(self):
        # Add jitter to spike times
        rng = np.random.default_rng(42)
        times = _spike_times_at_bpm(120.0, duration=10.0)
        jittered = [t + rng.normal(0, 0.05) for t in times]
        _, conf_jittery = bpm_simple_isi(jittered)
        _, conf_clean = bpm_simple_isi(times)
        assert conf_jittery < conf_clean


# --- bpm_histogram_peak ---

class TestBPMHistogramPeak:
    def test_120bpm(self):
        times = _spike_times_at_bpm(120.0, duration=10.0)
        bpm, conf = bpm_histogram_peak(times)
        assert pytest.approx(bpm, abs=2.0) == 120.0
        assert conf > 0.5

    def test_empty(self):
        bpm, conf = bpm_histogram_peak([])
        assert bpm == 0.0


# --- bpm_windowed ---

class TestBPMWindowed:
    def test_120bpm(self):
        times = _spike_times_at_bpm(120.0, duration=10.0)
        bpm, conf = bpm_windowed(times)
        assert pytest.approx(bpm, abs=2.0) == 120.0
        assert conf > 0.8

    def test_too_few_spikes(self):
        bpm, conf = bpm_windowed([0.0, 0.5])
        assert bpm == 0.0

    def test_empty(self):
        bpm, conf = bpm_windowed([])
        assert bpm == 0.0


# --- bpm_autocorrelation ---

class TestBPMAutocorrelation:
    def test_120bpm(self):
        times = _spike_times_at_bpm(120.0, duration=10.0)
        bpm, conf = bpm_autocorrelation(times)
        assert pytest.approx(bpm, abs=5.0) == 120.0
        assert conf > 0.0

    def test_too_few_spikes(self):
        bpm, conf = bpm_autocorrelation([0.0, 0.5])
        assert bpm == 0.0

    def test_empty(self):
        bpm, conf = bpm_autocorrelation([])
        assert bpm == 0.0


# --- calculate_bpm_all_methods ---

class TestCalculateBPMAllMethods:
    def test_all_methods_return(self):
        buf = _make_pulse_train(120.0, duration=10.0, channel=1)
        results = calculate_bpm_all_methods(buf, channel_id=1)
        assert set(results.keys()) == {'isi_average', 'histogram_peak', 'windowed', 'autocorrelation'}
        for method, (bpm, conf) in results.items():
            assert isinstance(bpm, float)
            assert isinstance(conf, float)

    def test_all_methods_agree(self):
        buf = _make_pulse_train(90.0, duration=10.0, channel=0)
        results = calculate_bpm_all_methods(buf, channel_id=0)
        bpms = [bpm for bpm, _ in results.values() if bpm > 0]
        # Normalize to same octave (autocorrelation can find half/double harmonics)
        target = 90.0
        normalized = [b if abs(b - target) < abs(b * 2 - target) else b * 2 for b in bpms]
        assert max(normalized) - min(normalized) < 10.0

    def test_empty_buffer(self):
        results = calculate_bpm_all_methods([], channel_id=0)
        for bpm, conf in results.values():
            assert bpm == 0.0
