# Screentool Integration

tau provides lifecycle-managed audio recording for screentool. tau-engine runs only while recording, with automatic startup and cleanup.

## Setup

```bash
export TAU_SRC=~/src/tau
export AUDIO_RECORDER=tau
export ST_SRC=~/src/screentool
export ST_DIR=~/recordings
```

## Usage

```bash
st record start       # Auto-starts tau-engine, begins recording
# ... recording ...
st record stop        # Stops recording, stops tau-engine

# Verify clean shutdown
pgrep tau-engine      # Should be empty
```

## What Happens

**Start** (`st record start`):
1. launcher.sh sources `tau_recording.sh`
2. `tau_start_recording()` called
3. TauRecorder checks if tau-engine running, spawns if needed
4. Waits for socket, sends `RECORD START`

**Stop** (`st record stop`):
1. `tau_cleanup_recording()` sends `RECORD STOP`
2. Sends `QUIT` to tau-engine
3. Waits for graceful shutdown, kills stragglers
4. Audio device released, no orphaned processes

## Session Output

Files go to `$ST_DIR/<epoch>/`. See [specs/av-sync.md](specs/av-sync.md) for the full session directory format and metadata schemas.

```bash
ls ~/recordings/latest/
# video.mp4  audio.wav  audio.wav.json  session.json  session.meta  t0
```

## A/V Sync

```bash
st sync latest
ffplay ~/recordings/latest/recording.mp4
```

## Troubleshooting

### tau-engine won't start

```bash
echo $TAU_SRC                        # Verify set
ls -la $TAU_SRC/engine/tau-engine    # Verify binary exists
cd $TAU_SRC/engine && ./build.sh     # Rebuild if needed
```

### Orphaned processes

```bash
pkill -KILL -f tau-engine
rm -f ~/tau/runtime/tau.sock
```

### Manual test

```bash
source $TAU_SRC/tau_lib/bash/tau_recording.sh
T0=$(python3 -c 'import time; print(int(time.monotonic_ns()))')
tau_start_recording /tmp/test.wav $T0
sleep 2
tau_cleanup_recording
ffprobe /tmp/test.wav
```

## Migration from Daemon Mode

- [ ] Set `TAU_SRC` environment variable
- [ ] Update launcher.sh to source `tau_recording.sh`
- [ ] Set `AUDIO_RECORDER=tau`
- [ ] Remove manual `tau-engine &` from scripts
- [ ] Remove manual `pkill tau-engine` from cleanup
- [ ] Test full cycle: `st record start` / `st record stop`
- [ ] Verify: `pgrep tau-engine` returns empty
