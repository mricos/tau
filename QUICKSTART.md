# tau Quick Start

## Installation

```bash
cd /Users/mricos/src/mricos/demos/tau

# Activate Python environment
source ~/tetra/tetra.sh && tetra_python_activate

# Install Python package
pip install -e .

# Build audio engine
cd engine && ./build.sh && cd ..
```

## Usage

### 1. REPL Mode (Default)

```bash
tau
```

Interactive shell for tau-engine:
```
tau> help
tau> MASTER 0.8
tau> SAMPLE 1 LOAD audio.wav
tau> SAMPLE 1 TRIG
tau> exit
```

### 2. TUI Mode

```bash
tau tui
tau tui audio.wav
```

Full terminal UI with waveform visualization and transport controls.

### 3. Single Commands

```bash
tau -c "SAMPLE 1 LOAD audio.wav"
tau -c "SAMPLE 1 TRIG"
tau -c "STATUS"
```

### 4. Script Mode

```bash
cat > demo.tau <<'EOF'
SAMPLE 1 LOAD audio.wav
SAMPLE 1 LOOP 1
SAMPLE 1 TRIG
EOF

tau -s demo.tau
```

## Examples

### Play a Sample
```bash
tau -c "SAMPLE 1 LOAD ~/audio/song.wav"
tau -c "SAMPLE 1 TRIG"
```

### Play a Synth Tone
```bash
tau -c "VOICE 1 FREQ 440"
tau -c "VOICE 1 GAIN 0.3"
tau -c "VOICE 1 ON"
```

### Stop Everything
```bash
tau -c "SAMPLE 1 STOP"
tau -c "VOICE 1 OFF"
```

### Shutdown Engine
```bash
tau -c "QUIT"
```

## Project Structure

```
tau/
├── engine/              # C audio engine
│   ├── tau-engine.c
│   ├── build.sh
│   └── tau-engine
├── tau_lib/             # Shared Python library
│   ├── core/            # state, config, commands
│   ├── data/            # data loading
│   └── integration/     # engine communication
├── repl_py/             # Python REPL (entry point)
│   ├── main.py          # Dispatcher (tau/tau tui)
│   ├── repl.py          # TauREPL class
│   └── cli/             # CLI manager
├── tui_py/              # Python TUI
│   ├── app.py           # Main curses app
│   ├── commands/        # Command definitions
│   ├── rendering/       # Waveform rendering
│   └── ui/              # Completion, palette
├── repl_c/              # C REPL (placeholder)
├── build.sh             # Build standalone
└── pyproject.toml       # Package config
```

## Tips

- **Tab completion** works in REPL mode
- **Command history** saved to `~/.tau_history`
- **Auto-start**: tau-engine starts automatically
- **Auto-stop**: engine stops when REPL exits (if it started it)
- **Config**: stored in `~/.config/tau/config.toml`

## Building Standalone

```bash
./build.sh              # Creates dist/tau executable
./build.sh clean        # Clean build artifacts
```
