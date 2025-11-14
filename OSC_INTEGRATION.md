# TAU OSC Integration

## Overview

tau now supports **dual control protocols**:
1. **Unix Datagram Socket** - Local control via `tau-send` (line-based protocol)
2. **OSC Multicast** - Network control via MIDI-1983 integration (239.1.1.1:1983)

Both protocols control the same audio engine in real-time with thread-safe atomic operations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   TAU Audio Engine                      │
│                                                          │
│  ┌────────────────┐         ┌──────────────────┐       │
│  │ Datagram Socket│         │   OSC Multicast  │       │
│  │ (tau.sock)     │         │ (239.1.1.1:1983) │       │
│  └────────┬───────┘         └──────┬───────────┘       │
│           │                        │                    │
│           └────────┬───────────────┘                    │
│                    ▼                                     │
│         ┌──────────────────────┐                        │
│         │  Atomic Parameters   │                        │
│         │  (Thread-Safe)       │                        │
│         └──────────┬───────────┘                        │
│                    ▼                                     │
│         ┌──────────────────────┐                        │
│         │   Audio Callback     │                        │
│         │   (miniaudio)        │                        │
│         └──────────────────────┘                        │
└─────────────────────────────────────────────────────────┘
```

---

## OSC Protocol

### Multicast Address
- **IP**: 239.1.1.1
- **Port**: 1983
- **Type**: UDP Multicast

### Message Formats

#### 1. Mapped/Semantic Controls
**Path**: `/midi/mapped/{variant}/{semantic_name}`
**Type**: `f` (float, normalized 0.0-1.0)

Example:
```
/midi/mapped/a/VOLUME_1     0.8    # Channel 1 gain = 0.8
/midi/mapped/a/MASTER_VOLUME 0.5   # Master gain = 0.5
/midi/mapped/a/FILTER_CUTOFF 0.3   # Filter cutoff scaled
```

#### 2. Raw MIDI CC
**Path**: `/midi/raw/cc/{channel}/{controller}`
**Type**: `i` (integer, 0-127)

Example:
```
/midi/raw/cc/1/7    127    # CC7 (volume) channel 1 = 127
/midi/raw/cc/1/10   64     # CC10 (pan) channel 1 = center
```

#### 3. Raw MIDI Notes
**Path**: `/midi/raw/note/{channel}/{note}`
**Type**: `i` (integer, velocity 0-127, 0=off)

Example:
```
/midi/raw/note/1/36   100  # Note 36 (C2) ON, vel=100 → Trigger Sample 1
/midi/raw/note/1/38   90   # Note 38 (D2) ON, vel=90 → Trigger Sample 2
/midi/raw/note/1/36   0    # Note 36 OFF
```

---

## Current Semantic Mappings

These are the default mappings implemented in `tau.c:osc_handle_mapped()`:

| Semantic Name    | tau Parameter          | Scale           | Notes                    |
|------------------|------------------------|-----------------|--------------------------|
| VOLUME_1         | Channel 0 gain         | 0.0-1.0         | Direct mapping           |
| VOLUME_2         | Channel 1 gain         | 0.0-1.0         | Direct mapping           |
| VOLUME_3         | Channel 2 gain         | 0.0-1.0         | Direct mapping           |
| VOLUME_4         | Channel 3 gain         | 0.0-1.0         | Direct mapping           |
| PAN_1            | Channel 0 pan          | 0.0-1.0 → -1-1  | Center = 0.5             |
| PAN_2            | Channel 1 pan          | 0.0-1.0 → -1-1  | Center = 0.5             |
| FILTER_CUTOFF    | Channel 0 filter freq  | 100-8000 Hz     | Scaled logarithmically   |
| MASTER_VOLUME    | Master gain            | 0.0-1.0         | Global output level      |

### Example MIDI Note Mappings

| MIDI Note | Note Name | Action            |
|-----------|-----------|-------------------|
| 36        | C2        | Trigger Sample 1  |
| 38        | D2        | Trigger Sample 2  |

---

## Testing OSC Integration

### 1. Start tau
```bash
./tau
```

Expected output:
```
Starting OSC listener on 239.1.1.1:1983
Datagram server ready: /Users/mricos/tau/runtime/tau.sock
OSC server ready: listening for MIDI events
tau running: sr=48000 frames=512 socket=/Users/mricos/tau/runtime/tau.sock
```

### 2. Send OSC Messages

Using `osc_send_raw.sh` from MIDI-1983:
```bash
# Test master volume
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/MASTER_VOLUME 0.5

# Test channel volume
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/VOLUME_1 0.8

# Test filter cutoff
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/FILTER_CUTOFF 0.7

# Test raw CC
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/raw/cc/1/7 100

# Test note trigger
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/raw/note/1/36 100
```

Using `oscsend` directly:
```bash
# Semantic control
oscsend 239.1.1.1 1983 /midi/mapped/a/MASTER_VOLUME f 0.5

# Raw CC
oscsend 239.1.1.1 1983 /midi/raw/cc/1/7 i 127

# Note trigger
oscsend 239.1.1.1 1983 /midi/raw/note/1/36 i 100
```

### 3. Monitor OSC Activity

tau prints received OSC messages to stderr:
```
[OSC] MASTER_VOLUME = 0.500
[OSC] VOLUME_1 = 0.800
[OSC] FILTER_CUTOFF = 0.300
[OSC] Raw CC 1/7 = 100 (master gain)
[OSC] Note 36 ON -> Sample 1 TRIG
```

---

## Integration with MIDI-1983

### Full MIDI Control Flow

```
MIDI Hardware
   ↓
midi-1983 service (TMC)
   ↓ (hardware map)
Syntax Names (p1, p2, etc.)
   ↓ (semantic map)
Semantic Names (VOLUME_1, FILTER_CUTOFF, etc.)
   ↓ (OSC multicast 239.1.1.1:1983)
tau OSC listener
   ↓
Audio Engine Parameters
```

### Example: MIDI Fader → tau Volume

1. Move MIDI fader (physical CC7)
2. MIDI-1983 receives: `CC ch1 cc7 value=100`
3. Hardware map translates: `p1 = 0.787` (100/127)
4. Semantic map translates: `VOLUME_1 = 0.787`
5. OSC broadcast: `/midi/mapped/a/VOLUME_1 0.787`
6. tau receives and sets: `channel[0].gain = 0.787`
7. Audio output level changes in real-time

---

## Customizing Semantic Mappings

To add or modify OSC control mappings, edit `tau.c:osc_handle_mapped()`:

```c
// Add new semantic mapping
else if (strcmp(semantic, "YOUR_SEMANTIC_NAME") == 0){
    // Scale value if needed
    float scaled = value * some_range + offset;

    // Update tau parameter (use atomic_store for thread safety)
    atomic_store(&G.your_parameter, scaled);

    fprintf(stderr, "[OSC] YOUR_SEMANTIC_NAME = %.3f\n", value);
}
```

Example: Adding reverb mix control:
```c
else if (strcmp(semantic, "REVERB_MIX") == 0){
    atomic_store(&G.reverb_mix, value);
    fprintf(stderr, "[OSC] REVERB_MIX = %.3f\n", value);
}
```

Then rebuild:
```bash
./build.sh
```

---

## Raw CC Custom Mapping

Edit `tau.c:osc_handle_raw_cc()` to map specific MIDI CC numbers:

```c
// Example: CC10 (pan) on channel 1
if (channel == 1 && controller == 10){
    float pan = (normalized * 2.0f) - 1.0f;  // 0-1 → -1 to 1
    atomic_store(&G.ch[0].pan, pan);
    fprintf(stderr, "[OSC] Raw CC %d/%d = %d (pan)\n", channel, controller, value);
}
```

---

## Note Trigger Custom Mapping

Edit `tau.c:osc_handle_raw_note()` to map notes to samples or synth triggers:

```c
// Example: C#2 (note 37) triggers sample 3
else if (note == 37 && G.slots[2].loaded){
    atomic_store(&G.slots[2].playing, 1);
    G.slots[2].pos = 0;
    fprintf(stderr, "[OSC] Note %d ON -> Sample 3 TRIG\n", note);
}
```

---

## Performance Notes

- **OSC Thread**: Runs independently via `lo_server_thread`
- **No Blocking**: OSC handlers use atomic operations (lock-free)
- **Low Latency**: OSC → parameter update ~1-2ms
- **Thread Safety**: All parameter updates use `atomic_store()`
- **Multicast**: One MIDI-1983 broadcast → many tau instances can listen

---

## Debugging OSC

### Check OSC Multicast Traffic

Using `oscdump`:
```bash
oscdump 1983
```

You should see all OSC messages on port 1983, including those from MIDI-1983.

### Test OSC Listener Without MIDI

Send test messages with `oscsend`:
```bash
oscsend 239.1.1.1 1983 /midi/mapped/a/VOLUME_1 f 0.5
```

Check tau stderr for:
```
[OSC] VOLUME_1 = 0.500
```

### Enable OSC Debug in tau

Add to `tau.c:osc_error()`:
```c
fprintf(stderr, "OSC Error %d in path %s: %s\n", num, path, msg);
fprintf(stderr, "  Debug: Check message format and types\n");
```

---

## Comparison: Datagram vs OSC

| Feature              | Unix Datagram (tau.sock) | OSC Multicast (239.1.1.1:1983) |
|----------------------|--------------------------|--------------------------------|
| **Local Control**    | ✅ Direct                | ❌ Network only                |
| **MIDI Integration** | ❌ Manual bridge needed  | ✅ Direct via MIDI-1983        |
| **Multi-Client**     | ✅ Via pub/sub           | ✅ Via multicast               |
| **Latency**          | ~0.5ms                   | ~1-2ms                         |
| **Protocol**         | Line-based text          | OSC binary                     |
| **Tools**            | `tau-send`               | `oscsend`, MIDI controllers    |
| **Use Case**         | Scripting, REPL          | Live performance, MIDI         |

---

## Future Enhancements

### Phase 2A Additions
- [ ] Bidirectional OSC (tau → MIDI feedback)
- [ ] OSC pattern matching (e.g., `/tau/voice/*/freq`)
- [ ] OSC bundle support (atomic multi-param updates)
- [ ] Per-voice frequency control via OSC
- [ ] ADSR envelope control via OSC

### Phase 3 Additions
- [ ] OSC-based session save/recall
- [ ] OSC learn mode (auto-map MIDI to parameters)
- [ ] OSC transport control (play/stop/record)

---

## Summary

tau's OSC integration provides:
- ✅ Real-time MIDI control via MIDI-1983 semantic mapping
- ✅ Dual protocol support (local + network)
- ✅ Thread-safe parameter updates
- ✅ Low-latency multicast (<2ms)
- ✅ Extensible semantic mappings
- ✅ Raw MIDI CC/note access
- ✅ No port conflicts (multicast)

**Ready for live performance with MIDI hardware!** 🎵

---

*Last updated: 2025-11-13*
*tau version: Phase 1 + OSC*
