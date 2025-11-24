"""
Tscale runner for ASCII Scope SNN.

Auto-generates tscale output from audio files with current kernel parameters.
"""

import subprocess
import tempfile
import toml
from pathlib import Path
from typing import Optional, List
from .data.trs import TRSStorage
from .core.state import KernelParams


class TscaleRunner:
    """Runs tscale to generate SNN data from audio files."""

    def __init__(self, trs: TRSStorage, tscale_bin: Optional[str] = None):
        """
        Initialize tscale runner.

        Args:
            trs: TRS storage instance
            tscale_bin: Path to tscale binary (default: auto-detect)
        """
        self.trs = trs

        # Auto-detect tscale binary if not specified
        if tscale_bin is None:
            script_dir = Path(__file__).parent
            tscale_paths = [
                script_dir.parent / "tscale" / "tscale",  # ../tscale/tscale
                Path("./tscale"),                          # ./tscale (for backward compat)
            ]

            for path in tscale_paths:
                if path.exists():
                    tscale_bin = str(path)
                    break

            if tscale_bin is None:
                raise FileNotFoundError(
                    f"tscale binary not found. Searched: {[str(p) for p in tscale_paths]}"
                )

        self.tscale_bin = Path(tscale_bin).resolve()

        if not self.tscale_bin.exists():
            raise FileNotFoundError(f"tscale binary not found: {self.tscale_bin}")

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

        # Use temp file for tscale output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Build tscale command
            cmd = [str(self.tscale_bin), '-i', str(audio_file)]
            cmd.extend(kernel_params.to_tscale_args())
            cmd.extend(['-norm', 'l2', '-sym', '-mode', 'iir', '-o', str(tmp_path)])

            # Run tscale
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                raise RuntimeError(f"tscale failed: {result.stderr}")

            # Read generated data
            with open(tmp_path, 'r') as f:
                tsv_data = f.read()

            # Write to TRS
            data_path = self.trs.write(
                "data", "raw", "tsv",
                tsv_data,
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
                toml.dumps(kernel_dict),
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

        finally:
            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

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
        try:
            result = subprocess.run(
                [str(self.tscale_bin), '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"
