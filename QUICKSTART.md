# tau Quick Start

## Installation

```bash
cd /Users/mricos/src/mricos/demos/tau
cd engine && make  # Build tau-engine if not already built
```

## Usage

### 1. REPL Mode (Default) - Direct Engine Control

```bash
python -m tau
```

Interactive shell for tau-engine daemon:
```
tau> help
tau> MASTER 0.8
tau> SAMPLE 1 LOAD audio.wav
tau> SAMPLE 1 TRIG
tau> exit
```

### 2. TUI Mode - Full Workstation

```bash
python -m tau -tui audio.wav
```

Full terminal UI with:
- Multi-track waveform visualization
- Neural network kernel parameter tuning
- Real-time transport controls
- Lane-based mixing

### 3. Single Commands

```bash
python -m tau -c "SAMPLE 1 LOAD audio.wav"
python -m tau -c "SAMPLE 1 TRIG"
```

### 4. Script Mode

```bash
# Create script
cat > demo.tau <<'EOF'
SAMPLE 1 LOAD audio.wav
SAMPLE 1 LOOP 1
SAMPLE 1 TRIG
EOF

# Run it
python -m tau -s demo.tau
```

## Quick Examples

### Play a Sample
```bash
cd /Users/mricos/src/mricos/demos
python -m tau -c "SAMPLE 1 LOAD ~/audio/song.wav"
python -m tau -c "SAMPLE 1 TRIG"
```

### Play a Synth Tone
```bash
python -m tau -c "VOICE 1 FREQ 440"
python -m tau -c "VOICE 1 GAIN 0.3"
python -m tau -c "VOICE 1 ON"
```

### Stop Everything
```bash
python -m tau -c "SAMPLE 1 STOP"
python -m tau -c "VOICE 1 OFF"
```

### Shutdown Engine
```bash
python -m tau -c "QUIT"
```

## File Structure

```
tau/
├── __main__.py          # Entry point (dispatches REPL vs TUI)
├── repl.py              # REPL implementation
├── main.py              # TUI implementation
├── tau_playback.py      # Python API
├── engine/
│   └── tau-engine       # Audio daemon binary
└── README_REPL.md       # Full documentation
```

## Tips

- **Tab completion** works in REPL mode
- **Command history** saved to ~/.tau_history
- **Auto-start**: tau-engine starts automatically if needed
- **Persistent**: Engine keeps running after REPL exits
- **Multiple clients**: Can connect multiple REPLs to same engine

## See README_REPL.md for full documentation
