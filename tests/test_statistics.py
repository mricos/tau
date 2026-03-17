"""Tests for tau_lib.analysis.statistics — pulse comparison and timing metrics."""

import pytest
import numpy as np
from tau_lib.analysis.statistics import (
    compute_count_ratios,
    compute_timing_precision,
    compute_correlation,
    compute_phase_alignment,
    detect_subdivisions,
    analyze_pulse_comparison,
)
from tau_lib.analysis.bpm import compute_isi


def _spike_times(bpm, duration=10.0):
    interval = 60.0 / bpm
    times = []
    t = 0.0
    while t < duration:
        times.append(t)
        t += interval
    return times


def _make_buffer(pulse1_bpm, pulse2_bpm, duration=10.0):
    """Create a data_buffer with two pulse channels."""
    dt = 0.001
    p1_interval = 60.0 / pulse1_bpm
    p2_interval = 60.0 / pulse2_bpm
    buffer = []
    t = 0.0
    next_p1 = 0.0
    next_p2 = 0.0
    while t < duration:
        vals = [0.0, 0.0, 0.0, 0.0]
        if t >= next_p1:
            vals[1] = 1.0
            next_p1 += p1_interval
        if t >= next_p2:
            vals[2] = 1.0
            next_p2 += p2_interval
        buffer.append((t, vals))
        t += dt
    return buffer


# --- compute_count_ratios ---

class TestCountRatios:
    def test_2_to_1_ratio(self):
        p1 = _spike_times(60.0, duration=10.0)   # 10 beats
        p2 = _spike_times(120.0, duration=10.0)   # 20 beats
        result = compute_count_ratios(p1, p2)
        assert result['pulse1_count'] == len(p1)
        assert result['pulse2_count'] == len(p2)
        assert result['expected_ratio'] == 2
        assert result['deviation_pct'] < 5.0

    def test_1_to_1_ratio(self):
        p1 = _spike_times(120.0)
        p2 = _spike_times(120.0)
        result = compute_count_ratios(p1, p2)
        assert result['expected_ratio'] == 1
        assert result['deviation_pct'] < 1.0

    def test_empty_pulse1(self):
        result = compute_count_ratios([], [1.0, 2.0])
        assert result['pulse1_count'] == 0
        assert result['ratio'] == 0.0

    def test_both_empty(self):
        result = compute_count_ratios([], [])
        assert result['pulse1_count'] == 0
        assert result['pulse2_count'] == 0


# --- compute_timing_precision ---

class TestTimingPrecision:
    def test_perfect_timing(self):
        times = _spike_times(120.0)
        result = compute_timing_precision(times)
        assert pytest.approx(result['mean_isi'], abs=0.001) == 0.5
        assert result['cv'] < 0.01  # near-zero variation
        assert result['jitter'] < 1.0  # sub-millisecond

    def test_jittery_timing(self):
        rng = np.random.default_rng(42)
        times = [t + rng.normal(0, 0.02) for t in _spike_times(120.0)]
        result = compute_timing_precision(times)
        assert result['cv'] > 0.01
        assert result['jitter'] > 1.0  # measurable jitter in ms

    def test_empty(self):
        result = compute_timing_precision([])
        assert result['mean_isi'] == 0.0
        assert result['cv'] == 0.0

    def test_single_spike(self):
        result = compute_timing_precision([1.0])
        assert result['mean_isi'] == 0.0

    def test_mad_nonzero_for_varied_intervals(self):
        times = [0.0, 0.3, 1.0, 1.5]  # uneven intervals
        result = compute_timing_precision(times)
        assert result['mad'] > 0.0


# --- compute_phase_alignment ---

class TestPhaseAlignment:
    def test_perfect_subdivision(self):
        """pulse2 at exactly 2x pulse1 rate should be 100% aligned."""
        p1 = _spike_times(60.0, duration=5.0)
        p2 = _spike_times(120.0, duration=5.0)
        alignment = compute_phase_alignment(p1, p2)
        assert alignment > 80.0  # high alignment

    def test_empty_inputs(self):
        assert compute_phase_alignment([], [1.0]) == 0.0
        assert compute_phase_alignment([1.0], []) == 0.0
        assert compute_phase_alignment([1.0], [2.0]) == 0.0  # need at least 2 pulse1s


# --- detect_subdivisions ---

class TestDetectSubdivisions:
    def test_2x_subdivision(self):
        """pulse2 at 2x rate: expect 1 subdivision per beat interval."""
        p1 = _spike_times(60.0, duration=5.0)   # every 1.0s
        p2 = _spike_times(120.0, duration=5.0)  # every 0.5s
        result = detect_subdivisions(p1, p2)
        assert result['mean_subdivisions_per_beat'] >= 0.5

    def test_empty(self):
        result = detect_subdivisions([], [1.0])
        assert result['mean_subdivisions_per_beat'] == 0.0
        assert result['subdivision_histogram'] == {}

    def test_no_pulse2(self):
        p1 = _spike_times(60.0, duration=3.0)
        result = detect_subdivisions(p1, [])
        assert result['mean_subdivisions_per_beat'] == 0.0


# --- compute_correlation ---

class TestCorrelation:
    def test_overlapping_pulses(self):
        """Identical pulse trains should have high cross-correlation."""
        p1 = _spike_times(120.0, duration=5.0)
        result = compute_correlation(p1, p1)
        assert result['cross_corr'] > 0.9

    def test_empty(self):
        result = compute_correlation([], [1.0])
        assert result['cross_corr'] == 0.0


# --- analyze_pulse_comparison (integration) ---

class TestAnalyzePulseComparison:
    def test_full_analysis(self):
        buf = _make_buffer(60.0, 120.0, duration=5.0)
        result = analyze_pulse_comparison(buf, pulse1_ch=1, pulse2_ch=2)
        assert 'count_ratios' in result
        assert 'timing_precision' in result
        assert 'correlation' in result
        assert result['count_ratios']['expected_ratio'] == 2

    def test_empty_buffer(self):
        result = analyze_pulse_comparison([], pulse1_ch=1, pulse2_ch=2)
        assert result['count_ratios']['pulse1_count'] == 0
