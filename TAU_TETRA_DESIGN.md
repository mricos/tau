# TAU - Tetra-Compliant Audio System Design

## Executive Summary

**tau** is a complete audio system for synthesis, sampling, playback, and recording, designed as a proper **tetra module** with TSM (Tetra Service Manager) integration, datagram-based IPC, MIDI control mapping, and custom line-based protocol.

---

## Core Design Principles

### 1. Tetra Module Compliance

```bash
# ALWAYS set strong global
export TAU_SRC=~/src/mricos/demos/tau
export TAU_DIR=~/tau

# NO dot files - ever
# Configuration in named directories only
$TAU_DIR/config/
$TAU_DIR/sessions/
$TAU_DIR/samples/

# Bash 5.2+ required
# Source tetra on startup (if integrated)
source ~/tetra/tetra.sh
```

### 2. TSM Process Management

Following `~/src/devops/tetra/bash/tsm`:

- **tau binary**: Long-running C process managed by TSM
- **tau REPL**: Interactive shell (not TSM-managed, user-facing)
- **tau services**: Helper services (loggers, mappers) managed by TSM
- **No ports**: Communication via Unix domain sockets (datagrams)

### 3. Datagram-based IPC

Like MIDI's TMC module and pulsar game:

- Unix datagram sockets (SOCK_DGRAM)
- Line-based protocol (newline-delimited)
- Bidirectional communication
- No TCP/UDP ports needed

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      TAU ECOSYSTEM                               │
└──────────────────────────────────────────────────────────────────┘

USER LAYER
  ┌─────────────┐
  │ tau REPL    │  Interactive CLI (bash)
  │ (tau.sh)    │  - Custom line syntax
  └──────┬──────┘  - Session management
         │         - Preset control
         │ Datagram
         ▼
  ┌──────────────────────────────────────┐
  │   tau.sock (Unix DGRAM)              │
  └──────────────────────────────────────┘
         │
         ▼
TSM-MANAGED SERVICES
  ┌──────────────────────────────────────┐
  │   tau (C binary)                     │  ← TSM service
  │   PID: managed by TSM                │
  │   Socket: $TAU_DIR/runtime/tau.sock  │
  │                                       │
  │   ┌──────────────────────────────┐   │
  │   │  Protocol Parser              │   │
  │   │  - Line-based commands        │   │
  │   │  - Response formatting        │   │
  │   └──────┬───────────────────────┘   │
  │          │                            │
  │   ┌──────▼───────────────────────┐   │
  │   │  Audio Engine                 │   │
  │   │  - 4 channels (mix/pan/flt)   │   │
  │   │  - 16 sample slots            │   │
  │   │  - 8 synth voices             │   │
  │   └──────┬───────────────────────┘   │
  │          │                            │
  │   ┌──────▼───────────────────────┐   │
  │   │  miniaudio Backend            │   │
  │   │  - CoreAudio/ALSA             │   │
  │   └──────────────────────────────┘   │
  └──────────────────────────────────────┘
         │ Broadcast datagrams
         ▼
  ┌──────────────────────────────────────┐
  │   Subscriber Services (TSM)          │
  │                                       │
  │   • midi-mapper.sock                 │  ← TSM service
  │     (MIDI CC → tau params)           │
  │                                       │
  │   • tau-logger.sock                  │  ← TSM service
  │     (Event logging)                  │
  │                                       │
  │   • tau-analyzer.sock                │  ← TSM service
  │     (Spectrum/VU meters)             │
  └──────────────────────────────────────┘

MIDI INTEGRATION
  ┌──────────────────────────────────────┐
  │   midi-1983 (TMC service)            │  ← TSM service
  │   - Raw MIDI events                  │
  │   - Semantic mapping from config     │
  │   - Broadcasts to subscribers        │
  └──────┬───────────────────────────────┘
         │ Subscribe
         ▼
  ┌──────────────────────────────────────┐
  │   midi-mapper service                │
  │   Reads: tau-midi-map.txt            │
  │                                       │
  │   track.1.vol   → /ch/1/gain         │
  │   track.1.pan   → /ch/1/pan          │
  │   track.1.lpf   → /ch/1/filter LP    │
  │   track.1.hpf   → /ch/1/filter HP    │
  └──────┬───────────────────────────────┘
         │ Datagram
         ▼
  ┌──────────────────────────────────────┐
  │   tau.sock                           │
  └──────────────────────────────────────┘
```

---

## Component Details

### 1. tau Binary (C) - TSM Service

**Purpose**: Realtime audio engine with datagram control

**Build**:
```bash
cd $TAU_SRC
gcc -std=c11 -O2 tau.c jsmn.c -lpthread \
  -framework CoreAudio -framework AudioUnit \
  -framework AudioToolbox -framework CoreFoundation \
  -o tau
```

**TSM Integration**:
```bash
# Start via TSM
tsm start $TAU_SRC/tau

# TSM creates:
# - Process tracking in $TETRA_DIR/tsm/runtime/processes/
# - Log file in $TETRA_DIR/tsm/logs/tau.log
# - Socket at $TAU_DIR/runtime/tau.sock

# Check status
tsm list
tsm logs tau
```

**Socket Communication**:
```c
// tau.c pseudo-code
int sock = socket(AF_UNIX, SOCK_DGRAM, 0);
struct sockaddr_un addr = {
    .sun_family = AF_UNIX,
    .sun_path = "/Users/mricos/tau/runtime/tau.sock"
};
bind(sock, &addr, sizeof(addr));

while (running) {
    char buf[4096];
    struct sockaddr_un client_addr;
    socklen_t len = sizeof(client_addr);

    ssize_t n = recvfrom(sock, buf, sizeof(buf)-1, 0,
                         (struct sockaddr*)&client_addr, &len);

    if (n > 0) {
        buf[n] = '\0';
        process_command(buf);  // Parse line protocol

        // Send response back to client
        char response[256];
        format_response(response, sizeof(response));
        sendto(sock, response, strlen(response), 0,
               (struct sockaddr*)&client_addr, len);
    }
}
```

**Line Protocol** (commands IN to tau):
```
INIT                           # Initialize engine
MASTER <gain>                  # Set master gain (0.0-1.0)
CH <n> GAIN <val>              # Channel gain
CH <n> PAN <val>               # Channel pan (-1.0 to 1.0)
CH <n> FILTER <type> <fc> <q>  # type: 0=off 1=LP 2=HP 3=BP

VOICE <n> ON                   # Voice on
VOICE <n> OFF                  # Voice off
VOICE <n> WAVE <0|1>           # 0=sine 1=pulse
VOICE <n> FREQ <hz>            # Frequency
VOICE <n> GAIN <val>           # Voice gain
VOICE <n> CHAN <ch>            # Route to channel (0-3)
VOICE <n> SPIKE                # Inject LIF spike
VOICE <n> TAU <a> <b>          # LIF time constants

SAMPLE <n> LOAD <path>         # Load .wav file
SAMPLE <n> TRIG                # Trigger playback
SAMPLE <n> STOP                # Stop playback
SAMPLE <n> GAIN <val>          # Sample gain
SAMPLE <n> CHAN <ch>           # Route to channel

STATUS                         # Get full status
QUIT                           # Shutdown
```

**Response Protocol** (OUT from tau):
```
OK <message>                   # Success
ERROR <code> <message>         # Error
ID <n>                         # Object ID (after spawn)
STATUS <json>                  # Status response

# Event broadcasts (to subscribers)
EVENT VOICE <n> <state>        # Voice state change
EVENT SAMPLE <n> <state>       # Sample state
EVENT CHANNEL <n> <param> <val>
EVENT MASTER <gain>
```

---

### 2. tau REPL (Bash) - User Interface

**Purpose**: Interactive command shell with custom syntax

**Location**: `$TAU_SRC/tau.sh`

**Usage**:
```bash
# Start REPL
tau repl

# Direct commands
tau start
tau voice 1 on sine 440 0.3
tau save my-session
```

**Custom Line Syntax**:
```bash
# Inside REPL
tau> start                     # Start tau service via TSM
tau> voice 1 sine 440 0.3      # Configure voice (compact syntax)
tau> voice 1 on                # Turn on
tau> ch 1 gain 0.8             # Channel control
tau> sample 1 load kick.wav    # Load sample
tau> sample 1 trig             # Trigger
tau> save session-1            # Save state
tau> quit                      # Exit REPL
```

**Implementation**:
```bash
#!/usr/bin/env bash
# tau.sh - Main REPL

source ~/tetra/tetra.sh  # If using tetra

export TAU_SRC=~/src/mricos/demos/tau
export TAU_DIR=~/tau

TAU_SOCKET="$TAU_DIR/runtime/tau.sock"

# Send command to tau via datagram
tau_send() {
    local cmd="$*"
    echo "$cmd" | socat - UNIX-DATAGRAM:$TAU_SOCKET
}

# REPL command handlers
tau_cmd_voice() {
    local n=$1
    shift

    case "$1" in
        on)
            tau_send "VOICE $n ON"
            ;;
        off)
            tau_send "VOICE $n OFF"
            ;;
        sine|pulse)
            local wave=$1 freq=$2 gain=$3
            local wave_num=0
            [[ "$wave" == "pulse" ]] && wave_num=1

            tau_send "VOICE $n WAVE $wave_num"
            tau_send "VOICE $n FREQ $freq"
            tau_send "VOICE $n GAIN $gain"
            ;;
        freq)
            tau_send "VOICE $n FREQ $2"
            ;;
        gain)
            tau_send "VOICE $n GAIN $2"
            ;;
        *)
            echo "Usage: voice <n> {on|off|sine|pulse} [freq] [gain]"
            ;;
    esac
}

tau_cmd_ch() {
    local n=$1 param=$2 val=$3

    case "$param" in
        gain|pan)
            tau_send "CH $n ${param^^} $val"
            ;;
        filter)
            local type=$3 fc=$4 q=$5
            tau_send "CH $n FILTER $type $fc $q"
            ;;
    esac
}

# REPL main loop
tau_repl() {
    echo "tau REPL - Type 'help' for commands, 'quit' to exit"

    while IFS= read -r -p "tau> " line; do
        [[ -z "$line" ]] && continue

        local args=($line)
        local cmd=${args[0]}

        case "$cmd" in
            start)
                tsm start $TAU_SRC/tau
                ;;
            stop)
                tsm stop tau
                ;;
            voice)
                tau_cmd_voice "${args[@]:1}"
                ;;
            ch)
                tau_cmd_ch "${args[@]:1}"
                ;;
            sample)
                tau_cmd_sample "${args[@]:1}"
                ;;
            save)
                tau_cmd_save "${args[1]}"
                ;;
            quit)
                break
                ;;
            *)
                echo "Unknown command: $cmd"
                ;;
        esac
    done
}

# Entry point
case "$1" in
    repl)
        tau_repl
        ;;
    *)
        # Direct command
        tau_send "$@"
        ;;
esac
```

---

### 3. MIDI Mapping Service - TSM Service

**Purpose**: Bridge MIDI events to tau parameters

**Location**: `$TAU_SRC/services/midi-mapper.sh`

**Map File** (`$TAU_DIR/config/tau-midi-map.txt`):
```
# Format: midi_semantic|tau_command|scale
# MIDI semantic names come from TMC semantic mapping

# Track 1 controls
track.1.vol|CH 1 GAIN|0.0:1.0
track.1.pan|CH 1 PAN|-1.0:1.0
track.1.lpf|CH 1 FILTER 1 {val} 1.0|100:8000
track.1.hpf|CH 1 FILTER 2 {val} 1.0|20:2000

# Track 2 controls
track.2.vol|CH 2 GAIN|0.0:1.0
track.2.pan|CH 2 PAN|-1.0:1.0

# Synth voice controls
synth.1.freq|VOICE 1 FREQ|100:1000
synth.1.gain|VOICE 1 GAIN|0.0:1.0
synth.2.freq|VOICE 2 FREQ|100:1000

# Sample triggers (buttons)
trigger.kick|SAMPLE 1 TRIG|
trigger.snare|SAMPLE 2 TRIG|
trigger.hihat|SAMPLE 3 TRIG|
```

**Implementation**:
```bash
#!/usr/bin/env bash
# midi-mapper.sh - Subscribe to MIDI, control tau

source ~/tetra/tetra.sh

export TAU_SRC=~/src/mricos/demos/tau
export TAU_DIR=~/tau

MIDI_SOCKET="$TETRA_DIR/midi/runtime/midi.sock"
TAU_SOCKET="$TAU_DIR/runtime/tau.sock"
MAP_FILE="$TAU_DIR/config/tau-midi-map.txt"
MAPPER_SOCKET="$TAU_DIR/runtime/midi-mapper.sock"

# Load mapping
declare -A MIDI_MAP

load_map() {
    while IFS='|' read -r midi_key tau_cmd scale; do
        [[ "$midi_key" =~ ^# ]] && continue
        [[ -z "$midi_key" ]] && continue

        MIDI_MAP["$midi_key"]="$tau_cmd|$scale"
    done < "$MAP_FILE"
}

# Scale MIDI value (0.0-1.0 normalized) to target range
scale_value() {
    local val=$1
    local range=$2

    if [[ "$range" =~ ^([0-9.]+):([0-9.]+)$ ]]; then
        local min="${BASH_REMATCH[1]}"
        local max="${BASH_REMATCH[2]}"

        # val * (max - min) + min
        echo "$val * ($max - $min) + $min" | bc -l
    else
        echo "$val"
    fi
}

# Process MIDI event
process_midi() {
    local event="$1"

    # Parse: "SEMANTIC track.1.vol 0.75"
    if [[ "$event" =~ ^SEMANTIC[[:space:]]+([^[:space:]]+)[[:space:]]+(.+)$ ]]; then
        local key="${BASH_REMATCH[1]}"
        local value="${BASH_REMATCH[2]}"

        # Lookup mapping
        local mapping="${MIDI_MAP[$key]}"
        if [[ -n "$mapping" ]]; then
            IFS='|' read -r tau_cmd scale <<< "$mapping"

            # Scale value if needed
            if [[ -n "$scale" ]]; then
                value=$(scale_value "$value" "$scale")
            fi

            # Substitute {val} in command
            tau_cmd="${tau_cmd//\{val\}/$value}"

            # Send to tau
            echo "$tau_cmd" | socat - UNIX-DATAGRAM:$TAU_SOCKET

            echo "[midi-mapper] $key ($value) → $tau_cmd"
        fi
    fi
}

# Subscribe to MIDI service
subscribe_midi() {
    # Create our socket
    rm -f "$MAPPER_SOCKET"
    socat UNIX-RECV:$MAPPER_SOCKET - | while IFS= read -r event; do
        process_midi "$event"
    done &

    local listener_pid=$!

    # Subscribe to MIDI
    echo "SUBSCRIBE $MAPPER_SOCKET" | socat - UNIX-DATAGRAM:$MIDI_SOCKET

    wait $listener_pid
}

# Main
load_map
echo "MIDI Mapper started: ${#MIDI_MAP[@]} mappings loaded"
subscribe_midi
```

**TSM Service Definition** (`$TETRA_DIR/tsm/services-available/tau-midi-mapper.tsm`):
```bash
SERVICE_NAME="tau-midi-mapper"
SERVICE_TYPE="bash"
SERVICE_COMMAND="bash $TAU_SRC/services/midi-mapper.sh"
SERVICE_PORT="0"  # Socket-based, no port
SERVICE_DIR="$TAU_SRC"
SERVICE_DESCRIPTION="MIDI → tau parameter mapper"
```

**Usage**:
```bash
# Enable and start
tsm enable tau-midi-mapper
tsm start tau-midi-mapper

# Check status
tsm list
tsm logs tau-midi-mapper
```

---

### 4. Session Management

**Purpose**: Save/load complete audio setups

**Session File Format** (`$TAU_DIR/sessions/my-session.json`):
```json
{
  "name": "my-session",
  "created": "2025-11-11T20:00:00Z",
  "master": {
    "gain": 0.8
  },
  "channels": [
    {"id": 1, "gain": 1.0, "pan": -0.5, "filter": {"type": 1, "cutoff": 800, "q": 1.0}},
    {"id": 2, "gain": 1.0, "pan": 0.5, "filter": {"type": 0, "cutoff": 1000, "q": 0.707}},
    {"id": 3, "gain": 0.7, "pan": 0.0, "filter": {"type": 0, "cutoff": 1000, "q": 0.707}},
    {"id": 4, "gain": 1.0, "pan": 0.0, "filter": {"type": 0, "cutoff": 1000, "q": 0.707}}
  ],
  "voices": [
    {"id": 1, "on": true, "wave": 0, "freq": 440.0, "gain": 0.3, "channel": 0},
    {"id": 2, "on": false, "wave": 1, "freq": 220.0, "gain": 0.25, "channel": 1}
  ],
  "samples": [
    {"id": 1, "path": "/Users/mricos/tau/samples/kick.wav", "gain": 0.5, "channel": 3},
    {"id": 2, "path": "/Users/mricos/tau/samples/snare.wav", "gain": 0.4, "channel": 3}
  ]
}
```

**REPL Commands**:
```bash
tau> save my-session           # Save current state
tau> load my-session           # Load and apply
tau> list sessions             # List all sessions
tau> delete my-session         # Delete session
```

---

## Directory Structure

```
$TAU_SRC/                       # ~/src/mricos/demos/tau
├── tau.c                       # Main C engine
├── tau                         # Compiled binary
├── tau.sh                      # REPL entry point
├── build.sh                    # Build script
├── miniaudio.h                 # Audio library
├── jsmn.h / jsmn.c             # JSON parser
│
├── core/                       # Bash core modules
│   ├── protocol.sh             # Datagram send/recv
│   ├── session.sh              # Session save/load
│   ├── state.sh                # State tracking
│   └── commands.sh             # REPL command handlers
│
├── services/                   # TSM services
│   ├── midi-mapper.sh          # MIDI → tau mapper
│   ├── event-logger.sh         # Event logging
│   └── analyzer.sh             # Spectrum analyzer
│
├── config/                     # Configuration templates
│   ├── default-session.json
│   └── tau-midi-map.txt
│
└── README.md

$TAU_DIR/                       # ~/tau (runtime)
├── runtime/                    # TSM runtime
│   ├── tau.sock                # Main socket
│   ├── midi-mapper.sock        # Mapper socket
│   └── tau.pid                 # PID file
│
├── sessions/                   # Saved sessions
│   ├── default.json
│   ├── live-set-1.json
│   └── recording-2025-11-11.json
│
├── samples/                    # Sample library
│   ├── drums/
│   │   ├── kick.wav
│   │   ├── snare.wav
│   │   └── hihat.wav
│   ├── synth/
│   └── fx/
│
├── config/                     # User config (NO dot files!)
│   ├── tau-midi-map.txt        # MIDI mapping
│   └── preferences.txt         # User preferences
│
└── logs/                       # Logs
    ├── tau.log                 # Engine log
    ├── midi-mapper.log         # Mapper log
    └── events.log              # Event log
```

---

## Datagram Communication Details

### Why Datagrams?

1. **Simplicity**: One-shot messages, no connection state
2. **Performance**: Low overhead for control messages
3. **TSM Compatible**: Works with socket-based service classification
4. **Pulsar Pattern**: Proven in `~/src/devops/tetra/bash/game/games/pulsar`

### Socket Creation (C side - tau.c)

```c
#include <sys/socket.h>
#include <sys/un.h>

int create_dgram_socket(const char *socket_path) {
    int sock = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (sock < 0) {
        perror("socket");
        return -1;
    }

    // Remove old socket file
    unlink(socket_path);

    struct sockaddr_un addr = {0};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);

    if (bind(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(sock);
        return -1;
    }

    // Set permissions (0666 for read/write)
    chmod(socket_path, 0666);

    return sock;
}

void socket_loop(int sock) {
    char buf[4096];
    struct sockaddr_un client_addr;
    socklen_t client_len;

    while (g_running) {
        client_len = sizeof(client_addr);
        ssize_t n = recvfrom(sock, buf, sizeof(buf)-1, 0,
                            (struct sockaddr*)&client_addr, &client_len);

        if (n > 0) {
            buf[n] = '\0';

            // Process command
            char response[256];
            process_line_command(buf, response, sizeof(response));

            // Send response back
            sendto(sock, response, strlen(response), 0,
                   (struct sockaddr*)&client_addr, client_len);
        }
    }
}
```

### Socket Communication (Bash side - tau.sh)

```bash
# Using socat for datagram send/recv
tau_send() {
    local cmd="$*"
    echo "$cmd" | socat - UNIX-DATAGRAM:$TAU_SOCKET
}

# With response
tau_send_recv() {
    local cmd="$*"
    echo "$cmd" | socat - UNIX-DATAGRAM:$TAU_SOCKET,sourceport=$TAU_DIR/runtime/client-$$.sock
}

# Subscribe to events (blocking receive)
tau_subscribe() {
    local subscriber_socket="$TAU_DIR/runtime/subscriber-$$.sock"
    rm -f "$subscriber_socket"

    # Tell tau to broadcast to us
    echo "SUBSCRIBE $subscriber_socket" | socat - UNIX-DATAGRAM:$TAU_SOCKET

    # Listen for events
    socat UNIX-RECV:$subscriber_socket - | while IFS= read -r event; do
        echo "Event: $event"
    done
}
```

---

## MIDI Integration Flow

### 1. MIDI Controller → TMC → Semantic Names

User moves MIDI controller:

```
Hardware: CC ch1 cc7 value=127
   ↓ (TMC hardware map)
Syntax: p1 value=127
   ↓ (TMC semantic map with range 0.0-1.0)
Semantic: track.1.vol value=1.0
```

TMC broadcasts to subscribers:
```
SEMANTIC track.1.vol 1.0
```

### 2. MIDI Mapper → tau

midi-mapper.sh receives broadcast, looks up mapping:

```
track.1.vol → CH 1 GAIN|0.0:1.0
```

Scales value (already 1.0 in this case) and sends:

```
CH 1 GAIN 1.0
```

via datagram to `tau.sock`.

### 3. tau Applies Change

tau.c receives datagram, parses line, applies:

```c
if (strcmp(tokens[0], "CH") == 0) {
    int ch = atoi(tokens[1]);
    if (strcmp(tokens[2], "GAIN") == 0) {
        float gain = atof(tokens[3]);
        atomic_store(&g_channels[ch-1].gain, gain);
    }
}
```

### 4. Broadcast Event

tau broadcasts to subscribers:

```
EVENT CHANNEL 1 GAIN 1.0
```

Any listener (logger, visualizer, etc.) receives the event.

---

## TSM Service Configuration

### tau Service

`$TETRA_DIR/tsm/services-available/tau.tsm`:
```bash
SERVICE_NAME="tau"
SERVICE_TYPE="binary"
SERVICE_COMMAND="$TAU_SRC/tau"
SERVICE_PORT="0"  # Socket-based
SERVICE_DIR="$TAU_SRC"
SERVICE_ENV="TAU_SRC=$TAU_SRC TAU_DIR=$TAU_DIR"
SERVICE_DESCRIPTION="tau realtime audio engine"
```

### MIDI Mapper Service

`$TETRA_DIR/tsm/services-available/tau-midi-mapper.tsm`:
```bash
SERVICE_NAME="tau-midi-mapper"
SERVICE_TYPE="bash"
SERVICE_COMMAND="bash $TAU_SRC/services/midi-mapper.sh"
SERVICE_PORT="0"
SERVICE_DIR="$TAU_SRC"
SERVICE_REQUIRES="tau midi"
SERVICE_DESCRIPTION="MIDI control mapping for tau"
```

### Event Logger Service

`$TETRA_DIR/tsm/services-available/tau-logger.tsm`:
```bash
SERVICE_NAME="tau-logger"
SERVICE_TYPE="bash"
SERVICE_COMMAND="bash $TAU_SRC/services/event-logger.sh"
SERVICE_PORT="0"
SERVICE_DIR="$TAU_SRC"
SERVICE_REQUIRES="tau"
SERVICE_DESCRIPTION="Log tau events to file"
```

---

## Complete Usage Example

### Initial Setup

```bash
# 1. Set globals
export TAU_SRC=~/src/mricos/demos/tau
export TAU_DIR=~/tau

# 2. Build tau binary
cd $TAU_SRC
./build.sh

# 3. Create directories
mkdir -p $TAU_DIR/{runtime,sessions,samples,config,logs}

# 4. Create MIDI map
cat > $TAU_DIR/config/tau-midi-map.txt <<EOF
track.1.vol|CH 1 GAIN|0.0:1.0
track.1.pan|CH 1 PAN|-1.0:1.0
track.1.lpf|CH 1 FILTER 1 {val} 1.0|100:8000
trigger.kick|SAMPLE 1 TRIG|
trigger.snare|SAMPLE 2 TRIG|
EOF

# 5. Enable TSM services
cd ~/tetra
tsm enable tau
tsm enable tau-midi-mapper
tsm enable tau-logger
```

### Start Services

```bash
# Start tau engine
tsm start tau

# Start MIDI mapper (requires MIDI service running)
tsm start midi          # If not already running
tsm start tau-midi-mapper

# Start logger
tsm start tau-logger

# Check all running
tsm list
```

### Use REPL

```bash
# Start REPL
tau repl

# Inside REPL:
tau> voice 1 sine 440 0.3    # Setup voice
tau> voice 1 on              # Turn on
tau> sample 1 load $TAU_DIR/samples/drums/kick.wav
tau> sample 1 chan 4         # Route to channel 4
tau> ch 4 gain 0.8           # Set channel gain
tau> save live-session-1     # Save state

# Now use MIDI controller:
# - Move fader 1 → controls track.1.vol → CH 1 GAIN
# - Press button → triggers kick sample

tau> quit
```

### Monitor Events

```bash
# In another terminal
tail -f $TAU_DIR/logs/events.log
```

### Stop Services

```bash
tsm stop tau-logger
tsm stop tau-midi-mapper
tsm stop tau
```

---

## Implementation Phases

### Phase 1: Core Datagram Engine ✅ (Current)
- ✅ C engine with audio (done as `engine.c`)
- ⬜ Convert OSC → Datagram protocol
- ⬜ Add line-based command parser
- ⬜ Unix socket creation/binding
- ⬜ TSM integration

### Phase 2: REPL & Basic Control
- ⬜ tau.sh REPL skeleton
- ⬜ Datagram send/recv functions
- ⬜ Custom line syntax parsing
- ⬜ Session save/load (JSON)

### Phase 3: MIDI Integration
- ⬜ midi-mapper.sh service
- ⬜ Map file parser
- ⬜ Value scaling logic
- ⬜ Subscribe to TMC broadcasts

### Phase 4: Services Ecosystem
- ⬜ Event logger service
- ⬜ Spectrum analyzer service
- ⬜ TSM service definitions
- ⬜ Auto-start on boot

### Phase 5: Advanced Features
- ⬜ Recording engine
- ⬜ Pattern sequencer
- ⬜ Preset management
- ⬜ TUI interface

---

## Key Differences from OSC Design

| Feature | OSC Design | Datagram Design |
|---------|-----------|-----------------|
| Transport | UDP network | Unix domain socket |
| Port | 9001 | No port (socket file) |
| Protocol | OSC binary | Line-based text |
| Discovery | IP:port | Socket path |
| TSM Integration | Not native | Native socket type |
| Bidirectional | Client polls | Datagram reply address |
| Broadcast | N/A | Socket publish list |

---

## Benefits of This Design

1. **TSM Native**: Sockets are first-class in TSM
2. **No Port Conflicts**: No network ports to manage
3. **Simple Protocol**: Human-readable line format
4. **Proven Pattern**: Follows pulsar game design
5. **MIDI Ready**: Clean integration with TMC
6. **Composable**: Services can be mixed/matched
7. **Tetra Compliant**: Strong globals, no dot files, bash 5.2+

---

## Next Steps

1. **Refactor engine.c → tau.c**: Replace OSC with datagram socket
2. **Implement line parser**: Parse text commands instead of OSC
3. **Create tau.sh REPL**: Interactive shell with custom syntax
4. **Write midi-mapper.sh**: First subscriber service
5. **TSM service definitions**: Integrate with tetra
6. **Test MIDI flow**: End-to-end MIDI → tau control

---

## Conclusion

This design makes **tau** a proper **tetra citizen**:

- TSM-managed processes (not ports)
- Datagram-based IPC (like pulsar)
- REPL with custom syntax (like TMC)
- MIDI semantic mapping (extensible config)
- No dot files, strong globals (CLAUDE.md compliant)

The result is a composable, extensible audio system that integrates seamlessly with the tetra ecosystem while maintaining clean separation of concerns and following established patterns.
