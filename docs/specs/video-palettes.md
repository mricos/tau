# Video Palettes Specification

ASCII art rendering system for video frames in the TUI, with 4 palettes and brightness/contrast controls.

## Palettes

### Simple (default)
- Ramp: ` .:-=+*#%@` (10 chars)
- Fastest rendering (<1ms for 4x4, ~2ms for 80x40)
- Best for thumbnails in lane view

### Extended
- 70-character ramp for photorealistic quality
- Floyd-Steinberg dithering support
- ~3ms for 80x40 (+dithering: ~5ms)
- Best for popup viewer

### Braille (UTF-8 subpixel)
- Unicode Braille patterns (U+2800-U+28FF)
- 2x4 subpixel resolution (8 dots per character)
- Effectively doubles resolution
- ~4ms for 80x40
- Best for line art, diagrams, high-contrast content

Each Braille character encodes a 2x4 pixel grid:
```
Dot positions:    Unicode: chr(0x2800 + dot_mask)
1 4               Full block: chr(0x2800 + 0xFF) = U+28FF
2 5
3 6
7 8
```

### Blocks (UTF-8 high contrast)
- Characters: ` ` `░` `▒` `▓` `█`
- Maximum readability, retro aesthetic
- ~2ms for 80x40
- Best for low-light viewing, accessibility

## Image Adjustment

### Brightness (-1.0 to +1.0)
Uniform additive offset to all pixels.

### Contrast (0.1 to 3.0)
Multiplies pixel deviation from midpoint (127.5).

### Algorithm
```python
adjusted = (pixel - 127.5) * contrast + 127.5   # contrast first
adjusted = adjusted + (brightness * 255)          # then brightness
adjusted = clip(adjusted, 0, 255)
```

### Floyd-Steinberg Dithering (extended palette only)
Error diffusion pattern:
```
      current   7/16
3/16   5/16    1/16
```

## API

### Source Files
- `tui_py/rendering/video_palettes.py` — palette classes, `frame_to_ascii()`
- `tui_py/rendering/video.py` — rendering integration

### Core Function
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

### TUI Commands
```
:video_palette <name>        # Set palette (simple/extended/braille/blocks)
:video_palette_next          # Cycle palettes
:video_brightness <value>    # Set brightness (-1.0 to +1.0)
:video_contrast <value>      # Set contrast (0.1 to 3.0)
```

### Popup Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `p` | Cycle palette |
| `+` / `-` | Brightness +/- 0.1 |
| `>` / `<` | Contrast x/÷ 1.1 |
| `0` | Reset to defaults |

## Configuration

In `~/.config/tau/config.toml`:

```toml
[video]
enabled = true
sampling_interval = 1.0
thumbnail_size = 4
popup_resolution = [80, 40]
palette = "extended"
brightness = 0.0
contrast = 1.0
```

## Display Format

Lane view: `[5:V:video]  [frame]  0.5s/10.2s (5%) [braille] br:+0.2 ct:1.5`

Popup header: `video.mp4 2.5s/10.2s (25%) 1920x1080 30fps [extended] br:+0.1 ct:1.2`

Popup footer: `[V]close [space]play [arrows]scrub [+/-]brightness [</>]contrast [p]palette`

## Requirements

Braille and blocks palettes require a Unicode-compatible terminal font (DejaVu Sans Mono, Menlo, Monaco, Consolas).
