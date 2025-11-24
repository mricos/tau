# Migration Guide: Lanes/Clips Architecture

## Overview

The new architecture separates **visual containers (lanes)** from **content (clips)**.

### Old Architecture
```python
Lane {
    lane_type: "timebased" | "pinned"
    channel_id: int           # Only for timebased
    content: List[str]        # Only for pinned
}
```

### New Architecture
```python
Lane {
    id, name, visible, expanded
    clip_stack: List[Clip]      # Can have multiple clips
    state_machine: LaneStateMachine
}

Clip (abstract)
├── TimebasedClip(channel_id, data_buffer)
├── StaticClip(lines)
└── EventsClip(events, filtering, color-coding)
```

## Key Changes

### 1. Lanes are Visual, Clips are Content
- **Lanes** = screen regions with position, size, visibility
- **Clips** = actual content (audio, text, events)

### 2. Multiple Clips Per Lane
A lane can have a **clip_stack**:
```python
lane.clip_stack = [
    StaticClip("preamble", ["Project: MyProject", "Author: Me"]),
    TimebasedClip("audio", channel_id=0, data_buffer=data),
    EventsClip("events")
]
```

### 3. Timebased vs. Static
- **Timebased clips**: Move with transport (audio waveforms)
- **Static clips**: Fixed content like preamble, notes, CLI output

### 4. State Machine for Interactions
Lanes have state machines that manage keyboard interactions:
```python
lane.state_machine.handle_event(LaneEvent.DOUBLE_CLICK)
# → Lane transitions to SELECTED state
```

## Migration Steps

### Phase 1: Current Code (Working)
Current implementation continues to work with backward compatibility:
```python
# Old way (still works)
lane = Lane(id=0, name="audio", lane_type="timebased", channel_id=0)
```

### Phase 2: Gradual Migration
Add new clip system alongside old system:
```python
# New way
lane = Lane(id=0, name="audio")
lane.clip_stack = [TimebasedClip("audio_ch0", channel_id=0, data_buffer=data)]
lane.state_machine = LaneStateMachine(lane_id=0)
```

### Phase 3: Full Migration
Replace old rendering with clip-based rendering:
```python
# Old rendering
if lane.lane_type == "timebased":
    render_waveform(...)
elif lane.lane_type == "pinned":
    render_pinned(...)

# New rendering
for clip in lane.clip_stack:
    lines = clip.render(layout, state)
    # Render lines to screen
```

## Using EventsClip

### Creating an Events Lane
```python
from clips import EventsClip, EventLevel, TimeFormat

events_clip = EventsClip("system_events")
events_clip.set_time_format(TimeFormat.DELTA)

# Add to a lane
lane = Lane(id=7, name="events")
lane.clip_stack = [events_clip]
```

### Adding Events
```python
# From code
events_clip.add_event(EventLevel.INFO, "Application started")
events_clip.add_event(EventLevel.WARN, "Buffer underrun detected")

# From CLI
:events_add info "Transport position changed"
:event warn "Kernel parameters out of range"  # Alias
```

### Filtering Events
```python
# By level
:events_filter level error,warn

# By message pattern
:events_filter msg kernel

# By time range
:events_filter time 2.5-10.0

# Clear filter
:events_filter clear
```

### Time Formats
```python
# Absolute time
:events_time_format absolute
# Output: [12.345s] [INFO] Application started

# Delta time (inter-event timing)
:events_time_format delta
# Output: [Δ123ms] [INFO] Application started

# Relative time
:events_time_format relative
# Output: [+0.123s] [INFO] Application started

# Wall clock time
:events_time_format timestamp
# Output: [14:35:12.345] [INFO] Application started
```

### Color Coding

#### By Level
- **DEBUG**: Dim gray
- **INFO**: White
- **WARN**: Yellow
- **ERROR**: Red

#### By Delta Time (Inter-Event Timing)
- **< 50ms**: Green (very fast)
- **50-100ms**: Cyan (fast)
- **100-500ms**: Yellow (medium)
- **500-1000ms**: Magenta (slow)
- **> 1000ms**: Red (very slow)

## Using State Machine

### Lane States
```python
from lane_state import LaneState, LaneEvent

# Check state
if lane.state_machine.current_state == LaneState.SELECTED:
    # Draw highlight border
    pass

# Handle keyboard event
lane.state_machine.handle_event(LaneEvent.DOUBLE_CLICK)

# Get visual attributes
attrs = lane.state_machine.get_visual_attributes()
# Returns: {'highlight': True, 'border': True, ...}
```

### State Transitions
```
NORMAL → KEY_UP_QUICK → HIDDEN (toggle visibility)
NORMAL → KEY_UP_MEDIUM → SELECTED (highlight)
NORMAL → DOUBLE_CLICK → SELECTED (highlight + expand)
SELECTED → TIMEOUT(2s) → NORMAL
HIDDEN → KEY_UP_QUICK → NORMAL (show again)
```

## Example: Complete Lane Setup

```python
from clips import TimebasedClip, StaticClip, EventsClip, EventLevel
from lane_state import LaneStateMachine, LaneEvent

# Create lane
lane = Lane(id=0, name="audio_with_context")

# Add preamble (static)
preamble = StaticClip("preamble", [
    "═" * 40,
    "Project: Breakbeat Analysis",
    "BPM: 174",
    "Key: A minor",
    "═" * 40,
])

# Add audio (timebased)
audio = TimebasedClip("audio", channel_id=0, data_buffer=data, gain=1.0)

# Add events (static with timestamps)
events = EventsClip("processing_log")
events.add_event(EventLevel.INFO, "File loaded: breakbeat.wav")
events.add_event(EventLevel.INFO, "Kernel params: tau_a=0.01, tau_r=0.05")

# Assemble clip stack
lane.clip_stack = [preamble, audio, events]

# Add state machine
lane.state_machine = LaneStateMachine(lane_id=0)

# Handle interaction
lane.state_machine.handle_event(LaneEvent.DOUBLE_CLICK)
# → Lane is now SELECTED and expanded
```

## Benefits

1. **Separation of Concerns**: Visual vs. Content
2. **Reusable Clips**: Same clip can be used in multiple lanes
3. **Flexible Composition**: Mix static and timebased content
4. **Rich Events**: Color-coded, filterable event logging
5. **State Management**: Clean keyboard interactions
6. **Preamble Support**: Context before timebased content
7. **Future Extensions**: Easy to add new clip types

## CLI Commands Summary

### Events Commands
```bash
:events_add <level> <message>    # Add event
:event <level> <message>         # Alias
:log <level> <message>           # Alias

:events_filter <type> <value>    # Filter events
:ef level error,warn             # Filter by level
:ef msg kernel                   # Filter by message
:ef time 2.5-10.0                # Filter by time range
:ef clear                        # Clear filter

:events_time_format <format>     # Set time format
:etf delta                       # Use delta time

:events_stats                    # Show statistics
:es                              # Alias

:events_clear                    # Clear all events
:ec                              # Alias
```

### Keypress Tuning (Already Implemented)
```bash
:press_double_click <ms>         # Double-click window
:press_up_quick <ms>             # Quick tap max
:press_up_medium <ms>            # Medium hold
:press_up_long <ms>              # Long hold
:press_info                      # Show settings
```

## Next Steps

1. **Phase 1 Complete**: Core classes created (clips.py, lane_state.py)
2. **Phase 2 Complete**: CLI commands added
3. **Phase 3 Next**: Integrate EventsClip into main.py
4. **Phase 4 Next**: Add clip rendering to rendering pipeline
5. **Phase 5 Next**: Migrate existing lanes to use clips
6. **Phase 6 Future**: Add EDITING state for inline editing
7. **Phase 7 Future**: Add clip layering/compositing
