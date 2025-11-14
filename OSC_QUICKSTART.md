# TAU OSC Quick Start

## 5-Minute Guide to MIDI Control

### What You Get
- MIDI hardware → tau audio parameters in real-time
- No manual mapping files needed (semantic layer handles it)
- Works with MIDI-1983's OSC multicast
- Hardware-agnostic (swap MIDI controllers without changing tau)

---

## Quick Test (Without MIDI Hardware)

### 1. Start tau
```bash
cd ~/src/mricos/demos/tau
./tau
```

### 2. Start a sound
```bash
./tau-send "VOICE 1 FREQ 440"
./tau-send "VOICE 1 GAIN 0.3"
./tau-send "VOICE 1 ON"
```

You should hear a 440Hz sine wave.

### 3. Control it via OSC
```bash
# Louder
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/MASTER_VOLUME 0.8

# Quieter
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/MASTER_VOLUME 0.3

# Channel 1 volume
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/VOLUME_1 0.5

# Filter cutoff (if enabled)
~/src/devops/tetra/bash/midi/osc_send_raw.sh /midi/mapped/a/FILTER_CUTOFF 0.7
```

---

## With MIDI Hardware (Full Flow)

### Prerequisites
1. MIDI-1983 service running
2. Your MIDI controller configured in MIDI-1983
3. Semantic map defining parameter names

### Start the Stack
```bash
# 1. Start MIDI-1983 (if not running)
cd ~/src/devops/tetra/bash/midi
./midi-service.sh start

# 2. Start tau
cd ~/src/mricos/demos/tau
./tau
```

### Configure Semantic Mapping in MIDI-1983

Edit your semantic map to include tau parameters:
```bash
# Example semantic map entry
p1 → VOLUME_1      # Fader 1 controls channel 1 volume
p2 → VOLUME_2      # Fader 2 controls channel 2 volume
p3 → FILTER_CUTOFF # Knob 1 controls filter cutoff
p4 → MASTER_VOLUME # Master fader
```

### Test the Flow

1. Move MIDI fader 1
2. MIDI-1983 broadcasts: `/midi/mapped/a/VOLUME_1 0.75`
3. tau receives and updates channel 1 gain
4. Audio level changes in real-time

---

## Current Semantic Names Supported

| Name              | Controls              | Range       |
|-------------------|-----------------------|-------------|
| VOLUME_1          | Channel 1 gain        | 0.0 - 1.0   |
| VOLUME_2          | Channel 2 gain        | 0.0 - 1.0   |
| VOLUME_3          | Channel 3 gain        | 0.0 - 1.0   |
| VOLUME_4          | Channel 4 gain        | 0.0 - 1.0   |
| PAN_1             | Channel 1 pan         | -1.0 - 1.0  |
| PAN_2             | Channel 2 pan         | -1.0 - 1.0  |
| FILTER_CUTOFF     | Channel 1 filter freq | 100-8000 Hz |
| MASTER_VOLUME     | Master output         | 0.0 - 1.0   |

---

## Adding New Semantic Controls

Edit `tau.c:osc_handle_mapped()` and rebuild:

```c
else if (strcmp(semantic, "REVERB_MIX") == 0){
    atomic_store(&G.reverb_mix, value);
    fprintf(stderr, "[OSC] REVERB_MIX = %.3f\n", value);
}
```

Then:
```bash
./build.sh
```

---

## Monitoring OSC Traffic

### See all MIDI OSC messages
```bash
oscdump 1983
```

### See tau's received messages
Check tau's stderr output for lines like:
```
[OSC] VOLUME_1 = 0.787
[OSC] MASTER_VOLUME = 0.500
```

---

## Troubleshooting

### No sound when moving MIDI faders

1. **Check MIDI-1983 is running**:
   ```bash
   ps aux | grep midi
   ```

2. **Check OSC traffic**:
   ```bash
   oscdump 1983
   ```
   Move a MIDI control. You should see OSC messages.

3. **Check tau is listening**:
   tau stderr should show:
   ```
   OSC server ready: listening for MIDI events
   ```

4. **Check semantic names match**:
   MIDI-1983 semantic name must match tau's `osc_handle_mapped()` cases.

### tau not receiving OSC

- **Firewall**: Check multicast isn't blocked (239.1.1.1:1983)
- **liblo**: Ensure installed (`brew install liblo`)
- **Rebuild**: After adding liblo: `./build.sh`

---

## What's Next?

See `OSC_INTEGRATION.md` for:
- Complete protocol reference
- Custom mapping examples
- Raw MIDI CC/note handling
- Performance tuning

---

## Summary

**You now have**:
- ✅ MIDI hardware controlling tau in real-time
- ✅ Hardware-agnostic semantic mapping
- ✅ Sub-2ms latency
- ✅ No config files to manage
- ✅ Multicast = multiple tau instances from one MIDI controller

**Enjoy!** 🎵
