"""
Tau algorithm plugins.

This module provides a plugin architecture for signal processing algorithms.
The base Algorithm class defines the interface; implementations live in subdirectories.

Currently available:
- tscale: Dual-tau SNN spike detector (Tau-Scale Synaptic Pulse Detector)
"""

from tau_lib.algorithms.base import Algorithm, AlgorithmRegistry

__all__ = ['Algorithm', 'AlgorithmRegistry']
