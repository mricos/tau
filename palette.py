"""
Color palette system for ASCII Scope SNN.
Supports reading TDS theme format (bash scripts with hex color definitions).
"""

import re
import curses
from pathlib import Path
from typing import Dict, Optional


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """
    Convert hex color to RGB tuple (0-255 range).

    Args:
        hex_color: Hex color string like "#fef3c7" or "fef3c7"

    Returns:
        Tuple of (r, g, b) values in 0-255 range
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_curses(r: int, g: int, b: int) -> tuple[int, int, int]:
    """
    Convert RGB (0-255) to curses color values (0-1000).

    Args:
        r, g, b: RGB values in 0-255 range

    Returns:
        Tuple of (r, g, b) values in 0-1000 range for curses
    """
    return (
        int(r * 1000 / 255),
        int(g * 1000 / 255),
        int(b * 1000 / 255)
    )


def parse_tds_theme(theme_path: str) -> Dict[str, str]:
    """
    Parse TDS theme bash script and extract color definitions.

    Args:
        theme_path: Path to TDS theme file

    Returns:
        Dictionary mapping variable names to hex colors
    """
    colors = {}

    try:
        with open(theme_path, 'r') as f:
            content = f.read()

        # Match lines like: PALETTE_PRIMARY_500="#f59e0b"
        # Allow spaces around = sign, handle numbers in var names
        pattern = r'^\s*([A-Z_0-9]+)\s*=\s*["\'](#[0-9a-fA-F]{6})["\']'

        for line in content.split('\n'):
            match = re.match(pattern, line)
            if match:
                var_name, hex_color = match.groups()
                colors[var_name] = hex_color

    except FileNotFoundError:
        pass  # Theme file not found, will use defaults

    return colors


class ColorPalette:
    """Manages application color palette with TDS theme support."""

    def __init__(self):
        self.colors: Dict[str, str] = {}
        self.theme_name = "default"

        # Data color indices for curses color pairs (1-8)
        self.COLOR_LANE_1 = 1
        self.COLOR_LANE_2 = 2
        self.COLOR_LANE_3 = 3
        self.COLOR_LANE_4 = 4
        self.COLOR_LANE_5 = 5
        self.COLOR_LANE_6 = 6
        self.COLOR_LANE_7 = 7
        self.COLOR_LANE_8 = 8

        # Status/UI color indices (9-12)
        self.COLOR_SUCCESS = 9   # Green - play button, success messages
        self.COLOR_WARNING = 10  # Orange/yellow - warnings
        self.COLOR_ERROR = 11    # Red - errors
        self.COLOR_INFO = 12     # Cyan/blue - info, hints

    def load_tds_theme(self, theme_path: str) -> bool:
        """
        Load colors from TDS theme file.

        Args:
            theme_path: Path to TDS theme bash script

        Returns:
            True if theme loaded successfully
        """
        colors = parse_tds_theme(theme_path)
        if colors:
            self.colors = colors
            self.theme_name = Path(theme_path).stem
            return True
        return False

    def get_hex(self, var_name: str, default: str = "#ffffff") -> str:
        """Get hex color by variable name."""
        return self.colors.get(var_name, default)

    def get_rgb(self, var_name: str, default: str = "#ffffff") -> tuple[int, int, int]:
        """Get RGB tuple (0-255) by variable name."""
        hex_color = self.get_hex(var_name, default)
        return hex_to_rgb(hex_color)

    def get_curses_rgb(self, var_name: str, default: str = "#ffffff") -> tuple[int, int, int]:
        """Get curses RGB tuple (0-1000) by variable name."""
        r, g, b = self.get_rgb(var_name, default)
        return rgb_to_curses(r, g, b)

    def apply_to_curses(self) -> bool:
        """
        Apply palette colors to curses color pairs (12 total).
        Requires curses.start_color() to have been called.

        12-Color System:
        - Pairs 1-8: Data colors (lanes/waveforms) from TDS theme palettes
        - Pairs 9-12: Status/UI colors from TDS theme state colors

        Data colors (1-8):
        - ENV: Lanes 1-2 (amber/primary)
        - MODE: Lanes 3-4 (orange/secondary)
        - VERBS: Lanes 5-6 (red/accent)
        - NOUNS: Lanes 7-8 (gray/neutral)

        Status colors (9-12):
        - SUCCESS: green
        - WARNING: orange/yellow
        - ERROR: red
        - INFO: cyan/blue

        Returns:
            True if colors were applied successfully
        """
        if not curses.has_colors() or not curses.can_change_color():
            return False

        try:
            # Map TDS theme to 12 color pairs
            palette_mapping = [
                # DATA COLORS (1-8) - Using lighter shades for visibility
                # ENV palette (amber/warm)
                ("PALETTE_PRIMARY_300", self.COLOR_LANE_1),    # Amber (bright)
                ("PALETTE_PRIMARY_400", self.COLOR_LANE_2),    # Rich amber

                # MODE palette (orange/structural)
                ("PALETTE_SECONDARY_300", self.COLOR_LANE_3),  # Orange (bright)
                ("PALETTE_SECONDARY_400", self.COLOR_LANE_4),  # Bright orange

                # VERBS palette (red/actions)
                ("PALETTE_ACCENT_300", self.COLOR_LANE_5),     # Red (bright)
                ("PALETTE_ACCENT_400", self.COLOR_LANE_6),     # Bright red

                # NOUNS palette (neutral warm)
                ("PALETTE_NEUTRAL_300", self.COLOR_LANE_7),    # Light warm gray
                ("PALETTE_NEUTRAL_400", self.COLOR_LANE_8),    # Medium light gray

                # STATUS/UI COLORS (9-12)
                ("PALETTE_SUCCESS", self.COLOR_SUCCESS),       # Green
                ("PALETTE_WARNING", self.COLOR_WARNING),       # Orange/yellow
                ("PALETTE_ERROR", self.COLOR_ERROR),           # Red
                ("PALETTE_INFO", self.COLOR_INFO),             # Amber/info
            ]

            # Define dark-dark-gray background color (color slot 30)
            # RGB: 26, 26, 26 (very dark gray, not pure black)
            DARK_GRAY_SLOT = 30
            curses.init_color(DARK_GRAY_SLOT, 102, 102, 102)  # 26/255 * 1000 ≈ 102

            for var_name, color_idx in palette_mapping:
                if var_name in self.colors:
                    r, g, b = self.get_curses_rgb(var_name)
                    # Use color slots 9-20 for custom colors (avoid conflict with standard 0-7)
                    curses.init_color(color_idx + 8, r, g, b)
                    curses.init_pair(color_idx, color_idx + 8, DARK_GRAY_SLOT)

            return True

        except Exception:
            return False  # Terminal doesn't support color changes

    def get_default_colors(self) -> Dict[int, tuple[int, int, int]]:
        """
        Get default color scheme (fallback if terminal doesn't support color changes).

        Returns:
            Dictionary mapping color pair indices to RGB tuples (0-1000)
        """
        defaults = {
            self.COLOR_LANE_1: (1000, 647, 0),    # Orange
            self.COLOR_LANE_2: (0, 1000, 0),      # Green
            self.COLOR_LANE_3: (1000, 0, 0),      # Red
            self.COLOR_LANE_4: (0, 0, 1000),      # Blue
            self.COLOR_LANE_5: (1000, 1000, 0),   # Yellow
            self.COLOR_LANE_6: (1000, 0, 1000),   # Magenta
            self.COLOR_LANE_7: (0, 1000, 1000),   # Cyan
            self.COLOR_LANE_8: (647, 647, 647),   # Gray
        }
        return defaults


def find_tds_theme(theme_name: str = "warm") -> Optional[str]:
    """
    Search for TDS theme file in common locations.

    Args:
        theme_name: Name of theme (e.g., "warm")

    Returns:
        Path to theme file if found, None otherwise
    """
    # Common TDS theme locations
    search_paths = [
        Path.home() / "src" / "devops" / "tetra" / "bash" / "tds" / "themes" / f"{theme_name}.sh",
        Path.home() / "tetra" / "bash" / "tds" / "themes" / f"{theme_name}.sh",
        Path.home() / "tetra" / "tds" / "themes" / f"{theme_name}.sh",
        Path.home() / ".tds" / "themes" / f"{theme_name}.sh",
        Path("/usr/local/share/tds/themes") / f"{theme_name}.sh",
        Path("~/.config/tds/themes").expanduser() / f"{theme_name}.sh",
    ]

    for path in search_paths:
        if path.exists():
            return str(path)

    return None
