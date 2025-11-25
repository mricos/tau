# tau Refactoring Proposal: Library-First Design

## Current State

tau is already well-structured as a Python package with:
- ✅ `tau_lib/` - Core library modules
- ✅ `repl_py/` - REPL interface
- ✅ `tui_py/` - TUI application
- ✅ `engine/` - C audio engine (tau-engine)
- ✅ `pyproject.toml` - Proper Python packaging
- ✅ Auto-start capability in `TauMultitrack` class

## Problem: Screentool Integration

Current screentool integration requires:
1. User manually starts tau-engine daemon
2. Python REPL called via subprocess for each command
3. No lifecycle management (daemon runs forever)

**Desired behavior**: tau-engine should run **only** while screentool is recording.

## Solution: Lifecycle-Managed Recording Context

### 1. Add `TauRecordingSession` Context Manager

**File**: `tau_lib/data/recording_session.py` (new)

```python
"""
Lifecycle-managed recording session with auto-start/stop of tau-engine.
"""
import time
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

from tau_lib.integration.tau_playback import TauMultitrack
from tau_lib.data.recording_api import TauRecorder


class TauRecordingSession:
    """
    Manages tau-engine lifecycle for recording sessions.

    Auto-starts tau-engine when recording starts.
    Auto-stops tau-engine when recording ends.

    Usage:
        session = TauRecordingSession()
        session.start_recording("output.wav", t0_ns)
        # ... tau-engine is running ...
        session.stop_recording()
        # ... tau-engine is stopped ...
    """

    def __init__(self,
                 auto_cleanup: bool = True,
                 socket_path: str = "~/tau/runtime/tau.sock"):
        """
        Args:
            auto_cleanup: Stop tau-engine when recording stops (default: True)
            socket_path: tau-engine socket path
        """
        self.auto_cleanup = auto_cleanup
        self.recorder = TauRecorder(socket_path=socket_path, auto_start=True)
        self.recording = False

    def start_recording(self, output_path: Path, t0_ns: int, **kwargs):
        """Start recording and ensure tau-engine is running."""
        if self.recording:
            raise RuntimeError("Already recording")

        # TauRecorder already auto-starts tau-engine
        metadata = self.recorder.start_recording(output_path, t0_ns, **kwargs)
        self.recording = True
        return metadata

    def stop_recording(self):
        """Stop recording and optionally clean up tau-engine."""
        if not self.recording:
            raise RuntimeError("Not recording")

        metadata = self.recorder.stop_recording()
        self.recording = False

        # Clean up tau-engine if auto_cleanup enabled
        if self.auto_cleanup and self.recorder.tau.engine_process:
            self.recorder.tau._send_command("QUIT")
            self.recorder.tau.engine_process.wait(timeout=2)
            self.recorder.tau.engine_process = None

        return metadata

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, *args):
        """Auto-cleanup on context exit."""
        if self.recording:
            self.stop_recording()


@contextmanager
def recording_session(output_path: Path, t0_ns: int = None, **kwargs):
    """
    Context manager for single recording session.

    Usage:
        with recording_session("output.wav", t0_ns) as session:
            time.sleep(5)  # Recording happens here
        # tau-engine automatically stopped
    """
    if t0_ns is None:
        t0_ns = time.monotonic_ns()

    session = TauRecordingSession()
    session.start_recording(output_path, t0_ns, **kwargs)

    try:
        yield session
    finally:
        session.stop_recording()
```

### 2. Create Bash API for Screentool

**File**: `tau_lib/bash/tau_recording.sh` (new)

```bash
#!/usr/bin/env bash
# tau_recording.sh - Bash API for tau recording with lifecycle management

# REQUIRES: TAU_SRC environment variable
[[ -v TAU_SRC ]] || { echo "Error: TAU_SRC not set"; return 1; }

# Use tau Python package for recording
TAU_PYTHON="${TAU_PYTHON:-python3}"

#
# tau_start_recording <output_file> <t0_ns>
#
# Start tau-engine recording with auto-start.
# tau-engine will be launched if not already running.
#
# Args:
#   output_file: Output WAV path
#   t0_ns: Monotonic timestamp in nanoseconds
#
# Returns:
#   0 on success, non-zero on error
#
tau_start_recording() {
    local output_file="$1"
    local t0_ns="$2"

    [[ -z "$output_file" ]] && { echo "Error: output_file required"; return 1; }
    [[ -z "$t0_ns" ]] && { echo "Error: t0_ns required"; return 1; }

    # Ensure output directory exists
    mkdir -p "$(dirname "$output_file")"

    # Start recording using Python API
    # The TauRecorder class will auto-start tau-engine
    "$TAU_PYTHON" -c "
import sys
sys.path.insert(0, '$TAU_SRC')
from pathlib import Path
from tau_lib.data.recording_api import TauRecorder

recorder = TauRecorder(auto_start=True)
try:
    recorder.start_recording(
        output_path=Path('$output_file'),
        t0_monotonic_ns=$t0_ns
    )
    print('✓ tau-engine recording started')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"
    return $?
}

#
# tau_stop_recording
#
# Stop tau-engine recording.
# Does NOT stop tau-engine daemon (in case other apps are using it).
# Use tau_cleanup_recording for full cleanup.
#
# Returns:
#   0 on success, non-zero on error
#
tau_stop_recording() {
    "$TAU_PYTHON" -c "
import sys
sys.path.insert(0, '$TAU_SRC')
from tau_lib.data.recording_api import TauRecorder

recorder = TauRecorder(auto_start=False)
try:
    recorder.stop_recording()
    print('✓ tau-engine recording stopped')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
"
    return $?
}

#
# tau_cleanup_recording
#
# Stop recording AND stop tau-engine daemon.
# Use this when you're done with tau-engine entirely.
#
# Returns:
#   0 on success, non-zero on error
#
tau_cleanup_recording() {
    # First stop recording
    tau_stop_recording || return 1

    # Then stop tau-engine daemon
    "$TAU_PYTHON" -c "
import sys
sys.path.insert(0, '$TAU_SRC')
from tau_lib.integration.tau_playback import TauMultitrack

tau = TauMultitrack(auto_start=False)
try:
    tau._send_command('QUIT')
    print('✓ tau-engine daemon stopped')
except:
    pass  # Already stopped
"

    # Kill any stray tau-engine processes
    pkill -f tau-engine 2>/dev/null || true

    return 0
}

#
# tau_recording_status
#
# Check if tau-engine is recording.
#
# Returns:
#   0 if recording, 1 if not
#
tau_recording_status() {
    "$TAU_PYTHON" -c "
import sys
sys.path.insert(0, '$TAU_SRC')
from tau_lib.integration.tau_playback import TauMultitrack

tau = TauMultitrack(auto_start=False)
try:
    response = tau._send_command('RECORD STATUS')
    if 'RECORDING' in response:
        print('Recording: Yes')
        sys.exit(0)
    else:
        print('Recording: No')
        sys.exit(1)
except:
    print('Recording: No (tau-engine not running)')
    sys.exit(1)
"
}

# Export functions
export -f tau_start_recording
export -f tau_stop_recording
export -f tau_cleanup_recording
export -f tau_recording_status
```

### 3. Update Screentool Launcher

**Changes to** `screentool/bash/launcher.sh`:

```bash
# At top of file
[[ -v TAU_SRC ]] || TAU_SRC="$HOME/src/mricos/demos/tau"
source "$TAU_SRC/tau_lib/bash/tau_recording.sh"

# In start_audio_recording function, replace tau case:
tau)
    # Use tau bash API with auto-start
    tau_start_recording "$output_file" "$t0_ns"
    echo "tau-session" > "$pid_file"  # Sentinel for cleanup
    ;;

# In stop_audio_recording function, replace tau case:
if [[ "$audio_pid" == "tau-session" ]]; then
    echo "Stopping tau-engine recording session..."
    tau_cleanup_recording  # Stop recording AND daemon
    rm -f "$pid_file"
    return 0
fi
```

## Benefits

### ✅ Clean Lifecycle Management
- tau-engine starts **only** when screentool starts recording
- tau-engine stops **automatically** when screentool stops recording
- No orphaned daemon processes

### ✅ Library-First Design
- screentool uses tau as a Python library (not subprocess)
- Direct imports: `from tau_lib.data.recording_api import TauRecorder`
- Faster, cleaner integration

### ✅ Flexible Usage
- Screentool can use bash API (simple)
- Other tools can use Python API directly (advanced)
- TUI/REPL can use tau-engine independently

### ✅ Resource Efficiency
- tau-engine only runs when needed
- Clean shutdown releases audio device
- No background CPU usage when idle

## Migration Path

### Phase 1: Add New Modules (Non-Breaking)
1. Create `tau_lib/data/recording_session.py`
2. Create `tau_lib/bash/tau_recording.sh`
3. Update `pyproject.toml` to include bash scripts

### Phase 2: Update Screentool (Simple)
1. Source `tau_recording.sh` in launcher
2. Replace subprocess calls with bash functions
3. Test lifecycle (start → record → stop → verify cleanup)

### Phase 3: Documentation
1. Add examples to `tau_lib/data/recording_session.py`
2. Update `QUICKSTART.md` with screentool integration
3. Add lifecycle diagrams

## File Structure After Refactoring

```
tau/
├── engine/
│   └── tau-engine              # C binary
├── tau_lib/
│   ├── data/
│   │   ├── recording_api.py     # Core recording API
│   │   └── recording_session.py # NEW: Lifecycle management
│   ├── integration/
│   │   └── tau_playback.py      # Has auto-start already
│   └── bash/                    # NEW: Bash API
│       └── tau_recording.sh     # NEW: Functions for screentool
├── repl_py/                     # REPL (separate usage)
├── tui_py/                      # TUI (separate usage)
└── pyproject.toml

screentool/
└── bash/
    └── launcher.sh              # Sources tau_recording.sh
```

## Example: Screentool Session

```bash
# User runs:
$ export TAU_SRC=~/src/mricos/demos/tau
$ export AUDIO_RECORDER=tau
$ st record start

# What happens:
1. launcher.sh sources tau_recording.sh
2. tau_start_recording called
3. TauRecorder(auto_start=True) starts tau-engine
4. Recording begins
5. ... user records ...
6. st record stop
7. tau_cleanup_recording stops recording
8. tau_cleanup_recording sends QUIT to tau-engine
9. tau-engine exits cleanly
10. No orphaned processes

# Verify:
$ pgrep tau-engine
# (empty - tau-engine stopped)
```

## Backward Compatibility

- ✅ Existing REPL/TUI usage unchanged
- ✅ Manual daemon mode still works (`tau-engine &`)
- ✅ Python API unchanged (recording_api.py)
- ✅ Only screentool integration changes

## Testing Checklist

- [ ] tau_start_recording auto-starts tau-engine
- [ ] Recording creates valid WAV file
- [ ] tau_cleanup_recording stops daemon
- [ ] No orphaned tau-engine processes after st record stop
- [ ] Multiple record sessions work (start-stop-start-stop)
- [ ] Python API still works for direct usage
- [ ] REPL/TUI unaffected by changes

## Conclusion

This refactoring makes tau a **true library** that screentool can use without leaving daemon processes running. The key insight is:

> **tau-engine should be a service used by screentool, not a separate always-on daemon.**

With auto-start in `TauRecorder` and cleanup in bash API, we get:
- Clean lifecycle
- Resource efficiency
- Library-first design
- No breaking changes
