"""
Canonical tau-engine connection policy.

Startup precedence:
  1. Connect to existing engine at $TAU_SOCKET (default ~/tau/runtime/tau.sock)
  2. Direct-start engine in current session at the shared socket path
     (inherits caller's audio session — sound works on macOS)

Every caller that needs a TauMultitrack should use connect_engine().
"""

import atexit
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _default_socket() -> Path:
    return Path(os.environ.get(
        "TAU_SOCKET",
        str(Path.home() / "tau" / "runtime" / "tau.sock"),
    ))


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
    """Result of connect_engine(). Check .ok before using .engine."""
    engine: Optional['TauMultitrack'] = None
    method: str = "none"   # "tsm", "started", "none"
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.engine is not None


_started_process: Optional[subprocess.Popen] = None
_atexit_registered: bool = False


def _cleanup():
    global _started_process
    if _started_process and _started_process.poll() is None:
        _started_process.terminate()
        try:
            _started_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _started_process.kill()
    _started_process = None


def connect_engine(auto_start: bool = True) -> EngineResult:
    """
    Connect to tau-engine using the canonical startup precedence.

    Returns:
        EngineResult with .engine, .method, .error
    """
    from tau_lib.integration.tau_playback import TauMultitrack

    sock = _default_socket()

    # ── Step 1: Try existing engine at shared socket ──
    if sock.exists():
        try:
            engine = TauMultitrack(socket_path=str(sock))
            if engine.check_connection():
                return EngineResult(engine=engine, method="tsm")
        except Exception:
            pass
        try:
            sock.unlink()
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

    global _started_process, _atexit_registered
    sock.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        [str(binary), "--socket", str(sock)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _started_process = proc
    if not _atexit_registered:
        atexit.register(_cleanup)
        _atexit_registered = True

    for _ in range(30):
        time.sleep(0.1)
        if sock.exists():
            break

    if not sock.exists():
        proc.kill()
        _started_process = None
        return EngineResult(error="tau-engine started but socket not created")

    try:
        engine = TauMultitrack(socket_path=str(sock))
        if engine.check_connection():
            return EngineResult(engine=engine, method="started")
    except Exception:
        pass

    proc.kill()
    _started_process = None
    return EngineResult(error="tau-engine started but not responding")
