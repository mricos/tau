# Recording API Specification

Python and Bash APIs for lifecycle-managed audio recording. tau-engine runs only during active recording sessions.

## Python API

### TauRecorder

**Module**: `tau_lib.data.recording_api`

```python
from tau_lib.data.recording_api import TauRecorder

recorder = TauRecorder(auto_start=True)
```

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `socket_path` | `str` | `~/tau/runtime/tau.sock` | Engine socket path |
| `auto_start` | `bool` | `False` | Auto-start engine if not running |

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `start_recording(output_path, t0_monotonic_ns)` | `dict` | Begin recording, returns metadata |
| `stop_recording()` | `dict` | Stop recording, returns final metadata |

### TauRecordingSession

**Module**: `tau_lib.data.recording_session`

Context manager wrapping TauRecorder with automatic engine lifecycle.

```python
from tau_lib.data.recording_session import TauRecordingSession, recording_session
from pathlib import Path
import time

# Class-based
with TauRecordingSession(auto_cleanup=True) as session:
    session.start_recording(Path("out.wav"), time.monotonic_ns())
    # ... recording ...
    session.stop_recording()
# Engine automatically stopped

# Function-based
with recording_session(Path("out.wav")) as session:
    time.sleep(5)  # Recording happens here
# Engine automatically stopped
```

#### Constructor

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `auto_cleanup` | `bool` | `True` | Stop engine when recording stops |
| `socket_path` | `str` | `~/tau/runtime/tau.sock` | Engine socket path |

## Bash API

**Source**: `tau_lib/bash/tau_recording.sh`

### Functions

| Function | Args | Description |
|----------|------|-------------|
| `tau_start_recording` | `<output_file> <t0_ns>` | Start recording with auto-start |
| `tau_stop_recording` | none | Stop recording (keep engine) |
| `tau_cleanup_recording` | none | Stop recording AND stop engine |
| `tau_recording_status` | none | Check if recording (exit 0=yes) |
| `tau_engine_status` | none | Check if engine running (exit 0=yes) |

### Example

```bash
source $TAU_SRC/tau_lib/bash/tau_recording.sh

T0=$(python3 -c 'import time; print(int(time.monotonic_ns()))')
tau_start_recording "/tmp/recording.wav" "$T0"
sleep 5
tau_cleanup_recording
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TAU_SRC` | Yes | - | Path to tau source directory |
| `TAU_PYTHON` | No | `python3` | Python interpreter |
| `TAU_RUNTIME` | No | `~/tau/runtime` | Runtime directory for sockets |
| `AUDIO_RECORDER` | No | - | Set to `tau` for screentool |

## Lifecycle

```
Start:  tau_start_recording()
        -> check engine running
        -> spawn if needed
        -> wait for socket
        -> RECORD START

Stop:   tau_cleanup_recording()
        -> RECORD STOP
        -> QUIT
        -> wait for exit
        -> kill stragglers
```

## Recording Output

- **Format**: WAV, stereo float32, 48kHz
- **Metadata**: JSON sidecar (`<file>.json`) with T0 timestamps
- **T0 field**: `t0_monotonic_ns` -- monotonic clock nanoseconds for A/V sync
- **Session format**: See [av-sync.md](av-sync.md) for full schema
