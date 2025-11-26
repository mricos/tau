"""
Video command definitions for tau.

Commands for controlling video playback, palettes, and adjustments.
"""

from tau_lib.core.commands_api import (
    CommandDef, CommandParam, ParamType, CommandCategory,
    COMMAND_REGISTRY as registry
)

# Lazy import palettes to avoid numpy dependency when video is disabled
PALETTES = None


def _get_palettes():
    """Lazily import PALETTES dict."""
    global PALETTES
    if PALETTES is None:
        try:
            from tui_py.rendering.video_palettes import PALETTES as _PALETTES
            PALETTES = _PALETTES
        except ImportError:
            PALETTES = {"simple": None}  # Fallback
    return PALETTES


def register_video_commands(app_state):
    """Register video display commands (palettes, brightness, contrast)."""

    # ========== VIDEO POPUP COMMANDS ==========
    # Note: video_toggle is registered in semantic_name_mapping_commands.py

    registry.register(CommandDef(
        name="video_close",
        category=CommandCategory.VIEW,
        description_short="Close video popup",
        aliases=["vc"],
        key_binding="V",
        handler=lambda: _close_video_popup(app_state)
    ))

    # ========== PALETTE COMMANDS ==========

    registry.register(CommandDef(
        name="video_palette",
        category=CommandCategory.VIEW,
        description_short="Set video palette",
        description_long="Set ASCII palette for video rendering. Available: simple, extended, braille, blocks",
        aliases=["vp"],
        params=[
            CommandParam("palette", ParamType.STRING, "Palette name (simple, extended, braille, blocks)")
        ],
        handler=lambda palette: _set_video_palette(app_state, palette)
    ))

    registry.register(CommandDef(
        name="video_palette_next",
        category=CommandCategory.VIEW,
        description_short="Next video palette",
        aliases=["vpn"],
        key_binding="p",
        handler=lambda: _cycle_video_palette(app_state, 1)
    ))

    registry.register(CommandDef(
        name="video_palette_prev",
        category=CommandCategory.VIEW,
        description_short="Previous video palette",
        aliases=["vpp"],
        key_binding="P",
        handler=lambda: _cycle_video_palette(app_state, -1)
    ))

    # ========== BRIGHTNESS/CONTRAST COMMANDS ==========

    registry.register(CommandDef(
        name="video_brightness_up",
        category=CommandCategory.VIEW,
        description_short="Increase video brightness",
        aliases=["vbu"],
        key_binding="+",
        handler=lambda: _adjust_video_brightness(app_state, 0.1)
    ))

    registry.register(CommandDef(
        name="video_brightness_down",
        category=CommandCategory.VIEW,
        description_short="Decrease video brightness",
        aliases=["vbd"],
        key_binding="-",
        handler=lambda: _adjust_video_brightness(app_state, -0.1)
    ))

    registry.register(CommandDef(
        name="video_brightness",
        category=CommandCategory.VIEW,
        description_short="Set video brightness",
        description_long="Set brightness adjustment (-1.0 to 1.0)",
        aliases=["vb"],
        params=[
            CommandParam("value", ParamType.FLOAT, "Brightness value (-1.0 to 1.0)")
        ],
        handler=lambda value: _set_video_brightness(app_state, value)
    ))

    registry.register(CommandDef(
        name="video_contrast_up",
        category=CommandCategory.VIEW,
        description_short="Increase video contrast",
        aliases=["vcu"],
        key_binding=">",
        handler=lambda: _adjust_video_contrast(app_state, 0.1)
    ))

    registry.register(CommandDef(
        name="video_contrast_down",
        category=CommandCategory.VIEW,
        description_short="Decrease video contrast",
        aliases=["vcd"],
        key_binding="<",
        handler=lambda: _adjust_video_contrast(app_state, -0.1)
    ))

    registry.register(CommandDef(
        name="video_contrast",
        category=CommandCategory.VIEW,
        description_short="Set video contrast",
        description_long="Set contrast multiplier (0.1 to 3.0)",
        aliases=["vct"],
        params=[
            CommandParam("value", ParamType.FLOAT, "Contrast value (0.1 to 3.0)")
        ],
        handler=lambda value: _set_video_contrast(app_state, value)
    ))

    registry.register(CommandDef(
        name="video_reset",
        category=CommandCategory.VIEW,
        description_short="Reset video settings",
        description_long="Reset brightness, contrast, and palette to defaults",
        aliases=["vr"],
        key_binding="R",
        handler=lambda: _reset_video_settings(app_state)
    ))

    # Note: video_info is registered in semantic_name_mapping_commands.py


# ========== HELPER FUNCTIONS ==========

def _toggle_video_popup(app_state):
    """Toggle video popup visibility."""
    if app_state.video_popup:
        app_state.video_popup.toggle()
        return f"Video popup {'opened' if app_state.video_popup.visible else 'closed'}"
    return "Video not available"


def _close_video_popup(app_state):
    """Close video popup."""
    if app_state.video_popup:
        app_state.video_popup.visible = False
        return "Video popup closed"
    return "Video not available"


def _get_video_state(app_state):
    """Get or create video display state."""
    if not hasattr(app_state, '_video_display'):
        app_state._video_display = {
            'palette': 'simple',
            'brightness': 0.0,
            'contrast': 1.0
        }
    return app_state._video_display


def _set_video_palette(app_state, palette: str):
    """Set video palette."""
    palettes = _get_palettes()
    palette = palette.lower()
    if palette not in palettes:
        return f"Unknown palette: {palette}. Available: {', '.join(palettes.keys())}"

    video_state = _get_video_state(app_state)
    video_state['palette'] = palette
    return f"Video palette: {palette}"


def _cycle_video_palette(app_state, direction: int):
    """Cycle through video palettes."""
    palettes = _get_palettes()
    palette_names = list(palettes.keys())
    video_state = _get_video_state(app_state)
    current = video_state['palette']

    if current in palette_names:
        idx = palette_names.index(current)
        idx = (idx + direction) % len(palette_names)
        new_palette = palette_names[idx]
    else:
        new_palette = palette_names[0]

    video_state['palette'] = new_palette
    return f"Video palette: {new_palette}"


def _adjust_video_brightness(app_state, delta: float):
    """Adjust video brightness."""
    video_state = _get_video_state(app_state)
    new_val = max(-1.0, min(1.0, video_state['brightness'] + delta))
    video_state['brightness'] = new_val
    return f"Brightness: {new_val:+.1f}"


def _set_video_brightness(app_state, value: float):
    """Set video brightness."""
    video_state = _get_video_state(app_state)
    value = max(-1.0, min(1.0, value))
    video_state['brightness'] = value
    return f"Brightness: {value:+.1f}"


def _adjust_video_contrast(app_state, delta: float):
    """Adjust video contrast."""
    video_state = _get_video_state(app_state)
    new_val = max(0.1, min(3.0, video_state['contrast'] + delta))
    video_state['contrast'] = new_val
    return f"Contrast: {new_val:.1f}"


def _set_video_contrast(app_state, value: float):
    """Set video contrast."""
    video_state = _get_video_state(app_state)
    value = max(0.1, min(3.0, value))
    video_state['contrast'] = value
    return f"Contrast: {value:.1f}"


def _reset_video_settings(app_state):
    """Reset video settings to defaults."""
    video_state = _get_video_state(app_state)
    video_state['palette'] = 'simple'
    video_state['brightness'] = 0.0
    video_state['contrast'] = 1.0
    return "Video settings reset to defaults"


def _show_video_info(app_state):
    """Show video information."""
    if not app_state.features.video_available:
        return "Video not available (opencv not installed)"

    if not app_state.features.video_enabled:
        return "Video disabled (--no-video)"

    # Check for video lanes
    if app_state.lanes:
        for lane in app_state.lanes.lanes:
            if hasattr(lane, 'get_info'):
                info = lane.get_info()
                if info:
                    return "\n".join(f"{k}: {v}" for k, v in info.items())

    return "No video loaded"
