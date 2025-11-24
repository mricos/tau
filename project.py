"""
Project manager for tau.

Manages project structure:
  tau/
    data/              # Runtime data (not checked in)
      sessions/        # Session files
      db/              # TRS data storage
      config.json      # Local config
    audio/             # Sample audio files
"""

import os
import json
from pathlib import Path
from typing import Optional, List
from .trs import TRSStorage
from .cwd_manager import CWDManager


class TauProject:
    """
    Manages tau project structure and metadata.

    Uses tau/data/ directory for:
    - sessions/ - Session state files
    - db/ - TRS data storage (timestamped records)
    - config.json - Local configuration
    """

    def __init__(self, project_dir: Optional[Path] = None):
        """
        Initialize tau project.

        Args:
            project_dir: Project root directory (default: tau module directory)
        """
        if project_dir:
            self.project_dir = Path(project_dir).resolve()
        else:
            # Default to tau module directory
            self.project_dir = Path(__file__).parent

        # Initialize directories
        self.data_dir = self.project_dir / "data"
        self.sessions_dir = self.data_dir / "sessions"
        self.db_dir = self.data_dir / "db"
        self.audio_dir = self.project_dir / "audio"

        # Create directories if they don't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # Initialize TRS storage
        self.trs = TRSStorage(str(self.db_dir))

        # Initialize CWD manager
        self.cwd_mgr = CWDManager(self.trs)

        # Current session name
        self.current_session = "default"

    def get_session_file(self, session_name: Optional[str] = None) -> Path:
        """
        Get path to session file.

        Args:
            session_name: Name of session (default: current session)
        """
        name = session_name or self.current_session
        return self.sessions_dir / f"{name}.json"

    def get_config_file(self) -> Path:
        """Get path to config file."""
        return self.data_dir / "config.json"

    def list_sessions(self) -> List[str]:
        """
        List all available session names.

        Returns:
            List of session names (without .json extension)
        """
        sessions = []
        for f in self.sessions_dir.glob("*.json"):
            sessions.append(f.stem)
        return sorted(sessions)

    def save_session_state(self, state_data: dict, session_name: Optional[str] = None):
        """
        Save session state to sessions/{name}.json.

        Args:
            state_data: Session state dictionary
            session_name: Session name (default: current session)
        """
        session_file = self.get_session_file(session_name)
        with open(session_file, 'w') as f:
            json.dump(state_data, f, indent=2)

    def load_session_state(self, session_name: Optional[str] = None) -> Optional[dict]:
        """
        Load session state from sessions/{name}.json.

        Args:
            session_name: Session name (default: current session)

        Returns:
            Session state dict or None if not found
        """
        session_file = self.get_session_file(session_name)
        if not session_file.exists():
            return None

        with open(session_file, 'r') as f:
            return json.load(f)

    def switch_session(self, session_name: str):
        """
        Switch to a different session.

        Args:
            session_name: Name of session to switch to
        """
        self.current_session = session_name

    def create_session(self, session_name: str, template: Optional[dict] = None):
        """
        Create a new session.

        Args:
            session_name: Name for new session
            template: Optional template data (default: empty session)
        """
        if template is None:
            template = {
                "timestamp": 0,
                "audio_file": None,
                "data_file": None,
                "position": 0.0,
                "markers": [],
                "kernel_params": {
                    "tau_a": 0.001,
                    "tau_r": 0.005,
                    "threshold": 3.0,
                    "refractory": 0.015
                },
                "display_mode": "envelope"
            }

        self.save_session_state(template, session_name)

    def delete_session(self, session_name: str):
        """
        Delete a session file.

        Args:
            session_name: Name of session to delete
        """
        session_file = self.sessions_dir / f"{session_name}.json"
        if session_file.exists():
            session_file.unlink()

    def save_local_config(self, config_data: dict):
        """
        Save local config to data/config.json.

        Args:
            config_data: Configuration dictionary
        """
        config_file = self.get_config_file()
        with open(config_file, 'w') as f:
            json.dump(config_data, f, indent=2)

    def load_local_config(self) -> dict:
        """
        Load local config from data/config.json.

        Returns:
            Config dict (returns defaults if file doesn't exist)
        """
        config_file = self.get_config_file()
        if not config_file.exists():
            # Return default config
            return {
                'quick_press_threshold_ms': 200,
                'medium_press_threshold_ms': 500,
                'long_press_threshold_ms': 1000,
            }

        with open(config_file, 'r') as f:
            return json.load(f)

    def get_config_value(self, key: str, default=None):
        """Get a config value with fallback to default."""
        config = self.load_local_config()
        return config.get(key, default)

    def get_cache_dir(self) -> Path:
        """Get cache directory (data/cache/)."""
        cache_dir = self.data_dir / "cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir

    def list_audio_files(self) -> List[Path]:
        """
        List all audio files in audio/ directory.

        Returns:
            List of audio file paths
        """
        audio_files = []
        for ext in ['*.wav', '*.mp3', '*.flac', '*.ogg', '*.m4a']:
            audio_files.extend(self.audio_dir.glob(ext))
        return sorted(audio_files)

    def get_info(self) -> dict:
        """
        Get project information.

        Returns:
            Dictionary with project metadata
        """
        # Count records by type
        data_count = len(self.trs.query(type="data"))
        config_count = len(self.trs.query(type="config"))
        session_count = len(self.trs.query(type="session"))
        log_count = len(self.trs.query(type="log"))
        audio_count = len(self.trs.query(type="audio"))

        # Get DB size
        db_size = self.trs.get_db_size()

        # Get latest records
        latest_data = self.trs.query_latest(type="data")
        latest_session = self.load_session_state()

        return {
            "project_dir": str(self.project_dir),
            "data_dir": str(self.data_dir),
            "sessions_dir": str(self.sessions_dir),
            "db_dir": str(self.db_dir),
            "audio_dir": str(self.audio_dir),
            "current_session": self.current_session,
            "available_sessions": self.list_sessions(),
            "audio_files": [str(f.name) for f in self.list_audio_files()],
            "cwd": str(self.cwd_mgr.get_cwd()),
            "db_size_bytes": db_size,
            "db_size_mb": round(db_size / (1024 * 1024), 2),
            "record_counts": {
                "data": data_count,
                "config": config_count,
                "session": session_count,
                "log": log_count,
                "audio": audio_count,
            },
            "latest_data_timestamp": latest_data.timestamp if latest_data else None,
            "has_local_config": self.get_config_file().exists(),
        }

    def __str__(self) -> str:
        """String representation of project."""
        info = self.get_info()
        sessions = ", ".join(info['available_sessions']) if info['available_sessions'] else "none"
        audio = ", ".join(info['audio_files']) if info['audio_files'] else "none"

        return (f"tau Project\n"
                f"  Directory: {info['project_dir']}\n"
                f"  Current Session: {info['current_session']}\n"
                f"  Available Sessions: {sessions}\n"
                f"  Audio Files: {audio}\n"
                f"  DB Size: {info['db_size_mb']} MB\n"
                f"  Records: {sum(info['record_counts'].values())} total")


# Keep SNNProject as alias for backward compatibility
SNNProject = TauProject
