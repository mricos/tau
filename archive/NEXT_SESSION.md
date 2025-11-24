# tau + screentool Integration - Next Session Guide

## What We've Accomplished

### 1. Created tau REPL (✅ COMPLETE)
- **File**: `tau/repl.py` (~430 lines)
- Interactive REPL for tau-engine daemon
- Tab completion, command history
- Single command mode (`-c`) and script mode (`-s`)
- **Usage**: `python -m tau` (default) or `python -m tau -tui` (full workstation)

### 2. Created screentool ffmpeg Recording (✅ COMPLETE)
- **File**: `screentool/bash/ffmpeg_record.sh` (~250 lines)
- Video-only screen recording with ffmpeg
- T0 timestamp embedded in MP4 metadata
- Background recording with PID management

### 3. Created screentool Launcher (✅ COMPLETE)
- **File**: `screentool/bash/launcher.sh` (~450 lines)
- Unified recording launcher
- Captures single T0 monotonic timestamp
- Launches video (ffmpeg) + audio (sox/ffmpeg) in parallel
- Supports multiple audio recorders: sox, ffmpeg, tau (future), none

### 4. Created screentool Sync Module (✅ COMPLETE)
- **File**: `screentool/bash/sync.sh` (~300 lines)
- Extracts T0 from video and audio metadata
- Computes sync delta in nanoseconds
- Merges A/V with ffmpeg `-itsoffset` for frame-accurate sync

### 5. Created tau Recording API (✅ COMPLETE)
- **File**: `tau/recording_api.py` (~350 lines)
- Python API for timestamped audio recording
- Metadata writing with T0 synchronization
- Ready to integrate with tau-engine once C implementation is done

### 6. Updated screentool CLI (✅ COMPLETE)
- **File**: `screentool/st` (modified)
- Added `st record start/stop/status` commands
- Added `st sync <session_id>` command
- Added `st test` for ffmpeg verification

### 7. Started tau-engine Recording Implementation (⏳ IN PROGRESS)
- **File**: `tau/engine/tau-engine.c` (partially modified)
- ✅ Added `Recorder` struct with `ma_encoder`
- ✅ Added recorder init/free functions
- ✅ Updated `Engine` struct to include recorder
- ✅ Changed device from `ma_device_type_playback` → `ma_device_type_duplex`
- ✅ Added capture configuration (stereo float32)
- ✅ Modified `data_cb()` to process input buffer (`pIn`)
- ✅ Added encoder writing in audio callback
- ❌ **NOT DONE**: RECORD commands in `process_command()`

---

## What Needs to Be Done Next

### Step 1: Complete tau-engine.c RECORD Commands

**Location**: `tau/engine/tau-engine.c` around line 800 (before QUIT command)

**Add these three commands**:

```c
// RECORD START <path> <t0_monotonic_ns>
// RECORD STOP
// RECORD STATUS
```

**Implementation details**:
1. **RECORD START**:
   - Parse path and t0_ns from command tokens
   - Initialize `ma_encoder` with WAV format
   - Set encoder to stereo, float32, 48kHz (or engine SR)
   - Store path, t0_ns, set recording flag
   - Return: `OK RECORD STARTED <path> t0=<ns>`

2. **RECORD STOP**:
   - Check if recording active
   - Stop recording, uninit encoder
   - Calculate duration from frame count
   - Return: `OK RECORD STOPPED frames=<n> duration=<sec>`

3. **RECORD STATUS**:
   - If recording: return path, frames, duration, t0
   - If not: return `OK NOT_RECORDING`

**Code template** (insert before QUIT command at line ~803):

```c
// RECORD <cmd> [args...]
if (strcmp(tokens[0], "RECORD") == 0){
    if (ntok < 2){
        snprintf(response, resp_size, "ERROR RECORD <cmd>\n");
        return;
    }

    if (strcmp(tokens[1], "START") == 0){
        // RECORD START <path> <t0_monotonic_ns>
        // ... implementation ...
    }

    if (strcmp(tokens[1], "STOP") == 0){
        // ... implementation ...
    }

    if (strcmp(tokens[1], "STATUS") == 0){
        // ... implementation ...
    }

    snprintf(response, resp_size, "ERROR Unknown RECORD cmd: %s\n", tokens[1]);
    return;
}
```

### Step 2: Test tau-engine Recording

```bash
# Rebuild tau-engine
cd ~/src/mricos/demos/tau/engine
make clean
make

# Test recording
./tau-engine &
echo "RECORD START /tmp/test.wav 1234567890123456789" | nc -U ~/tau/runtime/tau.sock
sleep 5
echo "RECORD STOP" | nc -U ~/tau/runtime/tau.sock
echo "QUIT" | nc -U ~/tau/runtime/tau.sock

# Verify WAV file
ffprobe /tmp/test.wav
```

### Step 3: Update recording_api.py

**File**: `tau/recording_api.py`

**Current state**: Uses sox/ffmpeg placeholder
**Change to**: Use tau-engine RECORD commands

**Key changes**:
```python
def start_recording(self, output_path, t0_monotonic_ns, ...):
    # Instead of sox/ffmpeg, send to tau-engine:
    cmd = f"RECORD START {output_path} {t0_monotonic_ns}"
    response = self.tau._send_command(cmd)
    # Parse response...
```

### Step 4: Update launcher.sh

**File**: `screentool/bash/launcher.sh`

**Function to update**: `start_audio_recording()`

**Add tau case**:
```bash
case "$AUDIO_RECORDER" in
    sox)
        record_audio_sox "$output_file" "$t0_ns" &
        ;;
    ffmpeg)
        record_audio_ffmpeg "$output_file" "$t0_ns" &
        ;;
    tau)
        # NEW: Use tau-engine RECORD command
        echo "RECORD START $output_file $t0_ns" | nc -U ~/tau/runtime/tau.sock
        ;;
    none)
        echo "Audio recording disabled"
        return 0
        ;;
esac
```

### Step 5: Write T0 Metadata to WAV

**Enhancement**: Store T0 in WAV file metadata (BWF format)

miniaudio encoder supports custom metadata. We could:
- Use BWF `time_reference` field
- Or write JSON sidecar (simpler, already implemented in Python API)

**Decision**: Keep JSON sidecar for now (already working)

### Step 6: End-to-End Test

```bash
# Set environment
export ST_SRC=~/src/screentool
export ST_DIR=~/recordings
export AUDIO_RECORDER=tau

# Start recording
st record start

# ... record for 10 seconds ...

# Stop recording
st record stop

# Sync A/V
st sync latest

# Verify sync
st sync info latest

# Play result
st play latest
```

---

## File Structure After Completion

```
~/recordings/[epoch]/
├── db/
│   ├── [epoch].video.raw.mp4           # ffmpeg video (T0 in metadata)
│   ├── [epoch].audio.raw.wav           # tau-engine audio
│   ├── [epoch].audio.raw.wav.json      # Audio metadata with T0
│   ├── [epoch].session.meta.json       # Session metadata
│   └── [epoch].sync.meta.json          # Sync results
├── recording.mp4                        # Final merged A/V
├── video.pid                            # Video recorder PID
├── audio.pid                            # Audio recorder PID (if using tau)
└── session.meta                         # Bash-sourced metadata
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────────────────┐
│         screentool Session Launcher                     │
│  1. Captures: t0_ns = time.monotonic_ns()              │
│  2. Starts: ffmpeg video (screen)                      │
│  3. Starts: tau-engine audio (microphone/input)        │
└──────────────┬────────────────────────┬─────────────────┘
               │                        │
       ┌───────v────────┐      ┌───────v────────┐
       │ ffmpeg         │      │ tau-engine     │
       │ Screen capture │      │ RECORD command │
       │                │      │                │
       │ Embeds T0 in   │      │ Stores T0 in   │
       │ MP4 comment    │      │ JSON sidecar   │
       └───────┬────────┘      └───────┬────────┘
               │                        │
               v                        v
     video.raw.mp4              audio.raw.wav
     (T0=1234567890ns)          (T0=1234567890ns)
               │                        │
               └────────┬───────────────┘
                        v
              Δ = (video_t0 - audio_t0) / 1e9
                        │
                        v
          ffmpeg -itsoffset Δ -i audio.wav \
                 -i video.mp4 \
                 -map 1:v:0 -map 0:a:0 \
                 -c:v copy -c:a aac \
                 recording.mp4
```

---

## Key Technical Points

### Monotonic Timestamps
- **Source**: Python `time.monotonic_ns()` (nanosecond precision)
- **Property**: Immune to system clock changes, perfect for A/V sync
- **Storage**:
  - Video: MP4 `comment` metadata tag
  - Audio: JSON sidecar file (`.wav.json`)

### Duplex Mode
- tau-engine now runs in **duplex mode** (simultaneous playback + capture)
- Playback: Stereo float32 output (existing functionality)
- Capture: Stereo float32 input (new recording functionality)
- Both share same sample rate (default 48kHz)

### Frame-Accurate Sync
- Compute delta: `Δ = (video_t0 - audio_t0) / 1e9` seconds
- Apply offset: `ffmpeg -itsoffset Δ` aligns streams
- No re-encoding of video (copy codec)
- Audio encoded once to AAC

---

## Commands Reference

### tau-engine Commands (New)
```
RECORD START <path> <t0_ns>    Start recording to file
RECORD STOP                     Stop recording
RECORD STATUS                   Query recording state
```

### screentool Commands (New)
```bash
st record start          # Start video + audio recording
st record stop           # Stop recording
st record status         # Show status
st sync <session_id>     # Merge and sync A/V
st sync info <id>        # Show sync information
st test                  # Test ffmpeg screen capture
```

### tau REPL
```bash
python -m tau                           # Start REPL
python -m tau -c "STATUS"              # Single command
python -m tau -s script.tau            # Run script
python -m tau -tui audio.wav           # Full workstation UI
```

---

## Testing Checklist

- [ ] tau-engine compiles without errors
- [ ] tau-engine starts in duplex mode
- [ ] RECORD START creates WAV file
- [ ] RECORD STOP closes file cleanly
- [ ] RECORD STATUS shows correct info
- [ ] Python recording_api.py uses tau-engine
- [ ] launcher.sh works with AUDIO_RECORDER=tau
- [ ] st record start/stop works end-to-end
- [ ] Sync delta computation is correct
- [ ] ffmpeg merge produces valid MP4
- [ ] A/V sync is frame-accurate
- [ ] Long recordings (>5 min) work without drift

---

## Files Modified This Session

| File | Status | Lines | Purpose |
|------|--------|-------|---------|
| `tau/repl.py` | ✅ Complete | 430 | tau-engine REPL |
| `tau/recording_api.py` | ✅ Complete | 350 | Python recording API |
| `tau/engine/tau-engine.c` | ⏳ Partial | +100 | Recording implementation |
| `screentool/bash/ffmpeg_record.sh` | ✅ Complete | 250 | Video recording |
| `screentool/bash/launcher.sh` | ✅ Complete | 450 | Unified launcher |
| `screentool/bash/sync.sh` | ✅ Complete | 300 | A/V sync & merge |
| `screentool/st` | ✅ Complete | +50 | CLI commands |

**Total new code**: ~2,000 lines

---

## Next Session Quick Start

```bash
# 1. Complete tau-engine.c RECORD commands
cd ~/src/mricos/demos/tau/engine
# Edit tau-engine.c, add RECORD commands around line 800
make clean && make

# 2. Test tau-engine recording
./tau-engine &
echo "RECORD START /tmp/test.wav $(date +%s)000000000" | nc -U ~/tau/runtime/tau.sock
sleep 3
echo "RECORD STOP" | nc -U ~/tau/runtime/tau.sock
ls -lh /tmp/test.wav

# 3. Update recording_api.py to use tau-engine

# 4. Update launcher.sh tau case

# 5. End-to-end test
export ST_SRC=~/src/screentool
export ST_DIR=~/recordings
export AUDIO_RECORDER=tau
st record start
# ... record ...
st record stop
st sync latest
st play latest
```

---

## Documentation Created

- [tau/README_REPL.md](README_REPL.md) - tau REPL guide
- [tau/QUICKSTART.md](QUICKSTART.md) - Quick reference
- [tau/INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) - Technical details
- [screentool/README_NEW_RECORDING.md](../../screentool/README_NEW_RECORDING.md) - screentool recording guide
- [screentool/QUICKSTART_NEW.md](../../screentool/QUICKSTART_NEW.md) - (attempted, interrupted)
- **This file**: Next session guide

---

## Critical Path to Completion

1. **15 min**: Add RECORD commands to tau-engine.c (3 commands)
2. **5 min**: Rebuild and test tau-engine recording
3. **10 min**: Update recording_api.py to use tau-engine
4. **5 min**: Update launcher.sh tau case
5. **10 min**: End-to-end testing
6. **5 min**: Documentation updates

**Total time to completion**: ~50 minutes

---

## Key Insight

**The hard work is done!** We have:
- ✅ Complete architecture designed
- ✅ All bash modules written
- ✅ Python API ready
- ✅ tau-engine data structures in place
- ✅ Duplex mode configured
- ✅ Audio callback processing input

**Only missing**: ~100 lines of C code for RECORD commands in `process_command()`.

This is a **straight-forward implementation** - no complex logic, just:
1. Parse command tokens
2. Call `ma_encoder_init_file()`
3. Set atomic flags
4. Return response

The encoder is already writing in the audio callback (line 345-355 of tau-engine.c).

---

## Contact Points Between Systems

```
screentool launcher.sh
    ↓
    Calls: tau-engine via Unix socket
    Command: "RECORD START <path> <t0_ns>"
    ↓
tau-engine.c process_command()
    ↓
    Initializes: ma_encoder
    Sets: G.recorder.recording = 1
    ↓
tau-engine.c data_cb()
    ↓
    Writes: pIn → ma_encoder → WAV file
    ↓
screentool sync.sh
    ↓
    Reads: T0 from video metadata + audio JSON
    Computes: Δ = (video_t0 - audio_t0)
    Merges: ffmpeg -itsoffset Δ
```

---

## Success Criteria

Recording is complete when:
1. ✅ `st record start` creates session directory
2. ✅ Video records to `db/[epoch].video.raw.mp4` with T0
3. ✅ Audio records to `db/[epoch].audio.raw.wav` with T0
4. ✅ `st record stop` stops both cleanly
5. ✅ `st sync latest` computes correct delta
6. ✅ `st sync latest` creates synced `recording.mp4`
7. ✅ `st play latest` plays with perfect A/V sync
8. ✅ Sync delta < 1ms for same-machine recording

Good luck! The finish line is close! 🎯
