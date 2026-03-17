# A/V Sync Specification

tau uses monotonic clock timestamps (T0) to synchronize audio recordings with screen capture video. Both streams embed the same T0 reference, enabling frame-accurate alignment.

## T0 Timestamp

- **Clock**: `time.monotonic_ns()` (Python) / `clock_gettime(CLOCK_MONOTONIC)` (C)
- **Unit**: Nanoseconds (int64)
- **Captured**: Once at session start, shared by all recorders
- **Constraint**: Must be captured before either recorder starts

## Session Directory Format

```
$ST_DIR/                           # Set via environment (required)
├── <session_id>/                  # Unix epoch timestamp (e.g., 1732518400)
│   ├── video.mp4                  # Screen capture (H.264, T0 in MP4 comment)
│   ├── audio.wav                  # tau-engine recording (stereo float32 48kHz)
│   ├── audio.wav.json             # Audio metadata with T0
│   ├── session.json               # Session metadata
│   ├── session.meta               # Bash-sourceable metadata
│   ├── t0                         # Raw T0 value (plain text)
│   ├── video.pid                  # Video recorder PID (during recording)
│   └── audio.pid                  # Audio recorder sentinel (during recording)
└── latest -> <session_id>         # Symlink to most recent session
```

### Post-Sync Files (after `st sync <id>`)

```
<session_id>/
├── db/
│   ├── <id>.video.raw.mp4        # Original video
│   ├── <id>.audio.raw.wav        # Original audio
│   └── <id>.sync.meta.json       # Sync calculation
└── recording.mp4                  # Final muxed A+V output
```

## Metadata Schemas

### audio.wav.json

```json
{
  "t0_monotonic_ns": 1732518400123456789,
  "recording_start_iso": "2025-11-25T10:30:45.123456Z",
  "sample_rate": 48000,
  "channels": 2,
  "bit_depth": 32,
  "sample_format": "float32",
  "format": "wav",
  "track_id": 1,
  "output_path": "<absolute path>",
  "engine_socket": "<socket path>",
  "engine_version": "1.0",
  "t1_monotonic_ns": 1732518403234567890,
  "recording_stop_iso": "2025-11-25T10:30:48.234567Z",
  "duration_sec": 3.111111,
  "duration_ns": 3111111101,
  "frames_recorded": 149333,
  "duration_from_engine": 3.111
}
```

Key field: `t0_monotonic_ns` — used for A/V sync.

### session.json

```json
{
  "session_id": "<epoch>",
  "t0_monotonic_ns": 1732518400123456789,
  "recording_start_iso": "2025-11-25T10:30:45.123456Z",
  "recording_method": "ffmpeg+tau",
  "video_file": "video.mp4",
  "audio_file": "audio.wav",
  "sample_rate": 48000,
  "video_fps": 30
}
```

### session.meta (bash-sourceable)

```bash
RECORDING_ID="<epoch>"
RECORDING_DIR="<path>"
T0_MONOTONIC_NS="<int64>"
START_TIME="<human readable>"
RECORDING_METHOD="ffmpeg+tau"
VIDEO_FILE="video.mp4"
AUDIO_FILE="audio.wav"
SAMPLE_RATE="48000"
VIDEO_FPS="30"
```

### t0 (plain text)

```
1732518400123456789
```

### video.mp4 T0 Embedding

T0 stored in MP4 comment metadata field: `t0_monotonic_ns=<value>`

## Sync Process

1. Run `st sync <session_id>`
2. Read T0 from video metadata and `audio.wav.json`
3. Compute delta: `delta_ns = video_t0 - audio_t0`
4. Merge with ffmpeg `-itsoffset` for the computed delta
5. Output `recording.mp4` (muxed A+V)

### Sync Metadata (`db/<id>.sync.meta.json`)

```json
{
  "video_t0_ns": 1732518400123456789,
  "audio_t0_ns": 1732518400123456789,
  "delta_ns": 0,
  "delta_sec": 0.0,
  "sync_method": "itsoffset",
  "merged_file": "../recording.mp4"
}
```

## Constraints

- Both recorders must use the same monotonic clock source
- Audio latency: ~250ms (engine startup + socket creation)
- `ST_DIR` must be set — screentool will error without it
- Session IDs are Unix epoch timestamps from `date +%s`
- `latest` symlink always points to most recent session
