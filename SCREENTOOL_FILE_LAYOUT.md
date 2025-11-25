# Where Files Go: Screentool + tau Recording

## Quick Answer

When you run:
```bash
export TAU_SRC=~/src/mricos/demos/tau
export AUDIO_RECORDER=tau
st record start && sleep 3 && st record stop
```

**Files go to**: `$ST_DIR/<session_id>/`

- Default `ST_DIR`: **`~/recordings`** (if not set, screentool will error)
- Session ID: Unix epoch timestamp (e.g., `1732518400`)

## Complete File Structure

```
$ST_DIR/                           # Default: ~/recordings
├── <session_id>/                  # e.g., 1732518400/
│   ├── video.mp4                  # Screen recording (with T0 in metadata)
│   ├── audio.wav                  # tau-engine recording (stereo float32)
│   ├── audio.wav.json             # Audio metadata (T0, sample rate, etc.)
│   ├── session.json               # Session metadata (JSON format)
│   ├── session.meta               # Session metadata (bash-sourced)
│   ├── t0                         # T0 timestamp (plain text)
│   ├── video.pid                  # Video recorder PID (during recording)
│   └── audio.pid                  # Audio recorder sentinel (during recording)
│
└── latest -> <session_id>         # Symlink to most recent session
```

## Example Session

```bash
# Setup
export ST_SRC=~/src/screentool
export ST_DIR=~/recordings          # <-- Files go here!
export TAU_SRC=~/src/mricos/demos/tau
export AUDIO_RECORDER=tau

# Record
st record start
# Created: ~/recordings/1732518400/
sleep 3
st record stop

# Check files
ls -la ~/recordings/latest/
```

**Output**:
```
~/recordings/1732518400/
├── video.mp4              33 MB   # Screen capture
├── audio.wav              4.2 MB  # tau-engine recording
├── audio.wav.json         345 B   # T0 metadata
├── session.json           289 B   # Session info
├── session.meta           234 B   # Bash metadata
└── t0                     19 B    # Raw T0 value
```

## File Contents

### `video.mp4`
- H.264 video codec
- Screen capture from ffmpeg
- T0 timestamp embedded in MP4 comment metadata
- Format: `t0_monotonic_ns=1732518400123456789`

### `audio.wav`
- Stereo float32 PCM
- 48kHz sample rate
- Recorded by tau-engine
- Compatible with all audio tools

### `audio.wav.json`
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
  "output_path": "/Users/mricos/recordings/1732518400/audio.wav",
  "engine_socket": "/Users/mricos/tau/runtime/tau.sock",
  "engine_version": "1.0",
  "t1_monotonic_ns": 1732518403234567890,
  "recording_stop_iso": "2025-11-25T10:30:48.234567Z",
  "duration_sec": 3.111111,
  "duration_ns": 3111111101,
  "frames_recorded": 149333,
  "duration_from_engine": 3.111
}
```

**Key field**: `t0_monotonic_ns` - Used for A/V sync!

### `session.json`
```json
{
  "session_id": "1732518400",
  "t0_monotonic_ns": 1732518400123456789,
  "recording_start_iso": "2025-11-25T10:30:45.123456Z",
  "recording_method": "ffmpeg+tau",
  "video_file": "video.mp4",
  "audio_file": "audio.wav",
  "sample_rate": 48000,
  "video_fps": 30
}
```

### `session.meta` (bash-sourced)
```bash
RECORDING_ID="1732518400"
RECORDING_DIR="/Users/mricos/recordings/1732518400"
T0_MONOTONIC_NS="1732518400123456789"
START_TIME="Mon Nov 25 10:30:45 PST 2025"
RECORDING_METHOD="ffmpeg+tau"
VIDEO_FILE="video.mp4"
AUDIO_FILE="audio.wav"
SAMPLE_RATE="48000"
VIDEO_FPS="30"
```

### `t0` (plain text)
```
1732518400123456789
```

## A/V Sync Files

After running `st sync latest`, additional files appear:

```
~/recordings/1732518400/
├── video.mp4              # Original files
├── audio.wav
├── audio.wav.json
│
├── db/                    # TRS database structure
│   ├── 1732518400.video.raw.mp4    # Original video
│   ├── 1732518400.audio.raw.wav    # Original audio
│   └── 1732518400.sync.meta.json   # Sync calculation
│
└── recording.mp4          # Final synced A+V output
```

### `db/1732518400.sync.meta.json`
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

## Important Notes

### ST_DIR Must Be Set

screentool **requires** `ST_DIR` to be set:

```bash
# ❌ Will error
st record start

# ✅ Correct
export ST_DIR=~/recordings
st record start
```

### Session ID = Unix Epoch

Session directories are named with Unix epoch timestamps:
```bash
date +%s
# Output: 1732518400

ls ~/recordings/
# 1732518400/  1732518450/  1732518500/  latest@
```

### "latest" Symlink

The `latest` symlink always points to the most recent session:
```bash
ls -la ~/recordings/latest
# latest -> 1732518500

# Access latest recording
ffplay ~/recordings/latest/video.mp4
```

## Common Workflows

### View Latest Recording

```bash
# Video only
ffplay ~/recordings/latest/video.mp4

# Audio only
ffplay ~/recordings/latest/audio.wav

# Both (after sync)
st sync latest
ffplay ~/recordings/latest/recording.mp4
```

### Copy Recording Elsewhere

```bash
# Copy entire session
cp -r ~/recordings/latest ~/Desktop/my-tutorial/

# Copy just synced video
cp ~/recordings/latest/recording.mp4 ~/Desktop/tutorial.mp4
```

### Clean Up Old Sessions

```bash
# Keep only last 5 sessions
cd ~/recordings
ls -t | tail -n +6 | xargs rm -rf

# Or use find (older than 7 days)
find ~/recordings -type d -name "[0-9]*" -mtime +7 -exec rm -rf {} \;
```

### Check Recording Size

```bash
# Latest session
du -sh ~/recordings/latest/

# All recordings
du -sh ~/recordings/
```

## Customizing ST_DIR

You can change where recordings go:

```bash
# Project-specific recordings
export ST_DIR=~/projects/tutorial/recordings
st record start

# External drive
export ST_DIR=/Volumes/ExternalSSD/screentool-recordings
st record start

# Temporary recordings
export ST_DIR=/tmp/recordings
st record start
```

## Environment Setup Script

Create `~/.screentool_env`:

```bash
#!/usr/bin/env bash
# Screentool + tau environment

export ST_SRC=~/src/screentool
export ST_DIR=~/recordings
export TAU_SRC=~/src/mricos/demos/tau
export AUDIO_RECORDER=tau

# Optional: Add st to PATH
export PATH="$ST_SRC:$PATH"

echo "✓ Screentool environment loaded"
echo "  Recordings: $ST_DIR"
echo "  Audio: $AUDIO_RECORDER (tau-engine)"
```

Then in your shell:
```bash
source ~/.screentool_env
st record start
```

## Summary

**Files Location**: `$ST_DIR/<epoch>/`

- `video.mp4` - Screen recording
- `audio.wav` - tau-engine audio
- `audio.wav.json` - Metadata with T0
- `session.json` - Session info
- `latest/` - Symlink to most recent

**Default Path**: `~/recordings/` (must be set explicitly)

**Access Latest**: `~/recordings/latest/`

**After Sync**: `~/recordings/latest/recording.mp4` (merged A+V)
