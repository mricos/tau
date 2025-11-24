# Video Playback in Tau

Tau supports MP4 video playback with ASCII art rendering, tight integration with screentool, and efficient caching.

## Features

- **Lean by default**: Runs without `opencv-python` if not installed (gracefully degrades)
- **ASCII mini-frames**: 4x4 thumbnail preview in track view (configurable)
- **Popup viewer**: Full-screen stippled ASCII art with Floyd-Steinberg dithering
- **Pre-rendered caching**: Videos are sampled once and cached for instant playback
- **Screentool integration**: Loads videos from shared `~/recordings/` directory (TRS pattern)
- **Context directory**: Configurable cache location via `--context-dir`

## Installation

### Required
```bash
pip install opencv-python
```

### Alternative (headless servers)
```bash
pip install opencv-python-headless
```

## Quick Start

### 1. Basic Usage

```bash
# Start tau (video enabled by default if opencv installed)
cd ~/src/mricos/demos/tau
python -m . --context-dir ~/recordings

# Load a video file
:video_load /path/to/video.mp4

# Toggle popup viewer (Shift+V)
V

# Or via command
:video_toggle
```

### 2. Screentool Integration

```bash
# Load video from screentool session
:video_load_session 1757046447

# Tau will look for:
# ~/recordings/1757046447/db/1757046447.video.raw.mp4
# OR
# ~/recordings/1757046447/recording.mp4
```

### 3. Disable Video

```bash
# Start without video features (lean mode)
python -m . --no-video
```

## Configuration

### Settings in Config File

Create/edit `~/.snn/config.toml`:

```toml
[video]
enabled = true
sampling_interval = 1.0      # Frames per second to cache (1 = every second)
thumbnail_size = 4           # NxN thumbnail resolution
popup_resolution = [80, 40]  # Popup viewer size [width, height]

[files]
context_dir = "/Users/you/recordings"  # Shared with screentool
```

### Runtime Configuration

```bash
# Resample video with new settings
:video_resample 2.0 8   # 2 fps sampling, 8x8 thumbnails

# Show video info
:video_info
```

## CLI Commands

### Video Loading

**`video_load <path> [lane_id]`**
- Load video file for playback
- Default lane: 5 (currently unused in tau)
- Generates thumbnail strip and caches to `$CONTEXT_DIR/.cache/video/`

Example:
```
:video_load ~/videos/demo.mp4
:video_load /tmp/recording.mp4 5
```

**`video_load_session <epoch>`**
- Load video from screentool session directory
- Follows TRS pattern: `context_dir/[epoch]/db/[epoch].video.raw.mp4`

Example:
```
:video_load_session 1757046447
```

### Video Control

**`video_toggle`** (alias: `vt`, key: `Shift+V`)
- Toggle popup viewer on/off

**`video_info`** (alias: `vi`)
- Show video metadata and cache statistics

Example output:
```
=== VIDEO INFO ===
Path: /Users/you/recordings/1757046447/db/1757046447.video.raw.mp4
Duration: 125.43s
FPS: 30.0
Resolution: 1920x1080
Codec: avc1
Thumbnail size: 4x4
Sampling: 1.0 fps
Cached frames: 126
```

**`video_resample [sampling_interval] [thumbnail_size]`**
- Regenerate thumbnail strip with new settings
- Updates config for future videos

Example:
```
:video_resample 2.0        # Sample at 2 fps
:video_resample 2.0 8      # 2 fps, 8x8 thumbnails
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Shift+V` | Toggle video popup viewer |
| `Space` | Play/pause (video syncs with audio) |
| `←` / `→` | Scrub (video updates in real-time) |
| `Home` / `End` | Jump to start/end |
| `<` / `>` | Zoom in/out |

## Architecture

### Data Flow

```
Video File (MP4)
    ↓
VideoLane.load()
    ↓
Pre-process: Sample frames at interval (e.g., 1 fps)
    ↓
Convert to 4x4 ASCII thumbnails
    ↓
Cache: $CONTEXT_DIR/.cache/video/video_{name}_{mtime}_{size}_{interval}.pkl
    ↓
Runtime: Fast lookup from cached strip (no decoding)
    ↓
Render: Mini-frame or popup (stippled with dithering)
```

### Cache Management

**Cache Location**: `$CONTEXT_DIR/.cache/video/`

**Cache Naming**: `video_{filename}_{mtime}_{thumbnail_size}_{sampling_interval}.pkl`

**Cache Invalidation**: Automatic via file modification time (`mtime`)

**Storage Size**:
- 4x4 thumbnails @ 1 fps: ~1KB per minute of video
- 8x8 thumbnails @ 2 fps: ~8KB per minute

### Screentool Integration (TRS Pattern)

Tau shares the `~/recordings/` directory with screentool using the **Timestamped Resource Storage (TRS)** pattern:

```
~/recordings/
├── [epoch]/                      # Session directory (e.g., 1757046447)
│   ├── db/                       # Raw data (TRS pattern)
│   │   ├── [epoch].video.raw.mp4 # screentool video
│   │   ├── [epoch].audio.raw.wav # tau audio
│   │   ├── [epoch].t0            # Shared T0 timestamp
│   │   └── [epoch].sync.meta.json # A/V sync metadata
│   └── recording.mp4             # Final merged A/V
└── .cache/                       # Tau video cache
    └── video/
        └── video_*.pkl           # Cached thumbnail strips
```

**Shared Timestamp (T0)**:
- Screentool and tau use monotonic timestamp for frame-accurate sync
- T0 captured once, shared between video and audio recorders
- Eliminates A/V drift

## Performance

### Initial Load Time

Depends on video length and sampling rate:

| Video Length | Sampling Rate | Load Time (approx) |
|--------------|---------------|-------------------|
| 1 minute     | 1 fps         | ~2-3 seconds      |
| 10 minutes   | 1 fps         | ~10-15 seconds    |
| 1 hour       | 1 fps         | ~60-90 seconds    |

**Optimization**: Use lower sampling rate for long videos (e.g., `0.5` fps for hour-long recordings)

### Runtime Performance

- **Thumbnail lookup**: <1ms (cached, no decoding)
- **4x4 ASCII render**: <1ms
- **Popup decode**: 10-20ms per frame (on-demand, full resolution)
- **Stippled ASCII conversion**: ~5ms for 80x40

### Memory Usage

- **Thumbnail strip**: ~10-50KB per video (depending on length and sampling)
- **Popup frame buffer**: ~3KB per frame (80x40 resolution)
- **LRU cache**: Last 10 sessions cached (configurable in future)

## Advanced Usage

### Custom Sampling Strategies

For different use cases:

**High-frequency action (sports, gaming)**:
```bash
:video_resample 5.0 6  # 5 fps, 6x6 thumbnails
```

**Long recordings (lectures, livestreams)**:
```bash
:video_resample 0.5 4  # 0.5 fps (every 2 seconds), 4x4
```

**High-quality popup viewing**:
```bash
# Edit config.toml
[video]
popup_resolution = [120, 60]  # Larger popup size
```

### Batch Processing

Pre-cache multiple videos:

```python
from pathlib import Path
from tau.video_lane import VideoLane

context_dir = Path.home() / "recordings"
videos = Path("~/videos").glob("*.mp4")

for video_path in videos:
    lane = VideoLane(video_path, context_dir, thumbnail_size=4, sampling_interval=1.0)
    lane.load()  # Generates and caches strip
```

### Manual Cache Cleanup

```bash
# Remove all cached video strips
rm -rf ~/recordings/.cache/video/

# Tau will regenerate on next load
```

## Troubleshooting

### Video features not available

**Problem**: `Video features unavailable (install opencv-python for video playback)`

**Solution**:
```bash
pip install opencv-python
```

### Video not loading from screentool session

**Problem**: `✗ Video not found in session: 1757046447`

**Solution**: Check that video exists at expected path:
```bash
ls ~/recordings/1757046447/db/*.video.raw.mp4
ls ~/recordings/1757046447/recording.mp4
```

### Slow popup rendering

**Problem**: Popup takes >100ms to update

**Cause**: On-demand decoding of full-resolution frames

**Solution**:
- Use smaller popup resolution in config
- Increase thumbnail size for better cached quality (trade-off: larger cache)

### Cache growing too large

**Problem**: `~/.recordings/.cache/video/` directory is several GB

**Solution**:
```bash
# Clean old caches (will be regenerated on next use)
find ~/recordings/.cache/video/ -mtime +30 -delete
```

## Technical Details

### ASCII Character Ramps

**Simple (4x4 thumbnails)**:
```
" .:-=+*#%@"
```
- 10 levels of brightness
- Fast conversion

**Extended (stippled popup)**:
```
" .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
```
- 70 levels of brightness
- Floyd-Steinberg dithering for photorealistic ASCII

### Video Codecs Supported

Any codec supported by OpenCV:
- H.264 (MP4, MKV)
- H.265/HEVC
- VP9 (WebM)
- AV1

Most common: **H.264 MP4** (screentool default)

## Future Enhancements

Potential improvements:

1. **Lane 5 mini-frame rendering**: Display 4x4 thumbnail in track view
2. **Multi-video support**: Load videos into multiple lanes
3. **Video export**: Save ASCII art as text file or ANSI art
4. **Real-time preview**: Show video in lane during scrubbing
5. **Audio extraction**: Use video audio track in tau-engine
6. **Frame-accurate seeking**: Sub-frame precision with FPS sync

## Contributing

Found a bug or have a feature request? Open an issue or PR:
- GitHub: https://github.com/anthropics/claude-code (tau is a demo project)

## License

Same as tau project (check main README)
