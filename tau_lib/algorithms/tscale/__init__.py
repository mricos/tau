"""
Tscale: Tau-Scale Synaptic Pulse Detector (TS-SPD).

A dual-tau spiking neural network algorithm for detecting transients in audio signals.

Model:
    k(t) = exp(-t/tau_r) - exp(-t/tau_a), where 0 < tau_a < tau_r

Modes:
    - conv: Direct convolution with kernel
    - iir: IIR filter approximation (faster)
    - sym: Zero-phase forward/backward (offline, better envelope)

Output:
    TSV with columns: t, y (filtered), env (envelope), evt (spike event 0/1)
"""

from tau_lib.algorithms.tscale.wrapper import TscaleAlgorithm, TscaleParams

__all__ = ['TscaleAlgorithm', 'TscaleParams']
