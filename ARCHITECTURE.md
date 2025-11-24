# ASCII Scope SNN - Architecture Design

## Core Concepts

### Lanes (Visual Display)
- **Lanes** are visual display regions on screen
- Each lane has: position, height, visibility, expanded state, color
- Lanes contain a **clip_stack** (multiple clips can be layered)
- Lanes have a **state machine** for keyboard interactions

### Clips (Content)
- **Clips** are content that live inside lanes
- Two fundamental types:
  - **Timebased Clips**: Move with transport (audio, waveforms)
  - **Static Clips**: Fixed content (logs, CLI, preamble, events)

### Time vs. Static
- **Timebased**: Content scrolls/moves with transport position
- **Static/Preamble**: Content stays fixed (like film leader before content)

## Class Hierarchy

```
Clip (abstract base)
├── TimebasedClip (audio waveforms, moving data)
├── StaticClip (fixed text, preamble)
└── EventsClip (timestamped events with filtering and coloring)

Lane
├── clip_stack: List[Clip]
├── state_machine: LaneStateMachine
├── visual properties: visible, expanded, height, color
└── keyboard interaction state

Event
├── timestamp: float (seconds since session start)
├── level: str (info, warn, error, debug)
├── message: str
├── metadata: dict
└── computed: delta_time_ms, delta_time_sd
```

## Events Lane Features

### Color Coding
- **By Level**: info=white, warn=yellow, error=red, debug=dim
- **By Delta Time**: Inter-event timing visualization
  - Fast events: green/cyan (< 100ms)
  - Medium: yellow (100-1000ms)
  - Slow: red (> 1000ms)
- **Delta Time SD**: Show timing consistency via color intensity

### Filtering
- Filter by level: `:events filter level=error,warn`
- Filter by message pattern: `:events filter msg=kernel`
- Filter by time range: `:events filter time=2.5-5.0`
- Clear filter: `:events filter clear`

### Time Format
- Absolute: `[12.345s]`
- Relative: `[+0.123s]`
- Delta: `[Δ123ms]`
- Timestamp: `[14:35:12.345]`
- Configure: `:events time_format delta`

## Lane State Machine

### States
- **NORMAL**: Default state, accepts all interactions
- **SELECTED**: Lane recently selected (highlight)
- **EDITING**: Lane content being edited (future)
- **PLAYING**: Lane actively playing/rendering (for timebased)
- **HIDDEN**: Lane not visible
- **PINNED**: Lane locked in position

### Transitions
- DOWN → check for double-click → SELECTED
- UP-QUICK → toggle visibility → NORMAL/HIDDEN
- UP-MEDIUM → toggle expanded → NORMAL
- Double-click → SELECTED + expanded

## Implementation Plan

1. **Phase 1**: Create Clip base class and subclasses
2. **Phase 2**: Implement EventsClip with Event class
3. **Phase 3**: Add filtering and time format to EventsClip
4. **Phase 4**: Create LaneStateMachine
5. **Phase 5**: Refactor Lane to use clip_stack
6. **Phase 6**: Update rendering pipeline
7. **Phase 7**: Add CLI commands for event management

## Video Playback System

### Architecture

Tau supports MP4 video playback with ASCII art rendering:

- **VideoLane**: Video content with pre-rendered thumbnail caching
- **VideoPopup**: Full-screen overlay with stippled ASCII art
- **Thumbnail Strip**: Pre-processed frames sampled at configurable interval (default 1 fps)
- **Cache System**: Persistent pickle cache in `$CONTEXT_DIR/.cache/video/`

### Integration

- **Screentool TRS Pattern**: Shared `~/recordings/` directory for A/V sessions
- **Context Directory**: `--context-dir` flag for cache location (default `~/recordings/`)
- **Feature Detection**: Graceful degradation without `opencv-python`
- **Opt-out Design**: Enabled by default, disable with `--no-video`

### Data Flow

```
Video File → VideoLane.load()
           ↓
    Sample frames @ interval (e.g., 1 fps)
           ↓
    Convert to 4x4 ASCII thumbnails
           ↓
    Cache: video_{name}_{mtime}_{size}_{interval}.pkl
           ↓
    Runtime: Fast lookup (no decoding)
           ↓
    Render: Mini-frame (4x4) or Popup (80x40 stippled)
```

### Commands

- `video_load <path>` - Load video file
- `video_load_session <epoch>` - Load from screentool session
- `video_toggle` (Shift+V) - Toggle popup viewer
- `video_info` - Show video metadata
- `video_resample` - Regenerate cache with new settings

See `VIDEO_PLAYBACK.md` for full documentation.

## Benefits

- **Separation of Concerns**: Visual (lanes) vs. Content (clips)
- **Flexibility**: Multiple clips per lane, reusable clips
- **Preamble Support**: Static clips for context before timebased content
- **Rich Events**: Color-coded, filterable event logging
- **State Management**: Clean keyboard interaction via state machine
- **Video Integration**: Lean, cached, screentool-compatible video playback
