# Library-First Design

Design rationale and architecture for tau's library-first recording system.

## Problem

Screentool integration previously required manually managing a tau-engine daemon:
1. User starts tau-engine as background process
2. Python REPL called via subprocess for each command
3. No lifecycle management — daemon runs forever, orphaned processes, audio device held idle

## Design Principle

> tau-engine should be a service used by screentool, not a separate always-on daemon.

tau-engine runs **only** while recording, with automatic startup and cleanup.

## Architecture

```
┌─────────────────────────────────────────┐
│         screentool (bash)               │
│  - launcher.sh sources tau_recording.sh │
└──────────────┬──────────────────────────┘
               │ bash API
               v
┌─────────────────────────────────────────┐
│    tau_lib/bash/tau_recording.sh        │
│  - tau_start_recording()                │
│  - tau_stop_recording()                 │
│  - tau_cleanup_recording()              │
└──────────────┬──────────────────────────┘
               │ Python API
               v
┌─────────────────────────────────────────┐
│    tau_lib/data/recording_api.py        │
│  - TauRecorder(auto_start=True)         │
│  - start_recording()                    │
│  - stop_recording()                     │
└──────────────┬──────────────────────────┘
               │ Unix socket
               v
┌─────────────────────────────────────────┐
│       engine/tau-engine (C)             │
│  - RECORD START/STOP/STATUS             │
│  - Duplex audio (playback + capture)    │
│  - Auto-started by TauRecorder          │
└─────────────────────────────────────────┘
```

## Lifecycle Flow

```
st record start
  -> launcher.sh
  -> tau_start_recording() [bash]
  -> TauRecorder(auto_start=True) [Python]
  -> Check engine running?
     ├─ Yes: reuse
     └─ No:  spawn tau-engine -> wait for socket
  -> Send RECORD START
  -> Recording active

st record stop
  -> launcher.sh
  -> tau_cleanup_recording() [bash]
  -> Send RECORD STOP
  -> Send QUIT
  -> Wait for exit
  -> Kill stragglers
  -> Clean shutdown
```

## Key Modules

| Module | Role |
|--------|------|
| `tau_lib/data/recording_api.py` | TauRecorder with auto-start |
| `tau_lib/data/recording_session.py` | Context manager for lifecycle |
| `tau_lib/integration/tau_playback.py` | TauMultitrack engine management |
| `tau_lib/bash/tau_recording.sh` | Bash API for screentool |

## Screentool Launcher Changes

```bash
# At top of launcher.sh
[[ -v TAU_SRC ]] || TAU_SRC="$HOME/src/tau"
source "$TAU_SRC/tau_lib/bash/tau_recording.sh"

# Start recording
tau)
    tau_start_recording "$output_file" "$t0_ns"
    echo "tau-session" > "$pid_file"
    ;;

# Stop recording
if [[ "$audio_pid" == "tau-session" ]]; then
    tau_cleanup_recording
    rm -f "$pid_file"
fi
```

## Migration Path

1. **Phase 1** (non-breaking): Add `recording_session.py`, `tau_recording.sh`
2. **Phase 2**: Update screentool launcher to use bash API
3. **Phase 3**: Documentation updates

## Backward Compatibility

- Existing REPL/TUI usage unchanged
- Manual daemon mode still works (`tau-engine &`)
- Python recording API unchanged
- Only screentool integration changes

## Resource Impact

| Metric | Daemon mode | Library mode |
|--------|-------------|--------------|
| RAM when idle | ~5-10 MB | 0 |
| Audio device | Held always | Only during recording |
| Startup overhead | N/A | ~250ms |
| Recording quality | Stereo float32 48kHz | Identical |
