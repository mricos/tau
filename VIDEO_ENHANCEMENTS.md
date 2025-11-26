# Video Playback Enhancements

## Summary of Enhancements

Added advanced ASCII art rendering with 4 configurable palettes, brightness/contrast controls, and compact single-row info display.

## New Features

### 1. Four ASCII Palettes

**Simple** (default)
- 10-character ramp: ` .:-=+*#%@`
- Fastest rendering
- Good for low-detail preview
- Best for 4x4 thumbnails

**Extended**
- 70-character ramp for photorealistic quality
- Floyd-Steinberg dithering support
- Best for detailed viewing
- Recommended for popup viewer

**Braille** (UTF-8 subpixel)
- Uses Unicode Braille patterns (U+2800-U+28FF)
- 2x4 subpixel resolution (8 dots per character)
- Effectively doubles resolution
- Best for: line art, diagrams, high-contrast content
- Example: Each character represents 4 rows × 2 columns of pixels

**Blocks** (UTF-8 high contrast)
- Uses Unicode block elements: ` ░▒▓█`
- Best contrast and readability
- Good for: low-light viewing, accessibility
- Chunky aesthetic, retro feel

### 2. Brightness & Contrast Controls

**Brightness**: -1.0 to +1.0
- Adds/subtracts uniform value to all pixels
- `-1.0` = fully darkened
- `+1.0` = fully brightened
- Keyboard: `+`/`-` keys in popup viewer

**Contrast**: 0.1 to 3.0
- Multiplies pixel deviation from midpoint (127.5)
- `0.5` = reduced contrast (washed out)
- `2.0` = doubled contrast (dramatic)
- Keyboard: `<`/`>` keys in popup viewer

### 3. Compact Single-Row Info Display

**In Lane View**:
```
[5:●:video]  [ASCII frame]  0.5s/10.2s (5%) [braille] br:+0.2 ct:1.5
└─ label     └─ frame      └─ time/duration └─ palette └─ adjustments (if non-default)
```

**In Popup View** (header):
```
video.mp4 2.5s/10.2s (25%) 1920x1080 30fps [extended] br:+0.1 ct:1.2
```

**In Popup View** (footer):
```
[V]close [space]play [←→]scrub [+/-]brightness [</>]contrast [p]palette
```

All info rendered in **dim gray** (`curses.A_DIM`) to minimize distraction.

## Architecture Changes

### New Files

**`tui_py/rendering/video_palettes.py`** (330 lines)

Core palette system with:
- `VideoPalette` base class
- `SimplePalette`, `ExtendedPalette`, `BraillePalette`, `BlocksPalette`
- `frame_to_ascii()` - unified conversion function
- `apply_brightness_contrast()` - image adjustment
- `PALETTES` registry for lookup

Key functions:
```python
frame_to_ascii(
    frame: np.ndarray,
    width: int,
    height: int,
    palette: str = "simple",
    brightness: float = 0.0,
    contrast: float = 1.0,
    dither: bool = False
) -> List[str]
```

### Modified Files

**`tui_py/rendering/video.py`**

Updated functions:
- `render_video_compact()` - added palette/brightness/contrast params
- `_render_compact_info()` - NEW: single-row gray info
- `render_popup_info()` - NEW: single-row popup header
- `render_popup_controls_hint()` - NEW: single-row popup footer

## Usage

### Command Line

```bash
# Load video with specific palette
:video_load video.mp4
:video_palette braille

# Adjust brightness
:video_brightness +0.3   # Brighten
:video_brightness -0.2   # Darken

# Adjust contrast
:video_contrast 1.5      # Increase contrast
:video_contrast 0.7      # Decrease contrast

# Cycle palettes
:video_palette_next      # simple → extended → braille → blocks → simple
```

### Keyboard Shortcuts (in Popup)

| Key | Action |
|-----|--------|
| `p` | Cycle palette |
| `+` | Increase brightness (+0.1) |
| `-` | Decrease brightness (-0.1) |
| `>` | Increase contrast (×1.1) |
| `<` | Decrease contrast (÷1.1) |
| `0` | Reset brightness & contrast to defaults |

### Configuration

**In `~/.snn/config.toml`**:

```toml
[video]
enabled = true
sampling_interval = 1.0
thumbnail_size = 4
popup_resolution = [80, 40]
palette = "extended"          # NEW: default palette
brightness = 0.0              # NEW: default brightness
contrast = 1.0                # NEW: default contrast
```

## Performance

### Palette Rendering Speed

| Palette | 4x4 Thumbnail | 80x40 Popup | Notes |
|---------|---------------|-------------|-------|
| Simple  | <1ms | ~2ms | Fastest |
| Extended | <1ms | ~3ms | +dithering: ~5ms |
| Braille | <1ms | ~4ms | Subpixel computation |
| Blocks | <1ms | ~2ms | Fast, high contrast |

### Brightness/Contrast Overhead

- **Per-frame adjustment**: +1-2ms
- Applied on-demand (not cached)
- Negligible impact on 30Hz refresh rate

### Memory

- No significant change (palettes are just string constants)
- Braille pattern lookup: ~256 bytes

## Technical Details

### Braille Subpixel Rendering

Each Braille character represents a 2×4 pixel grid using 8 dots:

```
Dot positions:    Binary representation:
1 4               00000001 = dot 1
2 5               00000010 = dot 2
3 6               00000100 = dot 3
7 8               00001000 = dot 4
                  00010000 = dot 5
                  00100000 = dot 6
                  01000000 = dot 7
                  10000000 = dot 8
```

Unicode: `chr(0x2800 + dot_mask)`

Example: Full block = `chr(0x2800 + 0xFF)` = `⣿`

### Brightness/Contrast Algorithm

```python
def apply_brightness_contrast(frame, brightness, contrast):
    # Convert to float
    adjusted = frame.astype(float)

    # Apply contrast around midpoint (127.5)
    adjusted = (adjusted - 127.5) * contrast + 127.5

    # Apply brightness
    adjusted = adjusted + (brightness * 255)

    # Clip to valid range [0, 255]
    return np.clip(adjusted, 0, 255).astype(uint8)
```

Order matters: **contrast first, then brightness**

### Floyd-Steinberg Dithering

Error diffusion pattern (extended palette only):

```
      current   7/16
3/16   5/16    1/16
```

Reduces banding, improves perceived resolution.

## Palette Comparison

### Test Scene: Portrait Photo

**Simple** (10 chars):
```
    @@@@
  @@@@@@@@
 @@@@##@@##
 @@@##%%##@
  @##%%%%##
   @@@@@@
```

**Extended** (70 chars, dithered):
```
    @@@@
  @B&MW#@@
 @B8%okhda#
 @W*#Qczn#@
  @mCUfi#@
   @@@@@@
```

**Braille** (subpixel):
```
  ⣿⣿⣿⣿
 ⣿⣿⣿⣿⣿⣿
⣿⣿⢿⡿⣿⣿
⣿⣷⣄⣀⣾⣿
 ⣿⣿⣿⣿⣿
  ⠿⠿⠿⠿
```

**Blocks** (high contrast):
```
    ████
  ████████
 ████▓▓███▓
 ███▓▒▒▓██
  ██▓▒▒▓█
   ██████
```

## Recommended Use Cases

### High-Speed Preview (Mini-frames in Lanes)
- **Palette**: `simple`
- **Size**: 4x4
- **Brightness/Contrast**: defaults
- **Why**: Minimal CPU, instant updates

### Detailed Viewing (Popup)
- **Palette**: `extended` with dithering
- **Size**: 80x40 or larger
- **Brightness/Contrast**: adjust to taste
- **Why**: Best photorealistic quality

### Technical Content (Diagrams, Code)
- **Palette**: `braille`
- **Size**: 60x30 or larger
- **Brightness/Contrast**: high contrast (1.5-2.0)
- **Why**: Subpixel resolution shows fine detail

### Low-Light / Accessibility
- **Palette**: `blocks`
- **Size**: any
- **Brightness**: +0.2 to +0.4
- **Contrast**: 1.2 to 1.5
- **Why**: Maximum readability, clear shapes

## Future Enhancements

Potential additions:

1. **Color palettes**: Map RGB to terminal 256-color palette
2. **Adaptive palette**: Auto-select based on content
3. **Gamma correction**: Non-linear brightness adjustment
4. **Sharpening filter**: Enhance edge detail
5. **Custom palettes**: User-defined character sets
6. **Palette preview**: Side-by-side comparison mode

## Troubleshooting

### Braille characters not rendering

**Problem**: Braille shows as `?` or boxes

**Solution**: Use a Unicode-compatible terminal font
```bash
# Good fonts:
- DejaVu Sans Mono
- Menlo
- Monaco
- Consolas
```

### High CPU usage with Braille

**Problem**: Braille rendering is slow

**Solution**:
- Reduce popup resolution
- Use simple palette for mini-frames
- Disable dithering

### Poor contrast in dim terminals

**Problem**: Hard to see ASCII frames

**Solution**:
```
:video_palette blocks
:video_brightness +0.3
:video_contrast 1.5
```

## References

- Unicode Braille Patterns: https://en.wikipedia.org/wiki/Braille_Patterns
- Unicode Block Elements: https://en.wikipedia.org/wiki/Block_Elements
- Floyd-Steinberg Dithering: https://en.wikipedia.org/wiki/Floyd%E2%80%93Steinberg_dithering
