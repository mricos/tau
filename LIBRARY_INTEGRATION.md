# tau Library Integration - Complete Guide

## Overview

tau is now a **library-first audio recording system** with clean lifecycle management. tau-engine runs **only** when recording, with automatic startup and cleanup.

## What Changed

### Before (Manual Daemon)
```bash
# User had to manage tau-engine manually
tau-engine &              # Start daemon
st record start           # Record (daemon running)
st record stop            # Stop (daemon still running!)
pkill tau-engine          # User must cleanup
```

**Problems**:
- ❌ Orphaned tau-engine processes
- ❌ Audio device held even when idle
- ❌ Manual lifecycle management
- ❌ Resource waste

### After (Library Mode)
```bash
# tau-engine managed automatically
export TAU_SRC=~/src/mricos/demos/tau
export AUDIO_RECORDER=tau

st record start           # Auto-starts tau-engine
# ... recording ...
st record stop            # Auto-stops tau-engine
# No orphaned processes!
```

**Benefits**:
- ✅ Automatic lifecycle management
- ✅ No orphaned processes
- ✅ Audio device released when done
- ✅ Zero-config for screentool users

## Architecture

### Component Structure

```
┌─────────────────────────────────────────┐
│         screentool (bash)               │
│  - launcher.sh sources tau_recording.sh │
└──────────────┬──────────────────────────┘
               │ bash API
               ↓
┌─────────────────────────────────────────┐
│    tau_lib/bash/tau_recording.sh        │
│  - tau_start_recording()                │
│  - tau_stop_recording()                 │
│  - tau_cleanup_recording()              │
└──────────────┬──────────────────────────┘
               │ Python API
               ↓
┌─────────────────────────────────────────┐
│    tau_lib/data/recording_api.py        │
│  - TauRecorder(auto_start=True)         │
│  - start_recording()                    │
│  - stop_recording()                     │
└──────────────┬──────────────────────────┘
               │ Socket
               ↓
┌─────────────────────────────────────────┐
│       engine/tau-engine (C)             │
│  - RECORD START/STOP/STATUS             │
│  - Duplex audio (playback + capture)    │
│  - Auto-started by TauRecorder          │
└─────────────────────────────────────────┘
```

### Lifecycle Flow

```
User: st record start
  ↓
screentool: launcher.sh
  ↓
tau_start_recording() [bash]
  ↓
TauRecorder(auto_start=True) [Python]
  ↓
Check if tau-engine running
  ├─ Yes → Use existing
  └─ No  → Start tau-engine
            ↓
            Spawn tau-engine process
            ↓
            Wait for socket
            ↓
            Send RECORD START command
            ↓
            ✅ Recording active

... user records ...

User: st record stop
  ↓
screentool: launcher.sh
  ↓
tau_cleanup_recording() [bash]
  ↓
Send RECORD STOP
  ↓
Send QUIT command
  ↓
Wait for tau-engine exit
  ↓
Kill any remaining processes
  ↓
✅ Clean shutdown
```

## File Structure

```
tau/
├── engine/
│   ├── tau-engine              # C binary with RECORD commands
│   └── build.sh                # Build script
│
├── tau_lib/                    # Core library (Python)
│   ├── data/
│   │   └── recording_api.py    # TauRecorder with auto-start
│   ├── integration/
│   │   └── tau_playback.py     # TauMultitrack (engine mgmt)
│   └── bash/                   # NEW: Bash API
│       ├── tau_recording.sh    # Functions for screentool
│       └── test_tau_recording.sh  # Test suite
│
├── repl_py/                    # REPL (independent)
├── tui_py/                     # TUI (independent)
│
├── REFACTOR_PROPOSAL.md        # Design document
├── LIBRARY_INTEGRATION.md      # This file
└── pyproject.toml              # Python package config

screentool/
└── bash/
    └── launcher.sh             # Sources tau_recording.sh
```

## API Reference

### Bash API

Source: `tau_lib/bash/tau_recording.sh`

#### tau_start_recording

Start recording with auto-start of tau-engine.

```bash
tau_start_recording <output_file> <t0_ns>

# Example:
T0=$(python3 -c 'import time; print(int(time.monotonic_ns()))')
tau_start_recording "/tmp/recording.wav" "$T0"
```

**Behavior**:
- Checks if tau-engine running
- Starts tau-engine if not running
- Sends RECORD START command
- Returns 0 on success

#### tau_stop_recording

Stop recording (keeps tau-engine running).

```bash
tau_stop_recording

# Returns:
#   0 on success
#   1 if no recording active
```

#### tau_cleanup_recording

Stop recording AND stop tau-engine daemon.

```bash
tau_cleanup_recording

# Does:
#   1. Stop recording (if active)
#   2. Send QUIT to tau-engine
#   3. Kill any remaining processes
#   4. Verify cleanup
```

**Use this** when done with tau-engine entirely (screentool uses this).

#### tau_recording_status

Check if currently recording.

```bash
if tau_recording_status; then
    echo "Recording active"
else
    echo "Not recording"
fi
```

#### tau_engine_status

Check if tau-engine daemon is running.

```bash
if tau_engine_status; then
    echo "tau-engine is running"
else
    echo "tau-engine is stopped"
fi
```

### Python API

Source: `tau_lib/data/recording_api.py`

```python
from tau_lib.data.recording_api import TauRecorder
from pathlib import Path
import time

# Auto-start mode (recommended for screentool)
recorder = TauRecorder(auto_start=True)

# Capture T0 for sync
t0_ns = time.monotonic_ns()

# Start recording (tau-engine starts automatically if needed)
metadata = recorder.start_recording(
    output_path=Path("recording.wav"),
    t0_monotonic_ns=t0_ns
)

# ... record ...

# Stop recording
final_metadata = recorder.stop_recording()

# Cleanup tau-engine (optional)
recorder.tau._send_command("QUIT")
```

## Environment Variables

### Required

- **`TAU_SRC`**: Path to tau source directory
  ```bash
  export TAU_SRC=~/src/mricos/demos/tau
  ```

### Optional

- **`TAU_PYTHON`**: Python interpreter (default: `python3`)
  ```bash
  export TAU_PYTHON=/usr/local/bin/python3.11
  ```

- **`TAU_RUNTIME`**: Runtime directory for sockets (default: `~/tau/runtime`)
  ```bash
  export TAU_RUNTIME=/tmp/tau
  ```

- **`AUDIO_RECORDER`**: For screentool (set to `tau`)
  ```bash
  export AUDIO_RECORDER=tau
  ```

## Screentool Integration

### Setup

```bash
# 1. Set environment
export ST_SRC=~/src/screentool
export ST_DIR=~/recordings
export TAU_SRC=~/src/mricos/demos/tau
export AUDIO_RECORDER=tau

# 2. Use screentool normally
st record start
# tau-engine starts automatically
# Recording begins

# 3. Stop recording
st record stop
# tau-engine stops automatically
# Clean shutdown

# 4. Verify no orphaned processes
pgrep tau-engine
# (empty output = clean)
```

### What Happens

1. **Start**: `st record start`
   - launcher.sh sources `tau_recording.sh`
   - Calls `tau_start_recording()`
   - TauRecorder checks if tau-engine running
   - If not running: spawns tau-engine process
   - Waits for socket to appear
   - Sends `RECORD START` command
   - Recording begins

2. **Stop**: `st record stop`
   - launcher.sh calls `tau_cleanup_recording()`
   - Sends `RECORD STOP` command
   - Sends `QUIT` command to tau-engine
   - Waits for graceful shutdown
   - Kills any remaining processes
   - Verifies cleanup

3. **Result**:
   - ✅ Recording saved with T0 metadata
   - ✅ tau-engine stopped
   - ✅ No orphaned processes
   - ✅ Audio device released

## Testing

### Test Bash API

```bash
cd ~/src/mricos/demos/tau
./tau_lib/bash/test_tau_recording.sh
```

**Tests**:
1. ✅ tau-engine initially stopped
2. ✅ Auto-start on recording
3. ✅ Recording works
4. ✅ Status commands work
5. ✅ WAV file created
6. ✅ Cleanup stops daemon
7. ✅ No orphaned processes

### Test with Screentool

```bash
# Setup
export TAU_SRC=~/src/mricos/demos/tau
export ST_SRC=~/src/screentool
export ST_DIR=/tmp/test-recordings
export AUDIO_RECORDER=tau

# Ensure tau-engine is stopped
pkill -f tau-engine || true

# Test recording
st record start
sleep 3
st record stop

# Verify cleanup
pgrep -f tau-engine && echo "FAIL: tau-engine still running" || echo "PASS: Clean shutdown"

# Check recording
ffprobe /tmp/test-recordings/latest/audio.wav
```

## Troubleshooting

### tau-engine won't start

```bash
# Check TAU_SRC
echo $TAU_SRC
# Should point to: ~/src/mricos/demos/tau

# Check binary exists
ls -la $TAU_SRC/engine/tau-engine
# Should show executable

# Rebuild if needed
cd $TAU_SRC/engine
./build.sh
```

### Orphaned tau-engine processes

```bash
# Force cleanup
pkill -KILL -f tau-engine

# Remove stale sockets
rm -f ~/tau/runtime/tau.sock

# Restart recording
st record start
```

### Recording fails

```bash
# Check tau-engine status
export TAU_SRC=~/src/mricos/demos/tau
source $TAU_SRC/tau_lib/bash/tau_recording.sh
tau_engine_status

# Check recording status
tau_recording_status

# Manual test
T0=$(python3 -c 'import time; print(int(time.monotonic_ns()))')
tau_start_recording /tmp/test.wav $T0
sleep 2
tau_cleanup_recording

# Check output
ffprobe /tmp/test.wav
```

### Python import errors

```bash
# Check Python path
python3 -c "import sys; print('\n'.join(sys.path))"

# Install tau package (optional)
cd ~/src/mricos/demos/tau
pip install -e .

# Or use TAU_SRC (recommended)
export TAU_SRC=~/src/mricos/demos/tau
# Python scripts use: sys.path.insert(0, TAU_SRC)
```

## Performance

### Resource Usage

**Before** (daemon mode):
- tau-engine runs 24/7
- Audio device held continuously
- ~5-10 MB RAM constantly
- CPU cycles for OSC/socket polling

**After** (library mode):
- tau-engine runs only during recording
- Audio device held only when needed
- 0 MB RAM when idle
- No CPU usage when idle

### Startup Time

- tau-engine startup: ~100-200ms
- Socket creation: ~50ms
- Total overhead: ~250ms
- **Impact**: Negligible for recording sessions

### Recording Quality

- ✅ Stereo float32 at 48kHz
- ✅ Frame-accurate T0 sync
- ✅ No audio dropouts
- ✅ Identical to daemon mode

## Migration Checklist

For users switching from daemon mode to library mode:

- [ ] Set `TAU_SRC` environment variable
- [ ] Update launcher.sh to source tau_recording.sh
- [ ] Change `AUDIO_RECORDER=tau`
- [ ] Remove manual `tau-engine &` from scripts
- [ ] Remove manual `pkill tau-engine` from cleanup
- [ ] Test: `st record start` → `st record stop`
- [ ] Verify: `pgrep tau-engine` returns empty
- [ ] Confirm: WAV files have correct T0 metadata

## Future Enhancements

### Multi-Session Support

Allow multiple simultaneous recordings:
- Each session gets unique socket
- Screentool manages per-session daemons
- Cleanup only stops owned tau-engine

### Resource Pooling

Reuse tau-engine across quick sessions:
- Keep daemon alive for N seconds after stop
- Next recording reuses existing daemon
- Timeout kills daemon if idle

### systemd Integration

Optional system service:
- `systemctl start tau-engine`
- Socket activation
- Automatic restart on crash

## Credits

- **tau-engine**: C audio engine with miniaudio
- **tau_lib**: Python library and bash API
- **screentool**: Screen recording integration
- **Author**: mricos

## Version

- tau: 0.1.0
- Library integration: v1.0 (2025-11-25)
- API: Stable

---

**Questions?** See:
- `REFACTOR_PROPOSAL.md` - Design rationale
- `QUICKSTART.md` - Quick start guide
- `tau_lib/bash/tau_recording.sh` - Bash API source
- `tau_lib/data/recording_api.py` - Python API source
