"""
Current Working Directory (CWD) manager for ASCII Scope SNN.

Tracks the current working directory for:
- Audio file discovery
- Relative path resolution
- Default output location

Similar to Claude Code's CWD concept.
"""

import os
import json
from pathlib import Path
from typing import Optional
from .trs import TRSStorage


class CWDManager:
    """Manages current working directory state using TRS."""

    def __init__(self, trs: TRSStorage):
        """
        Initialize CWD manager.

        Args:
            trs: TRS storage instance
        """
        self.trs = trs
        self.cwd = self._load_cwd()

    def _load_cwd(self) -> Path:
        """Load CWD from latest session record."""
        record = self.trs.query_latest(type="session", kind="cwd")
        if record:
            data = self.trs.read(record)
            if isinstance(data, dict) and 'cwd' in data:
                return Path(data['cwd'])

        # Default to current directory
        return Path.cwd()

    def get_cwd(self) -> Path:
        """Get current working directory."""
        return self.cwd

    def set_cwd(self, path: Path) -> Path:
        """
        Set current working directory and persist to TRS.

        Args:
            path: New working directory

        Returns:
            Resolved absolute path
        """
        path = Path(path).resolve()

        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        self.cwd = path

        # Persist to TRS
        self.trs.write("session", "cwd", "json", {
            "cwd": str(self.cwd),
            "timestamp": self.trs.query_latest(type="session", kind="cwd").timestamp
                         if self.trs.query_latest(type="session", kind="cwd") else None
        })

        return self.cwd

    def resolve_path(self, relative_path: str) -> Path:
        """
        Resolve path relative to CWD.

        Args:
            relative_path: Relative or absolute path

        Returns:
            Absolute resolved path
        """
        path = Path(relative_path)

        if path.is_absolute():
            return path.resolve()

        # Resolve relative to CWD
        return (self.cwd / path).resolve()

    def find_audio_files(self, pattern: str = "*.wav") -> list[Path]:
        """
        Find audio files in CWD matching pattern.

        Args:
            pattern: Glob pattern (default: *.wav)

        Returns:
            List of matching audio file paths
        """
        return sorted(self.cwd.glob(pattern))

    def get_relative_path(self, absolute_path: Path) -> Optional[Path]:
        """
        Get path relative to CWD if possible.

        Args:
            absolute_path: Absolute path

        Returns:
            Relative path or None if not relative to CWD
        """
        try:
            return Path(absolute_path).relative_to(self.cwd)
        except ValueError:
            return None
