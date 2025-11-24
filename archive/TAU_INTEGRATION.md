# Tau Multitrack Audio Integration for ascii_scope_snn

## Overview

This document describes the integration between ascii_scope_snn (Python curses DAW) and tau (C audio engine) for synchronized multitrack audio playback.

## Architecture

```
ascii_scope_snn (Python/curses)
    ↓ Unix socket commands
tau_playback.py
    ↓ SOCK_DGRAM
tau daemon (C audio engine)
    ↓ CoreAudio/ALSA
Speakers
```

## Features Implemented

### In tau.c (C audio engine)

1. **SAMPLE LOOP** command
   - Enable/disable looping playback
   - Usage: `SAMPLE <n> LOOP <0|1>`
   - Essential for long audio tracks in DAW

2. **SAMPLE SEEK** command
   - Seek to position in seconds
   - Usage: `SAMPLE <n> SEEK <time>`
   - Allows scrubbing and synchronized transport

3. **Thread-safe position tracking**
   - Changed `pos` to `_Atomic uint32_t`
   - Safe seeking during playback

### In tau_playback.py (Python integration)

Complete Python API for controlling tau:

- **Track loading**: `load_track(track_id, audio_path)`
- **Playback control**: `play_track()`, `stop_track()`
- **Seeking**: `seek(track_id, time_seconds)`
- **Looping**: `set_loop(track_id, loop)`
- **Gain control**: `set_track_gain(track_id, gain)`
- **Channel routing**: `assign_track_channel(track_id, channel)`
- **Mixer controls**: `set_channel_gain()`, `set_channel_pan()`
- **Master**: `set_master_gain(gain)`
- **Bulk operations**: `play_all()`, `stop_all()`, `seek_all()`

## Track Mapping Strategy

```
ascii_scope_snn Lane → Tau Sample → Tau Channel
─────────────────────────────────────────────────
Lane 1 (audio)       → Sample 1    → Channel 0
Lane 2 (pulse1)      → Sample 2    → Channel 1
Lane 3 (pulse2)      → Sample 3    → Channel 2
Lane 4 (envelope)    → Sample 4    → Channel 3
Lane 5-8             → Sample 5-8  → Ch 0-3 (round-robin)
```

**Channels 0-3**: Mixer buses for EQ/compression/effects
**Master**: Final output gain

## Usage Example

```python
from tau_playback import TauMultitrack
from pathlib import Path

# Initialize
tau = TauMultitrack()

# Load audio to track 1
tau.load_track(1, Path("~/audio/track1.wav"))

# Configure for looping playback
tau.set_loop(1, True)
tau.set_track_gain(1, 0.8)
tau.assign_track_channel(1, 0)

# Play
tau.play_track(1)

# Seek to 5 seconds
tau.seek(1, 5.0)

# Stop
tau.stop_track(1)
```

## Integration with ascii_scope_snn Transport

To integrate with the existing DAW:

### 1. Modify `state.py`

```python
from tau_playback import TauMultitrack

class Transport:
    def __init__(self):
        self.playing = False
        self.position = 0.0
        self.tau = TauMultitrack()
        self.loaded_tracks = {}  # {lane_id: track_id}

    def toggle_play(self):
        """Space bar - play/pause."""
        self.playing = not self.playing

        if self.playing:
            # Seek all tracks to current position first
            self.tau.seek_all(self.position)
            # Then trigger playback
            self.tau.play_all()
        else:
            self.tau.stop_all()

    def seek(self, position: float):
        """Seek transport to new position."""
        self.position = position
        # Sync tau tracks
        self.tau.seek_all(position)

    def load_audio_for_lane(self, lane_id: int, audio_path: Path):
        """Load audio file for a lane."""
        track_id = lane_id
        if self.tau.load_track(track_id, audio_path):
            self.loaded_tracks[lane_id] = track_id
            # Enable looping for DAW tracks
            self.tau.set_loop(track_id, True)
            # Route to channel
            channel = (lane_id - 1) % 4
            self.tau.assign_track_channel(track_id, channel)
```

### 2. Modify `lanes.py`

```python
def set_lane_gain(self, lane_id: int, gain: float):
    """Adjust lane volume."""
    lane = self.lanes[lane_id]
    lane.gain = gain

    # Sync to tau
    if lane_id in self.state.transport.loaded_tracks:
        track_id = self.state.transport.loaded_tracks[lane_id]
        self.state.transport.tau.set_track_gain(track_id, gain)

def toggle_lane_mute(self, lane_id: int):
    """Mute/unmute lane."""
    lane = self.lanes[lane_id]
    lane.muted = not lane.muted

    # Mute in tau by setting gain to 0
    if lane_id in self.state.transport.loaded_tracks:
        track_id = self.state.transport.loaded_tracks[lane_id]
        gain = 0.0 if lane.muted else lane.gain
        self.state.transport.tau.set_track_gain(track_id, gain)
```

### 3. Add CLI Commands

```python
# In command_definitions.py

@command("load-audio")
def cmd_load_audio(app, args):
    """Load audio file to lane: load-audio <lane_id> <path>"""
    if len(args) < 2:
        return "Usage: load-audio <lane_id> <path>"

    lane_id = int(args[0])
    audio_path = Path(" ".join(args[1:]))

    app.state.transport.load_audio_for_lane(lane_id, audio_path)
    return f"Loaded {audio_path.name} to lane {lane_id}"

@command("seek")
def cmd_seek(app, args):
    """Seek to time: seek <seconds>"""
    if not args:
        return "Usage: seek <seconds>"

    time = float(args[0])
    app.state.transport.seek(time)
    return f"Seeked to {time:.2f}s"
```

## Protocol Reference

### Tau Socket Commands

```
SAMPLE <n> LOAD <path>         Load audio file
SAMPLE <n> TRIG                Start playback
SAMPLE <n> STOP                Stop playback
SAMPLE <n> LOOP <0|1>          Set looping
SAMPLE <n> SEEK <time>         Seek to position (seconds)
SAMPLE <n> GAIN <gain>         Set gain (0.0-10.0)
SAMPLE <n> CHAN <ch>           Assign to channel (0-3)

CH <n> GAIN <gain>             Set channel gain (1-4)
CH <n> PAN <pan>               Set channel pan (-1.0 to 1.0)

MASTER <gain>                  Set master gain

STATUS                         Check if running
```

### Response Format

```
OK <command> [details]         Success
ERROR <message>                Failure
```

## Testing

Test the integration:

```bash
# Start tau daemon
tau start

# Test Python module
cd ~/src/mricos/demos/tscale/ascii_scope_snn
python3 tau_playback.py

# Should output:
# ✓ Connected to tau
# ✓ Loaded: ~/src/mricos/demos/tscale/audio.wav
# ▶ Playing track 1...
# ⏩ Seeking to 5.0 seconds...
# ⏹ Stopping...
# Done!
```

## Files Modified/Created

### New Files
- `/Users/mricos/src/mricos/demos/tscale/ascii_scope_snn/tau_playback.py` - Python integration module

### Modified Files
- `/Users/mricos/src/mricos/demos/tau/tau.c` - Added LOOP and SEEK commands

### Changes to tau.c

1. Added `_Atomic int loop` to `SampleSlot` struct
2. Changed `uint32_t pos` to `_Atomic uint32_t pos`
3. Modified `slot_tick()` to handle looping
4. Added `SAMPLE LOOP` command handler
5. Added `SAMPLE SEEK` command handler

## Performance Considerations

### Audio Thread Safety
- All sample state uses atomic operations
- Seeking is non-blocking and glitch-free
- Looping has no audio gap

### Latency
- Unix sockets: ~100µs round-trip
- Seeking: Instant (atomic store)
- Command processing: Non-realtime thread

### Memory
- Samples loaded entirely into RAM
- No streaming (yet)
- Good for tracks <5 minutes at 48kHz

## Future Enhancements

1. **Streaming playback** - For very long files
2. **Position callbacks** - Tau sends position updates to UI
3. **Waveform caching** - Store peak data for fast rendering
4. **Time stretching** - Sync to DAW tempo
5. **Crossfading** - Between loop points
6. **Effects chain** - Per-track EQ/compression/reverb

## Troubleshooting

### "Tau socket not found"
```bash
tau start
```

### "Connection refused"
```bash
# Clean stale socket and restart
rm ~/tau/runtime/tau.sock
tau start
```

### "Failed to load audio"
- Check file exists and path is absolute
- Check file format supported (wav, mp3, flac, ogg)
- Check permissions

### No audio output
```bash
# Check tau status
tau status

# Test with simple tone
tau test

# Check system audio output
```

## References

- Tau documentation: `~/src/devops/tetra/bash/tau/README.md`
- Tau C source: `~/src/mricos/demos/tau/tau.c`
- ascii_scope_snn docs: `~/src/mricos/demos/tscale/ascii_scope_snn/README.md`
