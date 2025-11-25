"""
Configuration management for tau.
Handles TOML serialization and deserialization of application state.
Config location: ~/.config/tau/config.toml
"""

import os
from typing import Optional

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python

try:
    import tomli_w as toml_writer
except ImportError:
    # Fallback - manual TOML writing
    toml_writer = None

from tau_lib.core.state import AppState, KernelParams, Marker


def save_config(state: AppState, path: str):
    """Save application state to TOML file."""

    config = {
        'kernel': {
            'tau_a': state.kernel.tau_a,
            'tau_r': state.kernel.tau_r,
            'threshold': state.kernel.threshold,
            'refractory': state.kernel.refractory,
            'fs': state.kernel.fs,
        },
        'transport': {
            'position': state.transport.position,
            'span': state.transport.span,
            'playing': state.transport.playing,
        },
        'display': {
            'mode': state.display.mode,
        },
        'video': {
            'enabled': state.features.video_enabled,
            'sampling_interval': state.features.video_sampling_interval,
            'thumbnail_size': state.features.video_thumbnail_size,
            'popup_resolution': list(state.features.video_popup_resolution),
        },
        'files': {},
    }

    if state.audio_input:
        config['files']['audio_input'] = state.audio_input
    if state.data_file:
        config['files']['data_file'] = state.data_file
    if state.context_dir:
        config['files']['context_dir'] = str(state.context_dir)

    # Lanes
    if state.lanes:
        config['lanes'] = []
        for lane in state.lanes.lanes:
            config['lanes'].append({
                'id': lane.id,
                'name': lane.name,
                'display_mode': int(lane.display_mode),
                'gain': lane.gain,
            })

    # Markers
    config['markers'] = []
    for m in state.markers.all():
        config['markers'].append({
            'time': m.time,
            'label': m.label,
            'color': m.color,
        })

    # Write to file
    if toml_writer:
        with open(path, 'wb') as f:
            toml_writer.dump(config, f)
    else:
        # Manual TOML writing (simple format)
        with open(path, 'w') as f:
            _write_toml_manual(config, f)


def load_config(path: str) -> Optional[AppState]:
    """Load application state from TOML file."""

    if not os.path.exists(path):
        return None

    with open(path, 'rb') as f:
        config = tomllib.load(f)

    state = AppState()

    # Load kernel params
    if 'kernel' in config:
        k = config['kernel']
        state.kernel = KernelParams(
            tau_a=k.get('tau_a', 0.001),
            tau_r=k.get('tau_r', 0.005),
            threshold=k.get('threshold', 3.0),
            refractory=k.get('refractory', 0.015),
            fs=k.get('fs', 48000),
        )

    # Load transport
    if 'transport' in config:
        t = config['transport']
        state.transport.position = t.get('position', 0.0)
        state.transport.span = t.get('span', 1.0)
        state.transport.playing = t.get('playing', False)

    # Load display
    if 'display' in config:
        d = config['display']
        state.display.mode = d.get('mode', 'envelope')

    # Load video settings
    if 'video' in config:
        v = config['video']
        state.features.video_enabled = v.get('enabled', True)
        state.features.video_sampling_interval = v.get('sampling_interval', 1.0)
        state.features.video_thumbnail_size = v.get('thumbnail_size', 4)
        popup_res = v.get('popup_resolution', [80, 40])
        if isinstance(popup_res, list) and len(popup_res) == 2:
            state.features.video_popup_resolution = tuple(popup_res)

    # Load files
    if 'files' in config:
        from pathlib import Path
        f = config['files']
        state.audio_input = f.get('audio_input')
        state.data_file = f.get('data_file')
        if 'context_dir' in f:
            state.context_dir = Path(f['context_dir'])

    # Load lanes
    if 'lanes' in config and state.lanes:
        from tui_py.content.lanes import LaneDisplayMode
        for lane_config in config['lanes']:
            lane_id = lane_config.get('id')
            lane = state.lanes.get_lane(lane_id)
            if lane:
                lane.name = lane_config.get('name', lane.name)
                # Handle old format with visible/expanded or new format with display_mode
                if 'display_mode' in lane_config:
                    lane.display_mode = LaneDisplayMode(lane_config['display_mode'])
                else:
                    # Legacy support
                    visible = lane_config.get('visible', True)
                    expanded = lane_config.get('expanded', False)
                    if not visible:
                        lane.display_mode = LaneDisplayMode.HIDDEN
                    elif expanded:
                        lane.display_mode = LaneDisplayMode.FULL
                    else:
                        lane.display_mode = LaneDisplayMode.COMPACT
                lane.gain = lane_config.get('gain', lane.gain)

    # Load markers
    if 'markers' in config:
        for m_config in config['markers']:
            state.markers.add(
                time=m_config['time'],
                label=m_config['label'],
                color=m_config.get('color', 6)
            )

    return state


def _write_toml_manual(config: dict, f):
    """Manual TOML writer (simple format, no dependencies)."""
    def format_value(val):
        """Format a value for TOML."""
        if isinstance(val, str):
            return f'"{val}"'
        elif isinstance(val, bool):
            return str(val).lower()
        elif isinstance(val, list):
            # Format list as TOML array
            formatted_items = [format_value(item) for item in val]
            return '[' + ', '.join(formatted_items) + ']'
        else:
            return str(val)

    for section, values in config.items():
        if isinstance(values, dict):
            f.write(f"\n[{section}]\n")
            for key, val in values.items():
                f.write(f'{key} = {format_value(val)}\n')
        elif isinstance(values, list):
            for item in values:
                f.write(f"\n[[{section}]]\n")
                for key, val in item.items():
                    f.write(f'{key} = {format_value(val)}\n')


def get_default_config_path() -> str:
    """Get default config file path (~/.config/tau/config.toml)."""
    config_dir = os.path.expanduser("~/.config/tau")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "config.toml")
