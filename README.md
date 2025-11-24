# ASCII Scope SNN - Multi-Page Oscilloscope for SNN Kernel Tuning

A modular, CLI-first terminal oscilloscope for visualizing and fine-tuning the dual-tau spike detection algorithm implemented in `tscale.c`.

## Features

- **Multi-Page Composable Interface**
  - Page 1: 4-channel oscilloscope with envelope/points rendering
  - Page 2: CLI command interface
  - Page 3: Real-time BPM analysis (4 methods) and comparative statistics
  - Page 4: Marker browser for time bookmarks

- **CLI-First Design**
  - All actions available as CLI commands
  - Keyboard shortcuts invoke CLI commands
  - Command history and tab completion

- **Real-Time Parameter Tuning**
  - Adjust tau_a, tau_r, threshold, refractory period
  - Live reprocessing with current parameters
  - Musical semitone scaling for tau adjustments

- **BPM Analysis** (4 methods simultaneously)
  - Simple ISI average
  - Histogram peak detection
  - Windowed analysis (tempo changes)
  - Autocorrelation

- **Comparative Statistics**
  - Count ratios (beat vs subdivision)
  - Timing precision (jitter, CV, MAD)
  - Cross-correlation and phase alignment

- **Marker System**
  - Time bookmarks for quick navigation
  - Jump to interesting sections
  - Persistent across sessions

- **TOML Configuration**
  - Auto-save on exit
  - Load/save parameter presets
  - Channel settings persistence

## Installation

```bash
# Install dependencies
pip install numpy tomli tomli_w

# Or for Python 3.11+
pip install numpy
```

## Usage

### Basic Launch

```bash
# From ascii_scope_snn directory
python -m ascii_scope_snn.main <tscale_output.txt> [audio_file.wav]

# Example
python -m ascii_scope_snn.main tscale.out.txt test.wav
```

### Keyboard Shortcuts

#### Transport Controls
- `Space` - Play/Pause
- `←/→` - Scrub backward/forward (1%)
- `Shift+←/→` - Scrub backward/forward (10%)
- `Home` - Jump to start
- `End` - Jump to end

#### Zoom
- `<` or `,` - Zoom in
- `>` or `.` - Zoom out

#### Pages (composable - multiple can be on)
- `1` - Toggle Page 1 (Oscilloscope)
- `2` - Toggle Page 2 (CLI)
- `3` - Toggle Page 3 (Statistics)
- `4` - Toggle Page 4 (Markers)
- `5` - Toggle Page 5 (reserved)

#### Channels
- `F1-F4` - Toggle channel visibility

#### Display
- `o` - Toggle envelope/points rendering

#### Quick Parameter Adjust
- `z/Z` - tau_a ±semitone
- `x/X` - tau_r ±semitone
- `c/C` - Threshold ±0.5σ
- `v/V` - Refractory ±5ms
- `K` - Reprocess with current parameters

#### Markers
- `m` - Create marker at playhead
- `` ` `` - Jump to next marker
- `~` - Jump to previous marker

#### CLI
- `:` - Enter CLI mode
- `ESC` - Exit CLI mode

#### Help
- `?` - Toggle help
- `q` - Quit

### CLI Commands

#### Transport
```
play                    - Start playback
stop                    - Stop playback
toggle_play             - Toggle play/pause
seek <time>             - Seek to time (seconds)
scrub <delta>           - Scrub by delta
scrub_pct <percent>     - Scrub by percentage
home                    - Jump to start
end                     - Jump to end
zoom <span>             - Set zoom (seconds)
zoom_in                 - Zoom in
zoom_out                - Zoom out
```

#### Channel Control (prefix-style)
```
toggle ch<N>            - Toggle channel visibility
gain ch<N> <value>      - Set gain
gain ch<N> <factor>x    - Multiply gain (e.g., gain ch1 1.1x)
offset ch<N> <value>    - Set vertical offset
reset ch<N>             - Reset channel to defaults
```

#### Parameters
```
tau_a <seconds>         - Set attack tau
tau_r <seconds>         - Set recovery tau
thr <sigma>             - Set threshold (sigma units)
ref <seconds>           - Set refractory period
tau_a_semitone <±N>     - Adjust tau_a by semitones
tau_r_semitone <±N>     - Adjust tau_r by semitones
reprocess               - Reprocess audio with current params
```

#### Markers
```
mark <label>            - Create marker at playhead
mark <time> <label>     - Create marker at specific time
goto <label>            - Jump to marker
list_markers            - List all markers
del_marker <label>      - Delete marker
next_marker             - Jump to next marker
prev_marker             - Jump to previous marker
```

#### Configuration
```
save <filename>         - Save config to TOML
load <filename>         - Load config from TOML
status                  - Show current status
```

#### Display
```
envelope                - Set envelope mode
points                  - Set points mode
toggle_mode             - Toggle rendering mode
```

#### Utility
```
help                    - Show command help
help <command>          - Show help for specific command
list_commands           - List all commands
clear                   - Clear CLI output
```

## Architecture

```
ascii_scope_snn/
├── main.py                # Entry point, event loop
├── state.py               # State management (AppState, Transport, Channels, etc.)
├── config.py              # TOML persistence
├── data_loader.py         # TSV data loading
├── cli/
│   ├── commands.py        # Command registry
│   ├── parser.py          # Prefix-style command parser
│   └── manager.py         # CLI state (input, history, output)
├── pages/
│   ├── base.py            # BasePage abstract class
│   ├── oscilloscope.py    # Page 1: 4-channel scope
│   ├── cli_page.py        # Page 2: CLI interface
│   ├── statistics.py      # Page 3: BPM + stats
│   └── markers.py         # Page 4: Marker browser
├── rendering/
│   ├── envelope.py        # Envelope rendering
│   ├── points.py          # Points rendering
│   └── helpers.py         # Utilities (formatting, colors, drawing)
└── analysis/
    ├── bpm.py             # 4 BPM calculation methods
    └── statistics.py      # Pulse comparison statistics
```

## Configuration File

Config is auto-saved to `~/.ascii_scope_snn.toml`:

```toml
[kernel]
tau_a = 0.001
tau_r = 0.005
threshold = 3.0
refractory = 0.015

[transport]
position = 12.34
span = 1.0

[[markers]]
time = 12.34
label = "intro-beat-clear"

[channels]
# Channel 0-3 settings...
```

## Data Format

Expected TSV format (tscale output):
```
time    audio   pulse1  pulse2
0.000   0.123   0.0     0.0
0.001   0.234   1.0     0.0
...
```

Columns:
- **time**: Time in seconds
- **audio**: Original audio signal (or filtered signal)
- **pulse1**: Beat detection (target for BPM)
- **pulse2**: Subdivision detection
- **env** (optional): Envelope

## Workflow

1. **Initial Exploration**
   - Load tscale output
   - Enable pages 1, 2, 3 (oscilloscope, CLI, statistics)
   - Zoom to interesting sections
   - Create markers at key points

2. **Parameter Tuning**
   - Adjust tau_a/tau_r with `z/Z` and `x/X`
   - Watch pulse1 detection in real-time
   - Press `K` to reprocess with new parameters
   - Monitor BPM estimates in Page 3

3. **Fine-Tuning for Beat Detection**
   - Target: pulse1 should hit "the beat"
   - Check BPM consensus across 4 methods
   - Adjust threshold/refractory if needed

4. **Subdivision Analysis**
   - Target: pulse2 should hit subdivisions
   - Check count ratio (expected 2:1, 3:1, or 4:1)
   - Check phase alignment %

5. **Save Preset**
   - `save preset_beat.toml` - Save working parameters

## Tips

- **Use markers liberally** - Mark sections with good/bad beat detection
- **Try all 4 BPM methods** - Consensus = high confidence
- **Watch count ratios** - Should be close to integer (2:1, 3:1, 4:1)
- **Check jitter** - Low jitter = stable beat detection
- **Use CLI for precision** - `tau_a 0.0015` for exact values
- **Keyboard for speed** - `z/Z` for quick exploration

## Troubleshooting

### No data appears
- Check file path
- Verify TSV format
- Ensure at least 2 columns (time, value)

### Reprocessing fails
- Verify `./tscale` executable exists
- Check audio file path
- Ensure tscale supports input format

### Strange rendering
- Try toggling envelope/points mode (`o`)
- Adjust channel offsets: `offset ch1 1.5`
- Reset channel: `reset ch1`

## Future Extensions

- **Page 5**: Spectrogram view
- **Multi-file comparison**: Compare different parameter sets side-by-side
- **Export markers**: Export to Audacity labels
- **Preset browser**: Quick-load parameter presets
- **Live audio input**: Real-time processing

## License

See parent project license.
