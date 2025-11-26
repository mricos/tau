"""
Tscale runner for ASCII Scope SNN.

Auto-generates tscale output from audio files with current kernel parameters.
Uses the TscaleAlgorithm from tau_lib.algorithms.tscale.
"""

import tempfile
from pathlib import Path
from typing import Optional

try:
    import tomli_w as toml_writer
except ImportError:
    toml_writer = None

from tau_lib.data.trs import TRSStorage
from tau_lib.core.state import KernelParams
from tau_lib.algorithms.tscale import TscaleAlgorithm, TscaleParams
from tau_lib.algorithms.tscale.wrapper import NormMode, FilterMode


def _dumps_toml(data: dict) -> str:
    """Serialize dict to TOML string."""
    if toml_writer:
        return toml_writer.dumps(data)
    # Manual fallback for simple flat dicts
    lines = []
    for key, val in data.items():
        if isinstance(val, str):
            lines.append(f'{key} = "{val}"')
        elif isinstance(val, bool):
            lines.append(f'{key} = {str(val).lower()}')
        else:
            lines.append(f'{key} = {val}')
    return '\n'.join(lines)


def _kernel_to_tscale_params(kernel: KernelParams) -> TscaleParams:
    """Convert KernelParams to TscaleParams."""
    return TscaleParams(
        tau_a=kernel.tau_a,
        tau_r=kernel.tau_r,
        threshold=kernel.threshold,
        refractory=kernel.refractory,
        fs=kernel.fs,
        norm=NormMode.L2,
        mode=FilterMode.IIR,
        zero_phase=True,
    )


class TscaleRunner:
    """Runs tscale to generate SNN data from audio files."""

    def __init__(self, trs: TRSStorage, tscale_bin: Optional[str] = None):
        """
        Initialize tscale runner.

        Args:
            trs: TRS storage instance
            tscale_bin: Path to tscale binary (default: auto-detect via TscaleAlgorithm)
        """
        self.trs = trs
        self._algorithm = TscaleAlgorithm()

        # Override binary path if specified
        if tscale_bin is not None:
            self._algorithm._binary_path = Path(tscale_bin).resolve()

        if not self._algorithm.is_built():
            # Try to build
            if not self._algorithm.build():
                raise FileNotFoundError(
                    f"tscale binary not found and build failed. "
                    f"Expected at: {self._algorithm._binary_path}"
                )

    def run(self,
            audio_file: Path,
            kernel_params: KernelParams,
            timestamp: Optional[int] = None) -> Path:
        """
        Run tscale on audio file with kernel parameters.

        Args:
            audio_file: Input audio file path
            kernel_params: Kernel parameters for processing
            timestamp: Optional timestamp (default: current time)

        Returns:
            Path to generated TSV data file in TRS

        Example:
            runner = TscaleRunner(trs)
            data_path = runner.run(Path("test.wav"), kernel_params)
            # Creates: ./db/{timestamp}.data.raw.tsv
        """
        audio_file = Path(audio_file).resolve()

        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        # Convert kernel params to tscale params
        tscale_params = _kernel_to_tscale_params(kernel_params)
        self._algorithm.params = tscale_params

        # Run tscale algorithm
        result = self._algorithm.run(audio_file)

        if not result.success:
            raise RuntimeError(f"tscale failed: {result.error}")

        # Write to TRS
        data_path = self.trs.write(
            "data", "raw", "tsv",
            result.data,
            timestamp=timestamp,
            audio=audio_file.stem
        )

        # Also save kernel params used for this data
        kernel_dict = {
            'tau_a': kernel_params.tau_a,
            'tau_r': kernel_params.tau_r,
            'threshold': kernel_params.threshold,
            'refractory': kernel_params.refractory,
            'fs': kernel_params.fs,
        }

        self.trs.write(
            "config", "kernel", "toml",
            _dumps_toml(kernel_dict),
            timestamp=timestamp,
            audio=audio_file.stem
        )

        # Copy source audio to TRS
        self.trs.write_file(
            "audio", "source",
            audio_file,
            timestamp=timestamp
        )

        return data_path

    def find_or_generate(self,
                         audio_file: Path,
                         kernel_params: KernelParams) -> Path:
        """
        Find existing data or generate new.

        Args:
            audio_file: Audio file path
            kernel_params: Kernel parameters

        Returns:
            Path to data file (existing or newly generated)
        """
        audio_file = Path(audio_file).resolve()

        # Check for existing data
        records = self.trs.query(
            type="data",
            kind="raw",
            format="tsv"
        )

        # Filter by audio file stem in filename
        audio_stem = audio_file.stem
        matching = [r for r in records if audio_stem in r.filepath.name]

        if matching:
            # Found existing data
            latest = matching[0]  # Already sorted newest first
            return latest.filepath

        # No existing data, generate new
        return self.run(audio_file, kernel_params)

    def get_tscale_version(self) -> str:
        """Get tscale version string."""
        return self._algorithm.get_version()

    @property
    def algorithm(self) -> TscaleAlgorithm:
        """Access underlying algorithm instance."""
        return self._algorithm
