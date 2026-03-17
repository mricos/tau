# tau - Terminal Audio Workstation

A modular audio workstation with a real-time C engine and Python interface.

## Features

- **Real-time Audio Engine** (C)
  - 48kHz sample rate, 512-frame buffer
  - 4 mixer channels with gain, pan, filters
  - 16 sample slots with loop/seek
  - 8 synth voices (sine/pulse)
  - PERC/SUST envelope system
  - Unix socket control

- **Python REPL**
  - Interactive shell with tab completion
  - Command history
  - Auto-starts engine

- **Python TUI**
  - Multi-track waveform visualization
  - Lane-based mixing
  - ASCII video palettes (simple, extended, braille, blocks)
  - Transport controls

## Quick Start

```bash
# Install
cd $TAU_SRC
source ~/tetra/tetra.sh && tetra_python_activate
pip install -e .

# Build engine
cd engine && ./build.sh && cd ..

# Run REPL
tau

# Run TUI
tau tui
```

## Usage

### REPL (default)

```bash
tau                     # Start interactive REPL
tau -c "STATUS"         # Execute single command
tau -s script.tau       # Run script file
```

REPL commands:
```
tau> help               # Show commands
tau> STATUS             # Engine status
tau> MASTER 0.8         # Set master gain
tau> SAMPLE 1 LOAD audio.wav
tau> SAMPLE 1 TRIG      # Play sample
tau> SAMPLE 1 STOP
tau> QUIT               # Stop engine
tau> exit               # Exit REPL (engine keeps running)
```

### TUI

```bash
tau tui                 # Start TUI
tau tui audio.wav       # Load audio file
```

### Single Commands

```bash
tau -c "SAMPLE 1 LOAD ~/audio/song.wav"
tau -c "VOICE 1 FREQ 440"
tau -c "VOICE 1 GAIN 0.3"
tau -c "VOICE 1 ON"
```

### Script Mode

```bash
cat > demo.tau <<'EOF'
SAMPLE 1 LOAD audio.wav
SAMPLE 1 LOOP 1
SAMPLE 1 TRIG
EOF

tau -s demo.tau
```

## Project Structure

```
tau/
├── engine/             # C audio engine
│   ├── tau-engine.c    # Main engine source
│   ├── build.sh        # Build script
│   └── tau-engine      # Compiled binary
├── tau_lib/            # Shared Python library
│   ├── core/           # state, config, commands
│   ├── data/           # data loading, recording API
│   ├── integration/    # engine communication
│   └── bash/           # Bash API for screentool
├── repl_py/            # Python REPL
│   ├── main.py         # Entry point
│   ├── repl.py         # TauREPL class
│   └── cli/            # CLI manager
├── tui_py/             # Python TUI
│   ├── app.py          # Main application
│   ├── commands/       # TUI commands
│   ├── content/        # lanes, clips
│   ├── rendering/      # waveform, sparkline, video
│   └── ui/             # completion, palette
├── player_py/          # Mini console music player
├── repl_c/             # C REPL (placeholder)
├── docs/               # Documentation & specs
├── build.sh            # Build standalone app
├── tau.spec            # PyInstaller config
└── pyproject.toml      # Package config
```

## Configuration

Config stored in `~/.config/tau/config.toml`:

```toml
[kernel]
tau_a = 0.001
tau_r = 0.005
threshold = 3.0

[transport]
position = 0.0
span = 1.0
```

## Engine Protocol

tau-engine accepts line-based commands via Unix socket. See [docs/specs/engine-protocol.md](docs/specs/engine-protocol.md) for the full spec.

```
MASTER <gain>                    # Master volume (0.0-1.0)
CH <1-4> GAIN|PAN|FILTER ...     # Channel control
SAMPLE <1-16> LOAD|TRIG|STOP ... # Sample playback
VOICE <1-8> ON|OFF|FREQ|GAIN ... # Synth voices
RECORD START|STOP|STATUS         # Recording control
STATUS                           # Get status
QUIT                             # Shutdown engine
```

## Building Standalone

```bash
./build.sh              # Build for current platform
./build.sh clean        # Clean build artifacts
```

Creates `dist/tau` - single executable with bundled Python.

## Tips

- **Tab completion** works in REPL mode
- **Command history** saved to `~/.tau_history`
- **Auto-start**: tau-engine starts automatically
- **Auto-stop**: engine stops when REPL exits (if it started it)

## Documentation

```
docs/
├── screentool-integration.md  # Using tau with screentool
└── specs/
    ├── engine-protocol.md     # Socket command protocol
    ├── recording-api.md       # Python & Bash recording API
    ├── library-first-design.md # Architecture & design rationale
    ├── av-sync.md             # A/V sync, session format, metadata
    └── video-palettes.md      # ASCII video rendering system
```

## License

See parent project license.
