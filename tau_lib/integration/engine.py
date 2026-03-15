"""
Canonical tau-engine connection policy.

Startup precedence:
  1. Connect to existing engine at ~/tau/runtime/tau.sock
     (user ran `tau start` from their terminal — has audio access)
  2. Direct-start engine in current session at the shared socket path
     (inherits caller's audio session — sound works on macOS)

TSM `setsid` detaches from the macOS audio session, so we never
auto-start via `tsm start` from Python. If the user wants TSM
management, they run `tau start` themselves first.

Every caller that needs a TauMultitrack should use connect_engine().
"""

import atexit
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── Constants ──

TAU_SOCKET = Path.home() / "tau" / "runtime" / "tau.sock"
TAU_RUNTIME_DIR = Path.home() / "tau" / "runtime"


def _find_engine_binary() -> Optional[Path]:
    """Locate tau-engine binary. Checks project tree then PATH."""
    project_root = Path(__file__).parent.parent.parent
    candidate = project_root / "engine" / "tau-engine"
    if candidate.exists() and os.access(candidate, os.X_OK):
        return candidate

    try:
        r = subprocess.run(
            ["which", "tau-engine"], capture_output=True, text=True, timeout=2
        )
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


@dataclass
class EngineResult:
    """Result of connect_engine() — always check .ok before using .engine."""
    engine: Optional['TauMultitrack'] = None
    method: str = "none"   # "tsm", "started", "none"
    error: str = ""
    process: Optional[subprocess.Popen] = None  # non-None if we started it

    @property
    def ok(self) -> bool:
        return self.engine is not None


# Module-level ref so atexit can clean up
_started_process: Optional[subprocess.Popen] = None


def _cleanup():
    global _started_process
    if _started_process and _started_process.poll() is None:
        _started_process.terminate()
        try:
            _started_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _started_process.kill()
    _started_process = None
    # Don't remove TAU_SOCKET — another process may own it


def connect_engine(auto_start: bool = True) -> EngineResult:
    """
    Connect to tau-engine using the canonical startup precedence.

    Args:
        auto_start: If True, start engine when not running.
                    If False, only connect to existing engine.

    Returns:
        EngineResult with .engine, .method, .error
    """
    from tau_lib.integration.tau_playback import TauMultitrack

    # ── Step 1: Try existing engine at shared socket ──
    if TAU_SOCKET.exists():
        try:
            engine = TauMultitrack(
                socket_path=str(TAU_SOCKET), auto_start=False
            )
            if engine.check_connection():
                return EngineResult(engine=engine, method="tsm")
        except Exception:
            pass
        # Stale socket — clean it up
        try:
            TAU_SOCKET.unlink()
        except OSError:
            pass

    if not auto_start:
        return EngineResult(error="tau-engine not running (try: tau start)")

    # ── Step 2: Direct-start at shared socket (inherits audio session) ──
    binary = _find_engine_binary()
    if binary is None:
        return EngineResult(
            error="tau-engine binary not found (tried project tree and PATH)"
        )

    global _started_process
    TAU_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [str(binary), "--socket", str(TAU_SOCKET)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # No start_new_session — stay in caller's audio session
    )
    _started_process = proc
    atexit.register(_cleanup)

    # Wait for socket
    for _ in range(30):
        time.sleep(0.1)
        if TAU_SOCKET.exists():
            break

    if not TAU_SOCKET.exists():
        proc.kill()
        _started_process = None
        return EngineResult(error="tau-engine started but socket not created")

    try:
        engine = TauMultitrack(
            socket_path=str(TAU_SOCKET), auto_start=False
        )
        if engine.check_connection():
            return EngineResult(engine=engine, method="started", process=proc)
    except Exception:
        pass

    proc.kill()
    _started_process = None
    return EngineResult(error="tau-engine started but not responding")
