# TAU - Full Architecture Design

## Overview

**tau** is a comprehensive audio system for synthesis, sampling, playback, and recording, designed following the Tetra module pattern. It provides a REPL interface, socket-based pub/sub architecture, and integration with MIDI and OSC control systems.

## Design Principles

1. **Tetra-compliant module**: Follows conventions from `~/src/devops/tetra/bash/midi`
2. **Strong globals**: `TAU_SRC` must be set for anything to work
3. **No dot files**: Configuration in named directories, no hidden files
4. **Bash 5.2+**: Always runs in bash 5.2, starts with `source ~/tetra/tetra.sh` (if using tetra)
5. **Socket-based**: Unix domain sockets for IPC, OSC for realtime control
6. **Service-managed**: Runs as TSM (Tetra Service Manager) service when integrated

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                        TAU ARCHITECTURE                          │
└──────────────────────────────────────────────────────────────────┘

                    ┌─────────────────┐
                    │   User / CLI    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   tau REPL      │  Interactive shell
                    │   (repl.sh)     │  Command processor
                    └────────┬────────┘
                             │ Unix Socket
                             ▼
          ┌──────────────────────────────────────┐
          │   Socket Server (socket_server.sh)   │
          │                                       │
          │  ┌────────────────────────────────┐  │
          │  │  Command Router                │  │
          │  │  - session management          │  │
          │  │  - state tracking              │  │
          │  │  - subscriber management       │  │
          │  └────────┬───────────────────────┘  │
          │           │                           │
          │  ┌────────▼───────────────────────┐  │
          │  │  Engine Controller              │  │
          │  │  - OSC message builder          │  │
          │  │  - voice/sample/channel mgmt    │  │
          │  │  - transport control            │  │
          │  └────────┬───────────────────────┘  │
          │           │                           │
          └───────────┼───────────────────────────┘
                      │ OSC (UDP 9001)
                      ▼
          ┌────────────────────────────┐
          │   Audio Engine (engine.c)   │
          │                             │
          │  ┌──────────────────────┐  │
          │  │  OSC Receiver        │  │  UDP port 9001
          │  └──────┬───────────────┘  │
          │         │                   │
          │  ┌──────▼───────────────┐  │
          │  │  Control Engine      │  │
          │  │  - master gain       │  │
          │  │  - process messages  │  │
          │  └──────────────────────┘  │
          │                             │
          │  ┌──────────────────────┐  │
          │  │  4 Mixer Channels    │  │
          │  │  - gain, pan         │  │
          │  │  - SVF filter (LP/HP/BP)│
          │  └──────┬───────────────┘  │
          │         │                   │
          │  ┌──────▼───────────────┐  │
          │  │  16 Sample Slots     │  │
          │  │  - .wav loader       │  │
          │  │  - one-shot playback │  │
          │  │  - gain, channel     │  │
          │  └──────┬───────────────┘  │
          │         │                   │
          │  ┌──────▼───────────────┐  │
          │  │  8 Synth Voices      │  │
          │  │  - sine/pulse wave   │  │
          │  │  - LIF modulation    │  │
          │  │  - freq, gain        │  │
          │  └──────┬───────────────┘  │
          │         │                   │
          │  ┌──────▼───────────────┐  │
          │  │  Mixer/Summing       │  │
          │  │  - channel routing   │  │
          │  │  - stereo output     │  │
          │  └──────┬───────────────┘  │
          │         │                   │
          │  ┌──────▼───────────────┐  │
          │  │  miniaudio Backend   │  │
          │  │  - CoreAudio (macOS) │  │
          │  │  - ALSA (Linux)      │  │
          │  └──────┬───────────────┘  │
          └─────────┼───────────────────┘
                    │
                    ▼
          ┌────────────────────┐
          │  Audio Hardware    │
          │  (speakers/phones) │
          └────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│                    EXTERNAL INTEGRATIONS                         │
└──────────────────────────────────────────────────────────────────┘

    ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
    │ MIDI Device  │        │ OSC Client   │        │  DAW/Other   │
    │ (via TMC)    │        │ (TouchOSC)   │        │   Software   │
    └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
           │                       │                        │
           ▼                       ▼                        ▼
    ┌──────────────────────────────────────────────────────────┐
    │         tau Socket Server (pub/sub bridge)              │
    │                                                          │
    │  Subscribers:                                            │
    │  - MIDI mapper (semantic → synth params)                │
    │  - OSC forwarder (external control)                     │
    │  - Event logger                                          │
    │  - Visualizer / Analyzer                                 │
    └──────────────────────────────────────────────────────────┘

```

---

## Directory Structure

```
$TAU_SRC/                           # ~/src/mricos/demos/tau
├── tau.sh                          # Main entry point / module loader
├── engine.c                        # C audio engine source
├── engine                          # Compiled binary
├── build.sh                        # Build script
├── miniaudio.h                     # Audio backend library
├── jsmn.h / jsmn.c                 # JSON parser
│
├── core/                           # Core bash services
│   ├── socket_server.sh            # Main service (TSM-managed)
│   ├── repl.sh                     # Interactive REPL
│   ├── engine_controller.sh        # OSC message builder
│   ├── state.sh                    # State tracking/caching
│   ├── session.sh                  # Session management
│   └── subscriber.sh               # Pub/sub management
│
├── config/                         # Configuration templates
│   ├── default_engine.json         # Default engine config
│   ├── session_template.json       # Session template
│   └── voice_presets.txt           # Synth voice presets
│
├── services/                       # Example subscriber services
│   ├── midi_mapper.sh              # MIDI → tau mapping
│   ├── event_logger.sh             # Event logging
│   └── transport_sync.sh           # Transport control
│
└── README.md                       # Documentation

$TAU_DIR/                           # ~/tau (runtime data)
├── sessions/                       # Saved sessions
│   └── my-session/
│       ├── engine.json             # Engine configuration
│       ├── voices.txt              # Voice states
│       ├── samples.txt             # Sample mappings
│       └── channels.txt            # Channel settings
│
├── samples/                        # Sample library
│   ├── drums/
│   ├── synth/
│   └── fx/
│
├── logs/                           # Service logs
│   ├── engine.log
│   ├── socket_server.log
│   └── events.log
│
├── repl/                           # REPL runtime
│   └── history.repl                # Command history
│
└── subscribers/                    # Active subscribers
    └── subscribers.txt             # Socket paths
```

---

## Component Details

### 1. Audio Engine (engine.c)

**Purpose**: Realtime audio synthesis, sample playback, mixing

**Features**:
- **4 Mixer Channels**: Independent gain, pan, SVF filters (LP/HP/BP)
- **16 Sample Slots**: Runtime .wav loading, one-shot playback, per-sample routing
- **8 Synth Voices**: Sine/pulse waveforms, LIF modulation, ADSR envelopes
- **OSC Control**: UDP server on port 9001
- **JSON Config**: Load engine parameters from JSON file

**OSC API** (current):
```
/master/gain f <gain>                      # Master output level

/ch/<1-4>/gain f <gain>                    # Channel gain
/ch/<1-4>/pan f <pan>                      # Pan (-1.0 to 1.0)
/ch/<1-4>/filter i <type> f <cutoff> f <q> # 0=off, 1=LP, 2=HP, 3=BP

/synth/<1-8>/on i <0|1>                    # Voice on/off
/synth/<1-8>/wave i <0|1>                  # 0=sine, 1=pulse
/synth/<1-8>/freq f <hz>                   # Frequency
/synth/<1-8>/gain f <gain>                 # Voice amplitude
/synth/<1-8>/chan i <0-3>                  # Route to channel
/synth/<1-8>/tau f <tau_a> f <tau_b>       # LIF time constants
/synth/<1-8>/duty f <duty>                 # Pulse duty cycle
/synth/<1-8>/spike                         # Inject LIF spike

/sample/<1-16>/load s <path>               # Load .wav file
/sample/<1-16>/trig                        # Trigger playback
/sample/<1-16>/stop                        # Stop playback
/sample/<1-16>/gain f <gain>               # Sample volume
/sample/<1-16>/chan i <0-3>                # Route to channel
```

**Build**:
```bash
clang -std=c11 -O2 engine.c jsmn.c -lpthread \
  -framework AudioToolbox -framework AudioUnit \
  -framework CoreAudio -framework CoreFoundation \
  -o engine
```

---

### 2. Socket Server (core/socket_server.sh)

**Purpose**: Unix socket service for command routing and pub/sub

**Responsibilities**:
- Accept commands from REPL or external clients
- Route commands to engine controller
- Manage subscriber list
- Broadcast events to subscribers
- State persistence

**Socket Protocol** (commands TO server):
```
START                              # Start audio engine
STOP                               # Stop audio engine
STATUS                             # Get status
HEALTH                             # Health check

# Engine control
MASTER <gain>                      # Set master gain
CHANNEL <ch> GAIN <val>            # Set channel gain
CHANNEL <ch> PAN <val>             # Set channel pan
CHANNEL <ch> FILTER <type> <cutoff> <q>

# Voice control
VOICE <n> ON|OFF                   # Turn voice on/off
VOICE <n> WAVE <sine|pulse>        # Set waveform
VOICE <n> FREQ <hz>                # Set frequency
VOICE <n> GAIN <val>               # Set gain
VOICE <n> CHAN <ch>                # Route to channel
VOICE <n> SPIKE                    # Inject spike

# Sample control
SAMPLE <n> LOAD <path>             # Load sample
SAMPLE <n> TRIG                    # Trigger playback
SAMPLE <n> STOP                    # Stop playback
SAMPLE <n> GAIN <val>              # Set gain
SAMPLE <n> CHAN <ch>               # Route to channel

# Session management
SAVE <session-name>                # Save current state
LOAD <session-name>                # Load session
LIST_SESSIONS                      # List saved sessions

# Pub/sub
SUBSCRIBE <socket-path>            # Add subscriber
UNSUBSCRIBE <socket-path>          # Remove subscriber
```

**Events FROM server** (broadcasts):
```
EVENT VOICE <n> <state>            # Voice state change
EVENT SAMPLE <n> <state>           # Sample state
EVENT MASTER <gain>                # Master gain change
EVENT ENGINE <status>              # Engine status
```

**Implementation**:
- TSM-managed service (when using tetra)
- Non-blocking event broadcasts
- Auto-cleanup of dead subscribers
- State caching for quick status queries

---

### 3. REPL (core/repl.sh)

**Purpose**: Interactive command-line interface

**Features**:
- Command history (readline)
- Tab completion
- Context-aware help
- Real-time status display
- Color-coded output (using TDS if available)

**Commands**:
```
/start                             # Start tau service
/stop                              # Stop tau service
/status                            # Show status

# Engine control
/master <gain>                     # Set master gain
/ch <n> gain <val>                 # Channel gain
/ch <n> pan <val>                  # Channel pan
/ch <n> filter <type> <cutoff> <q> # Channel filter

# Voice control
/voice <n> on|off                  # Voice on/off
/voice <n> <wave> <freq> <gain>    # Quick voice setup
/voice <n> chan <ch>               # Route voice
/voice <n> spike                   # Inject spike

# Sample control
/sample <n> load <path>            # Load sample
/sample <n> trig                   # Trigger
/sample <n> stop                   # Stop

# Session management
/save [name]                       # Save session
/load [name]                       # Load session
/list                              # List sessions

# Monitoring
/monitor                           # Start event monitor
/log                               # View logs

# Presets
/preset <name>                     # Load preset
/preset save <name>                # Save preset

# Help
/help [topic]                      # Show help
```

**Usage**:
```bash
# Start REPL
tau repl

# Inside REPL
tau ready > /start
✓ Engine started (PID: 12345)

tau ready > /voice 1 sine 440 0.3
✓ Voice 1: sine 440Hz gain=0.3

tau ready > /voice 1 on
✓ Voice 1 on

tau ready > /save my-session
✓ Saved session: my-session
```

---

### 4. Engine Controller (core/engine_controller.sh)

**Purpose**: Translate bash commands to OSC messages

**Functions**:
```bash
tau_osc_send <osc-path> <type> <args...>   # Send OSC message
tau_engine_start                            # Start engine process
tau_engine_stop                             # Stop engine process
tau_engine_status                           # Check engine status

tau_master_gain <val>                       # Master gain
tau_channel_gain <ch> <val>                 # Channel gain
tau_channel_pan <ch> <val>                  # Channel pan
tau_channel_filter <ch> <type> <cutoff> <q> # Channel filter

tau_voice_on <n>                            # Voice on
tau_voice_off <n>                           # Voice off
tau_voice_wave <n> <sine|pulse>             # Set waveform
tau_voice_freq <n> <hz>                     # Set frequency
tau_voice_gain <n> <val>                    # Set gain
tau_voice_chan <n> <ch>                     # Route to channel
tau_voice_spike <n>                         # Inject spike

tau_sample_load <n> <path>                  # Load sample
tau_sample_trig <n>                         # Trigger sample
tau_sample_stop <n>                         # Stop sample
tau_sample_gain <n> <val>                   # Sample gain
tau_sample_chan <n> <ch>                    # Sample routing
```

**Dependencies**:
- `oscsend` utility (from liblo)
- Running engine process

---

### 5. State Manager (core/state.sh)

**Purpose**: Track and cache engine state

**State Variables**:
```bash
TAU_ENGINE_PID                     # Engine process ID
TAU_ENGINE_STATUS                  # running|stopped|error
TAU_MASTER_GAIN                    # Current master gain

declare -A TAU_CHANNELS            # Channel states
declare -A TAU_VOICES              # Voice states
declare -A TAU_SAMPLES             # Sample states
```

**Functions**:
```bash
tau_state_init                     # Initialize state
tau_state_save                     # Save to session
tau_state_load                     # Load from session
tau_state_snapshot                 # Get current state
tau_state_diff                     # Compare states
```

---

### 6. Session Manager (core/session.sh)

**Purpose**: Save/load complete audio setups

**Session Format** (JSON):
```json
{
  "name": "my-session",
  "created": "2025-11-11T19:30:00Z",
  "engine": {
    "master_gain": 0.8,
    "sample_rate": 48000
  },
  "channels": [
    {
      "id": 1,
      "gain": 1.0,
      "pan": -0.5,
      "filter": {"type": "LP", "cutoff": 800, "q": 1.0}
    }
  ],
  "voices": [
    {
      "id": 1,
      "on": true,
      "wave": "sine",
      "freq": 440,
      "gain": 0.3,
      "channel": 1
    }
  ],
  "samples": [
    {
      "id": 1,
      "path": "/path/to/kick.wav",
      "gain": 0.5,
      "channel": 4
    }
  ]
}
```

**Functions**:
```bash
tau_session_save <name>            # Save current state
tau_session_load <name>            # Load and apply session
tau_session_list                   # List sessions
tau_session_delete <name>          # Delete session
tau_session_export <name> <path>   # Export to file
tau_session_import <path>          # Import session
```

---

## Integration Points

### MIDI Integration (via TMC)

**Subscriber Service**: `services/midi_mapper.sh`

Maps MIDI CC/NOTE events to tau parameters:

```bash
# Example mapping
CC 1 7 → /voice/1/freq (MIDI 0-127 → Hz 100-1000)
CC 1 10 → /ch/1/pan (MIDI 0-127 → -1.0 to 1.0)
NOTE 1 60 → /sample/1/trig (C4 triggers kick)
```

**Setup**:
```bash
# Subscribe tau to TMC
echo "SUBSCRIBE $TAU_SOCKET" | nc -U $TMC_SOCKET

# In midi_mapper.sh
while read midi_event; do
    case "$midi_event" in
        *"VOLUME"*)
            # Map to master gain
            tau_master_gain "$value"
            ;;
        *"p1"*)
            # Map to voice 1 frequency
            tau_voice_freq 1 "$freq"
            ;;
    esac
done
```

### External OSC Control

**Direct OSC** (bypass socket server):
```bash
oscsend localhost 9001 /synth/1/freq f 440.0
```

**Via Socket** (logged, broadcasted):
```bash
echo "VOICE 1 FREQ 440" | nc -U $TAU_SOCKET
```

### DAW Integration

- **OSC → DAW**: Forward tau events to DAW for automation recording
- **DAW → OSC**: DAW sends OSC to control tau parameters
- **Sample Export**: Export rendered audio to DAW

---

## Service Management (TSM)

When integrated with Tetra Service Manager:

```bash
# Start tau as TSM service
tsm start bash $TAU_SRC/core/socket_server.sh tau

# Check status
tsm list
tsm logs tau

# Stop
tsm stop tau
```

**Service Definition**:
```bash
SERVICE_NAME="tau"
SOCKET_PATH="$TSM_PROCESSES_DIR/sockets/tau.sock"
REQUIRES="tetra-boot"
RESTART_ON_FAIL=true
```

---

## Environment Variables

**Required**:
```bash
export TAU_SRC=~/src/mricos/demos/tau    # Source directory
export TAU_DIR=~/tau                      # Runtime directory
```

**Optional**:
```bash
export TAU_ENGINE_PORT=9001               # OSC port (default: 9001)
export TAU_SAMPLE_RATE=48000              # Sample rate (default: 48000)
export TAU_BUFFER_SIZE=512                # Buffer size (default: 512)
export TAU_LOG_LEVEL=INFO                 # DEBUG|INFO|WARN|ERROR
```

---

## Control Flow Examples

### Example 1: Start Engine and Play Chord

```bash
# Terminal 1: Start tau
tau repl

# In REPL:
/start
/voice 1 sine 261.63 0.2      # C4
/voice 2 sine 329.63 0.2      # E4
/voice 3 sine 392.00 0.2      # G4
/voice 1 on
/voice 2 on
/voice 3 on
/save c-major-chord
```

### Example 2: Trigger Samples via MIDI

```bash
# Terminal 1: Start tau
tau start

# Terminal 2: Start midi mapper service
bash $TAU_SRC/services/midi_mapper.sh

# Terminal 3: Configure MIDI mapping (in TMC REPL)
midi repl
/learn KICK b1a
/learn SNARE b1b
/learn HIHAT b1c

# Now pressing MIDI buttons triggers samples!
```

### Example 3: External OSC Control

```bash
# Start engine
./engine --config quadra.json

# Control from external OSC client (TouchOSC, Max/MSP, etc.)
# Client sends to: localhost:9001

/synth/1/freq f 440.0
/synth/1/on i 1
/master/gain f 0.5
```

---

## Data Flow

### Command Path
```
User REPL Input
    ↓
tau.sh (parse command)
    ↓
Unix Socket → socket_server.sh
    ↓
engine_controller.sh (build OSC message)
    ↓
OSC → UDP → engine.c (port 9001)
    ↓
Audio processing
    ↓
Hardware output
```

### Event Path
```
Engine state change
    ↓
socket_server.sh (detect/poll)
    ↓
Broadcast to subscribers
    ↓
    ├─→ REPL (display)
    ├─→ Logger (log to file)
    ├─→ MIDI (send LED feedback)
    └─→ External (webhooks, etc.)
```

---

## Future Extensions

### Recording Engine
- **File output**: Record to .wav/.flac
- **Live recording**: Buffer circular recording
- **Mixdown**: Render voices/samples to stems

### Advanced Synthesis
- **More waveforms**: Saw, triangle, noise
- **Modulation**: LFO, envelope followers
- **Effects**: Reverb, delay, distortion per-channel

### Sequencer
- **Pattern engine**: Step sequencer for voices/samples
- **Transport**: Play/pause/stop/record
- **MIDI clock sync**: Sync to external clock

### Analysis
- **Spectrum analyzer**: FFT visualization
- **VU meters**: Per-channel metering
- **Waveform display**: Oscilloscope mode

### Network
- **Multi-instance**: Multiple engines, synchronized
- **Remote control**: Web UI, mobile apps
- **Streaming**: Network audio streaming

---

## API Reference Summary

### Socket Commands

| Command | Args | Description |
|---------|------|-------------|
| `START` | - | Start engine |
| `STOP` | - | Stop engine |
| `STATUS` | - | Get status |
| `MASTER` | gain | Master gain |
| `VOICE n ON` | - | Turn voice on |
| `VOICE n FREQ` | hz | Set frequency |
| `SAMPLE n LOAD` | path | Load sample |
| `SAVE` | name | Save session |

### OSC Messages

| Path | Types | Description |
|------|-------|-------------|
| `/master/gain` | f | Master gain (0.0-1.0) |
| `/synth/n/freq` | f | Frequency (Hz) |
| `/synth/n/on` | i | Voice on (1) or off (0) |
| `/sample/n/trig` | - | Trigger sample |
| `/ch/n/pan` | f | Pan (-1.0 to 1.0) |

---

## Performance Characteristics

- **Latency**: ~10ms (512 samples @ 48kHz)
- **CPU Usage**: ~5-10% (8 voices + 4 samples active)
- **Memory**: ~50MB (engine + loaded samples)
- **Max polyphony**: 8 simultaneous voices
- **Sample slots**: 16 (limited by RAM)

---

## Dependencies

### C Engine
- miniaudio (bundled header)
- jsmn (bundled)
- CoreAudio (macOS) or ALSA (Linux)
- liblo (for OSC, optional - can use raw UDP)

### Bash Services
- bash 5.2+
- nc (netcat) for socket communication
- oscsend/oscdump (liblo-tools) for OSC
- jq for JSON parsing (optional)

### Optional
- Tetra framework (for TSM, TDS integration)
- TMC (for MIDI control)
- socat (advanced socket routing)

---

## Implementation Phases

### Phase 1: Core (DONE)
- ✓ C engine with OSC control
- ✓ 4 channels, 16 samples, 8 voices
- ✓ JSON configuration
- ✓ Test script

### Phase 2: Bash Services (NEXT)
- Socket server implementation
- Basic REPL
- Engine controller
- State management

### Phase 3: Session Management
- Save/load sessions
- Preset system
- Sample library management

### Phase 4: Integration
- MIDI mapper service
- TMC integration
- Event logging

### Phase 5: Extensions
- Recording engine
- Advanced synthesis
- Web UI

---

## Conclusion

The tau architecture provides a solid foundation for a modular, extensible audio system. By following the Tetra pattern and using Unix sockets + OSC, we achieve:

- **Separation of concerns**: C for realtime, bash for control
- **Composability**: Services can be mixed and matched
- **Extensibility**: Easy to add new services/integrations
- **Reliability**: Service management, state persistence
- **Interoperability**: OSC for external control, pub/sub for events

The system is designed to grow from a simple synth/sampler to a full production audio environment.
