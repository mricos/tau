# tau - Audio Engine REPL

Interactive command-line interface for controlling tau-engine audio daemon.

## Quick Start

```bash
# Start interactive REPL (default mode)
python -m tau

# Or from parent directory
cd /Users/mricos/src/mricos/demos
python -m tau
```

## Usage Modes

### 1. Interactive REPL (Default)

```bash
python -m tau
```

Interactive shell with:
- **Tab completion** for commands and arguments
- **Command history** (saved to `~/.tau_history`)
- **Colored output** (green=success, red=error)
- **Up/Down arrows** for history navigation

Example session:
```
tau> STATUS
OK STATUS running

tau> MASTER 0.8
OK MASTER 0.800

tau> SAMPLE 1 LOAD ~/audio/kick.wav
OK SAMPLE 1 LOADED /Users/you/audio/kick.wav

tau> SAMPLE 1 LOOP 1
OK SAMPLE 1 LOOP 1

tau> SAMPLE 1 TRIG
OK SAMPLE 1 PLAYING

tau> exit
Goodbye! (tau-engine still running)
```

### 2. Single Command Mode

Execute one command and exit:

```bash
python -m tau -c "MASTER 0.5"
python -m tau -c "SAMPLE 1 LOAD audio.wav"
python -m tau -c "STATUS"
```

### 3. Script Mode

Run commands from a file:

```bash
python -m tau -s script.tau
```

Example script (`demo.tau`):
```bash
# Setup
STATUS
MASTER 0.7

# Load samples
SAMPLE 1 LOAD ~/audio/kick.wav
SAMPLE 2 LOAD ~/audio/snare.wav

# Configure
SAMPLE 1 LOOP 1
SAMPLE 1 GAIN 0.8
SAMPLE 1 CHAN 0

# Play
SAMPLE 1 TRIG
```

### 4. TUI Mode (Full Workstation)

Launch the full terminal UI workstation:

```bash
python -m tau -tui [audio.wav]
python -m tau --tui [audio.wav]
```

## Command Reference

### Engine Status
```
STATUS                          Check if tau-engine is running
QUIT                           Shutdown tau-engine daemon
```

### Master Controls
```
MASTER <gain>                  Set master output gain (0.0-10.0)
```

### Channel/Bus Controls
```
CH <1-4> GAIN <gain>          Set channel gain (0.0-10.0)
CH <1-4> PAN <pan>            Set stereo pan (-1.0=left, 0=center, 1.0=right)
CH <1-4> FILTER <type> <cutoff> <q>
                               Set channel filter
                               type: 0=off, 1=LP, 2=HP, 3=BP
                               cutoff: Hz (20-20000)
                               q: resonance (0.1-20.0)
```

### Sample/Track Controls
```
SAMPLE <1-16> LOAD <path>     Load audio file (.wav, .mp3, etc)
SAMPLE <1-16> TRIG            Start playback
SAMPLE <1-16> STOP            Stop playback
SAMPLE <1-16> GAIN <gain>     Set sample gain (0.0-10.0)
SAMPLE <1-16> CHAN <0-3>      Assign to mixer channel
SAMPLE <1-16> LOOP <0|1>      Enable/disable looping
SAMPLE <1-16> SEEK <seconds>  Seek to position
```

### Synth Voice Controls
```
VOICE <1-8> ON                Turn voice on
VOICE <1-8> OFF               Turn voice off
VOICE <1-8> WAVE <0|1>        Set waveform (0=sine, 1=pulse)
VOICE <1-8> FREQ <hz>         Set frequency (Hz)
VOICE <1-8> GAIN <gain>       Set voice gain (0.0-2.0)
VOICE <1-8> CHAN <0-3>        Assign to mixer channel
VOICE <1-8> SPIKE             Inject spike to LIF modulator
VOICE <1-8> TAU <tau_a> <tau_b>  Set LIF time constants (seconds)
```

## Examples

### Basic Playback
```bash
# Load and play a sample
python -m tau -c "SAMPLE 1 LOAD ~/audio/song.wav"
python -m tau -c "SAMPLE 1 LOOP 1"
python -m tau -c "SAMPLE 1 TRIG"

# Seek around
python -m tau -c "SAMPLE 1 SEEK 30.0"

# Stop
python -m tau -c "SAMPLE 1 STOP"
```

### Synth Voice
```bash
# Play a 440Hz sine wave
python -m tau -c "VOICE 1 FREQ 440"
python -m tau -c "VOICE 1 WAVE 0"
python -m tau -c "VOICE 1 GAIN 0.3"
python -m tau -c "VOICE 1 ON"

# Stop
python -m tau -c "VOICE 1 OFF"
```

### Multi-track Setup
```bash
# Load 4 tracks
python -m tau -c "SAMPLE 1 LOAD kick.wav"
python -m tau -c "SAMPLE 2 LOAD snare.wav"
python -m tau -c "SAMPLE 3 LOAD hihat.wav"
python -m tau -c "SAMPLE 4 LOAD bass.wav"

# Configure channels
python -m tau -c "SAMPLE 1 CHAN 0"  # Drums on channel 0
python -m tau -c "SAMPLE 2 CHAN 0"
python -m tau -c "SAMPLE 3 CHAN 1"  # Hi-hat on channel 1
python -m tau -c "SAMPLE 4 CHAN 2"  # Bass on channel 2

# Mix
python -m tau -c "CH 1 GAIN 0.8"
python -m tau -c "CH 2 GAIN 0.6"
python -m tau -c "CH 3 GAIN 0.7"

# Play
python -m tau -c "SAMPLE 1 TRIG"
python -m tau -c "SAMPLE 2 TRIG"
python -m tau -c "SAMPLE 3 TRIG"
python -m tau -c "SAMPLE 4 TRIG"
```

## Options

```
-c, --command <cmd>           Execute single command and exit
-s, --script <file>           Run commands from script file
--socket <path>               Custom socket path (default: ~/tau/runtime/tau.sock)
--no-auto-start               Don't auto-start tau-engine if not running
-tui, --tui                   Launch full TUI workstation instead
```

## Architecture

```
tau REPL → Unix Socket → tau-engine daemon
                              ↓
                         Audio Output (CoreAudio/ALSA)
```

The REPL communicates with tau-engine via Unix domain sockets using a simple line-based protocol. The engine runs as a background daemon and continues running even after the REPL exits.

## Tips

- **Auto-start**: tau-engine automatically starts if not running
- **Tab completion**: Press Tab to complete commands
- **History**: Use Up/Down arrows to browse command history
- **Comments**: Script files support `#` comments
- **Persistent engine**: tau-engine keeps running after REPL exits
- **Multiple clients**: Multiple REPLs can connect to same engine

## Files

- `~/.tau_history` - Command history
- `~/tau/runtime/tau.sock` - Unix socket for tau-engine
- `repl.py` - REPL implementation
- `tau_playback.py` - Python API wrapper
- `engine/tau-engine.c` - C audio engine daemon

## See Also

- `tau -tui` - Full terminal workstation with waveform visualization
- `tau_playback.py` - Python API for programmatic control
- `engine/tau-engine.c` - C implementation of audio engine
