"""
TscaleAlgorithm: Python wrapper for the tscale C binary.

Handles building from source, parameter validation, and execution.
"""

import subprocess
import tempfile
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from enum import Enum

from tau_lib.algorithms.base import Algorithm, AlgorithmParams, AlgorithmOutput, AlgorithmRegistry


class NormMode(Enum):
    """Normalization mode for kernel."""
    L2 = "l2"      # Unit RMS normalization
    AREA = "area"  # Unit area normalization
    NONE = "none"  # No normalization


class FilterMode(Enum):
    """Filter implementation mode."""
    IIR = "iir"    # IIR filter (faster)
    CONV = "conv"  # Direct convolution


@dataclass
class TscaleParams(AlgorithmParams):
    """Parameters for tscale algorithm."""
    tau_a: float = 0.001       # Attack tau (seconds)
    tau_r: float = 0.005       # Recovery tau (seconds)
    threshold: float = 3.0     # Detection threshold (sigma units)
    refractory: float = 0.015  # Refractory period (seconds)
    fs: int = 48000            # Sample rate (Hz)
    norm: NormMode = NormMode.L2
    mode: FilterMode = FilterMode.IIR
    zero_phase: bool = True    # Use symmetric (forward/backward) filtering

    def to_args(self) -> List[str]:
        """Convert parameters to tscale CLI arguments."""
        args = [
            '-ta', str(self.tau_a),
            '-tr', str(self.tau_r),
            '-th', str(self.threshold),
            '-ref', str(self.refractory),
            '-norm', self.norm.value,
            '-mode', self.mode.value,
        ]
        if self.zero_phase:
            args.append('-sym')
        return args


@AlgorithmRegistry.register
class TscaleAlgorithm(Algorithm):
    """
    Tau-Scale Synaptic Pulse Detector.

    A dual-tau SNN algorithm for transient detection in audio signals.
    Uses a bi-exponential kernel k(t) = exp(-t/tau_r) - exp(-t/tau_a).
    """

    name = "tscale"
    version = "1.0.0"
    description = "Dual-tau SNN spike detector for audio transients"

    def __init__(self, params: Optional[TscaleParams] = None):
        super().__init__(params)
        self._source_dir = Path(__file__).parent
        self._binary_path = self._find_or_default_binary()

    @classmethod
    def default_params(cls) -> TscaleParams:
        return TscaleParams()

    def _find_or_default_binary(self) -> Path:
        """Find existing binary or return default build path."""
        # Check for pre-built binary in algorithm directory
        local_bin = self._source_dir / "tscale"
        if local_bin.exists():
            return local_bin

        # Check original tscale location (sibling directory)
        original = self._source_dir.parent.parent.parent.parent / "tscale" / "tscale"
        if original.exists():
            return original

        # Default to local build path
        return local_bin

    def is_built(self) -> bool:
        """Check if tscale binary exists."""
        return self._binary_path.exists()

    def build(self, force: bool = False) -> bool:
        """
        Build tscale from source.

        Uses clang on macOS, gcc on Linux.

        Args:
            force: Rebuild even if binary exists

        Returns:
            True if build succeeded
        """
        if self.is_built() and not force:
            return True

        source_file = self._source_dir / "tscale.c"
        if not source_file.exists():
            return False

        output_path = self._source_dir / "tscale"
        compiler = "clang" if platform.system() == "Darwin" else "gcc"

        cmd = [
            compiler,
            "-std=c11",
            "-O3",
            "-o", str(output_path),
            str(source_file),
            "-lm"
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self._source_dir),
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                return False
            self._binary_path = output_path
            return True
        except Exception:
            return False

    def run(self, input_path: Path, output_path: Optional[Path] = None) -> AlgorithmOutput:
        """
        Run tscale on an audio file.

        Args:
            input_path: Path to input audio file (wav, mp3, etc.)
            output_path: Optional output TSV path (uses temp file if not specified)

        Returns:
            AlgorithmOutput with TSV data and metadata
        """
        if not self.is_built():
            if not self.build():
                return AlgorithmOutput(
                    data=None,
                    success=False,
                    error="Failed to build tscale binary"
                )

        input_path = Path(input_path).resolve()
        if not input_path.exists():
            return AlgorithmOutput(
                data=None,
                success=False,
                error=f"Input file not found: {input_path}"
            )

        # Use temp file if no output path specified
        use_temp = output_path is None
        if use_temp:
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False)
            output_path = Path(tmp.name)
            tmp.close()

        try:
            params = self.params or self.default_params()
            cmd = [
                str(self._binary_path),
                '-i', str(input_path),
                '-o', str(output_path),
            ]
            cmd.extend(params.to_args())

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for long files
            )

            if result.returncode != 0:
                return AlgorithmOutput(
                    data=None,
                    success=False,
                    error=f"tscale failed: {result.stderr}"
                )

            # Read output data
            with open(output_path, 'r') as f:
                tsv_data = f.read()

            return AlgorithmOutput(
                data=tsv_data,
                metadata={
                    'input': str(input_path),
                    'output': str(output_path),
                    'params': {
                        'tau_a': params.tau_a,
                        'tau_r': params.tau_r,
                        'threshold': params.threshold,
                        'refractory': params.refractory,
                        'norm': params.norm.value,
                        'mode': params.mode.value,
                        'zero_phase': params.zero_phase,
                    }
                },
                success=True
            )

        except subprocess.TimeoutExpired:
            return AlgorithmOutput(
                data=None,
                success=False,
                error="tscale timed out"
            )
        except Exception as e:
            return AlgorithmOutput(
                data=None,
                success=False,
                error=str(e)
            )
        finally:
            if use_temp and output_path.exists():
                output_path.unlink()

    def get_version(self) -> str:
        """Get tscale binary version."""
        if not self.is_built():
            return f"{self.version} (not built)"

        try:
            result = subprocess.run(
                [str(self._binary_path), '--help'],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Parse version from help output if available
            return self.version
        except Exception:
            return self.version

    def validate_params(self) -> List[str]:
        """Validate tscale parameters."""
        errors = []
        params = self.params or self.default_params()

        if params.tau_a <= 0:
            errors.append("tau_a must be positive")
        if params.tau_r <= 0:
            errors.append("tau_r must be positive")
        if params.tau_a >= params.tau_r:
            errors.append("tau_a must be less than tau_r")
        if params.threshold <= 0:
            errors.append("threshold must be positive")
        if params.refractory < 0:
            errors.append("refractory must be non-negative")
        if params.fs <= 0:
            errors.append("fs must be positive")

        return errors
