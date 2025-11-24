# Migration Guide: ascii_scope_snn.py → ascii_scope_snn/

This guide explains the changes from the monolithic `ascii_scope_snn.py` to the new modular architecture.

## What Changed

### 1. File Structure

**Before:**
```
ascii_scope_snn.py  (1 file, ~800 lines)
```

**After:**
```
ascii_scope_snn/
├── main.py                # Entry point (~350 lines)
├── state.py               # State management (~280 lines)
├── config.py              # TOML persistence (~180 lines)
├── data_loader.py         # Data loading (~120 lines)
├── cli/                   # CLI system
│   ├── commands.py        # Command registry (~450 lines)
│   ├── parser.py          # Command parser (~120 lines)
│   └── manager.py         # CLI manager (~130 lines)
├── pages/                 # Page system
│   ├── base.py            # Base class (~40 lines)
│   ├── oscilloscope.py    # Scope page (~70 lines)
│   ├── cli_page.py        # CLI page (~60 lines)
│   ├── statistics.py      # Stats page (~80 lines)
│   └── markers.py         # Markers page (~50 lines)
├── rendering/             # Rendering helpers
│   ├── envelope.py        # Envelope mode (~70 lines)
│   ├── points.py          # Points mode (~60 lines)
│   └── helpers.py         # Utilities (~150 lines)
└── analysis/              # Analysis modules
    ├── bpm.py             # BPM calculation (~220 lines)
    └── statistics.py      # Pulse comparison (~180 lines)
```

### 2. Key Binding Changes

| Old Key | New Key | Action |
|---------|---------|--------|
| `1-4` | `F1-F4` | Toggle channel visibility |
| `h` | `?` | Show help (h removed) |
| - | `m` | Create marker |
| - | `` ` `` | Next marker |
| - | `~` | Prev marker |

All other keys remain the same.

### 3. New Features

#### Multi-Page System
- **Page 1**: Oscilloscope (same as before)
- **Page 2**: CLI (enhanced with command history)
- **Page 3**: Statistics (NEW - BPM + comparative analysis)
- **Page 4**: Markers (NEW - bookmark browser)

#### CLI Commands
ALL actions now available as CLI commands:
```bash
:tau_a 0.0015        # Set tau_a precisely
:gain ch1 1.5        # Set channel gain
:mark beat_start     # Create marker
:save preset.toml    # Save configuration
```

#### BPM Analysis (4 Methods)
- ISI Average
- Histogram Peak
- Windowed Analysis
- Autocorrelation

#### Comparative Statistics
- Count ratios (pulse1:pulse2)
- Timing precision (jitter, CV)
- Cross-correlation
- Phase alignment

#### Marker System
- Time bookmarks with labels
- Quick navigation
- Persistent across sessions

#### TOML Configuration
- Auto-save on exit to `~/.ascii_scope_snn.toml`
- Save/load parameter presets
- Channel settings persistence

### 4. Running the New Version

**Old way:**
```bash
python ascii_scope_snn.py tscale.out.txt audio.wav
```

**New way:**
```bash
python -m ascii_scope_snn.main tscale.out.txt audio.wav
```

Or use the test script first:
```bash
python test_scope.py
```

### 5. Configuration

The new version saves configuration automatically:
```toml
# ~/.ascii_scope_snn.toml
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

# ... channels, pages, etc.
```

### 6. Architecture Benefits

#### Testability
Each module is independently testable:
```python
from ascii_scope_snn.analysis.bpm import calculate_bpm_all_methods
bpm_results = calculate_bpm_all_methods(data_buffer, channel_id=1)
```

#### Extensibility
Add new pages easily:
```python
from ascii_scope_snn.pages.base import BasePage

class MyPage(BasePage):
    def render(self, scr, layout):
        # Your rendering code
        pass
```

Add new commands:
```python
def cmd_my_command(self, args):
    # Your command logic
    return "✓ Command executed"

commands.register("my_command", cmd_my_command, "My command help")
```

#### Reusability
Import and use components in other projects:
```python
from ascii_scope_snn.analysis.bpm import bpm_simple_isi
from ascii_scope_snn.state import KernelParams

params = KernelParams(tau_a=0.001, tau_r=0.005)
print(params.to_tscale_args())
```

### 7. Migration Checklist

- [ ] Install numpy if not already installed: `pip install numpy`
- [ ] Install TOML libraries: `pip install tomli tomli_w` (or skip for Python 3.11+)
- [ ] Test basic functionality: `python test_scope.py`
- [ ] Run new application: `python -m ascii_scope_snn.main tscale.out.txt`
- [ ] Learn new key bindings: `?` for help, `F1-F4` for channels
- [ ] Explore CLI commands: Press `:` and type `help`
- [ ] Try new pages: Press `3` for statistics, `4` for markers
- [ ] Create markers: Press `m` or use `:mark label`
- [ ] Save presets: `:save my_preset.toml`

### 8. Backward Compatibility

The old `ascii_scope_snn.py` is **still functional** if you need it. The new system reads the same tscale output format.

### 9. Performance

The new system should have similar or better performance:
- Same rendering algorithms (envelope/points)
- Optimized data windowing with binary search
- Page-level rendering (only render visible pages)

### 10. Future Extensions

The modular architecture makes these easy to add:
- **Page 5**: Spectrogram view
- **Multi-file comparison**: Side-by-side parameter comparison
- **Export features**: Markers → Audacity labels
- **Plugin system**: Load custom analysis modules
- **Live audio**: Real-time processing

## Getting Help

- Press `?` in the application for keyboard reference
- Type `:help` in CLI for command list
- Type `:help <command>` for specific command help
- Read `README.md` for full documentation
- Run `python test_scope.py` to verify installation

## Reporting Issues

The new system is thoroughly tested but if you encounter issues:
1. Run `python test_scope.py` to isolate the problem
2. Check that tscale output format is correct (TSV with time + values)
3. Verify numpy is installed: `python -c "import numpy; print(numpy.__version__)"`
4. Check TOML library: `python -c "import tomli; print('OK')"` (or tomllib for 3.11+)
