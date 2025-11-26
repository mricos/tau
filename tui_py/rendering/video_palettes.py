"""
ASCII palettes for video rendering.

Provides 4 palette options:
1. simple - Basic 10-character ramp (fastest)
2. extended - 70-character ramp with good detail
3. braille - UTF-8 Braille patterns (2x4 subpixel resolution)
4. blocks - UTF-8 block elements (best contrast)
"""

from typing import List, Tuple
import numpy as np


class VideoPalette:
    """Base class for video ASCII palettes."""

    name: str = "base"
    chars: str = " "

    @classmethod
    def get_char(cls, brightness: int) -> str:
        """
        Get character for brightness value (0-255).

        Args:
            brightness: Grayscale value 0-255

        Returns:
            ASCII character
        """
        idx = int(brightness / 255 * (len(cls.chars) - 1))
        idx = max(0, min(len(cls.chars) - 1, idx))
        return cls.chars[idx]

    @classmethod
    def supports_subpixel(cls) -> bool:
        """Whether this palette supports subpixel rendering."""
        return False


class SimplePalette(VideoPalette):
    """Simple 10-character ASCII ramp (dark to light)."""

    name = "simple"
    chars = " .:-=+*#%@"


class ExtendedPalette(VideoPalette):
    """Extended 70-character ASCII ramp for photorealistic rendering."""

    name = "extended"
    chars = " .'`^\",:;Il!i><~+_-?][}{1)(|/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


class BraillePalette(VideoPalette):
    """
    UTF-8 Braille patterns for 2x4 subpixel resolution.

    Braille Unicode block: U+2800 to U+28FF
    Each character represents 2x4 grid of pixels using 8 dots.

    Dot numbering:
    1 4
    2 5
    3 6
    7 8
    """

    name = "braille"

    # Braille base character
    BRAILLE_BASE = 0x2800

    # Dot positions (bit values)
    DOTS = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80]

    @classmethod
    def supports_subpixel(cls) -> bool:
        return True

    @classmethod
    def pixels_to_braille(cls, pixels: np.ndarray) -> str:
        """
        Convert 2x4 pixel block to Braille character.

        Args:
            pixels: 2x4 numpy array of brightness values (0-255)

        Returns:
            Braille character
        """
        # Threshold pixels (binary)
        threshold = 128
        dots_on = pixels > threshold

        # Map to Braille dots (specific layout)
        # Left column: dots 1,2,3,7 (rows 0-3)
        # Right column: dots 4,5,6,8 (rows 0-3)
        braille_value = cls.BRAILLE_BASE

        if pixels.shape != (4, 2):
            # Fallback for wrong shape
            return chr(cls.BRAILLE_BASE)

        # Left column (dots 1,2,3,7)
        if dots_on[0, 0]: braille_value += cls.DOTS[0]  # dot 1
        if dots_on[1, 0]: braille_value += cls.DOTS[1]  # dot 2
        if dots_on[2, 0]: braille_value += cls.DOTS[2]  # dot 3
        if dots_on[3, 0]: braille_value += cls.DOTS[6]  # dot 7

        # Right column (dots 4,5,6,8)
        if dots_on[0, 1]: braille_value += cls.DOTS[3]  # dot 4
        if dots_on[1, 1]: braille_value += cls.DOTS[4]  # dot 5
        if dots_on[2, 1]: braille_value += cls.DOTS[5]  # dot 6
        if dots_on[3, 1]: braille_value += cls.DOTS[7]  # dot 8

        return chr(braille_value)

    @classmethod
    def render_frame(cls, frame: np.ndarray, width: int, height: int) -> List[str]:
        """
        Render frame using Braille subpixel resolution.

        Args:
            frame: Grayscale frame (H x W)
            width: Target character width
            height: Target character height

        Returns:
            List of Braille character lines
        """
        import cv2

        # Each Braille char represents 2x4 pixels
        pixel_height = height * 4
        pixel_width = width * 2

        # Resize frame to pixel resolution
        resized = cv2.resize(frame, (pixel_width, pixel_height))

        # Convert to Braille characters
        lines = []
        for y in range(0, pixel_height, 4):
            line = []
            for x in range(0, pixel_width, 2):
                # Extract 2x4 block
                block = resized[y:y+4, x:x+2]

                # Handle edge cases
                if block.shape[0] < 4 or block.shape[1] < 2:
                    # Pad with zeros
                    padded = np.zeros((4, 2), dtype=np.uint8)
                    padded[:block.shape[0], :block.shape[1]] = block
                    block = padded

                # Convert to Braille
                braille_char = cls.pixels_to_braille(block)
                line.append(braille_char)

            lines.append(''.join(line))

        return lines


class BlocksPalette(VideoPalette):
    """
    UTF-8 block elements for high-contrast rendering.

    Uses Unicode block drawing characters:
    - Full blocks, half blocks, quarter blocks
    - Shaded blocks for gradients
    """

    name = "blocks"

    # Block characters ordered by density (light to dark)
    chars = " ░▒▓█"

    # Alternative: use fractional blocks for smoother gradients
    # chars = " ▁▂▃▄▅▆▇█"  # vertical eighths
    # chars = " ▏▎▍▌▋▊▉█"  # horizontal eighths

    @classmethod
    def get_char(cls, brightness: int) -> str:
        """Get block character for brightness."""
        idx = int(brightness / 255 * (len(cls.chars) - 1))
        idx = max(0, min(len(cls.chars) - 1, idx))
        return cls.chars[idx]


# Palette registry
PALETTES = {
    "simple": SimplePalette,
    "extended": ExtendedPalette,
    "braille": BraillePalette,
    "blocks": BlocksPalette,
}


def get_palette(name: str) -> VideoPalette:
    """
    Get palette by name.

    Args:
        name: Palette name (simple, extended, braille, blocks)

    Returns:
        Palette class

    Raises:
        ValueError: If palette name is invalid
    """
    if name not in PALETTES:
        raise ValueError(f"Unknown palette: {name}. Available: {', '.join(PALETTES.keys())}")
    return PALETTES[name]


def apply_brightness_contrast(frame: np.ndarray, brightness: float, contrast: float) -> np.ndarray:
    """
    Apply brightness and contrast adjustments to frame.

    Args:
        frame: Grayscale frame (0-255)
        brightness: Brightness offset (-1.0 to 1.0, maps to -255 to +255)
        contrast: Contrast multiplier (0.1 to 3.0)

    Returns:
        Adjusted frame (clipped to 0-255)
    """
    # Convert to float for processing
    adjusted = frame.astype(np.float32)

    # Apply contrast (around midpoint 127.5)
    adjusted = (adjusted - 127.5) * contrast + 127.5

    # Apply brightness
    adjusted = adjusted + (brightness * 255)

    # Clip to valid range
    adjusted = np.clip(adjusted, 0, 255)

    return adjusted.astype(np.uint8)


def frame_to_ascii(
    frame: np.ndarray,
    width: int,
    height: int,
    palette: str = "simple",
    brightness: float = 0.0,
    contrast: float = 1.0,
    dither: bool = False
) -> List[str]:
    """
    Convert video frame to ASCII art with configurable palette and adjustments.

    Args:
        frame: OpenCV frame (BGR or grayscale)
        width: Target character width
        height: Target character height
        palette: Palette name (simple, extended, braille, blocks)
        brightness: Brightness adjustment (-1.0 to 1.0)
        contrast: Contrast multiplier (0.1 to 3.0)
        dither: Apply Floyd-Steinberg dithering (extended palette only)

    Returns:
        List of ASCII art lines
    """
    import cv2

    # Convert to grayscale if needed
    if len(frame.shape) == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    else:
        gray = frame.copy()

    # Apply brightness/contrast adjustments
    if brightness != 0.0 or contrast != 1.0:
        gray = apply_brightness_contrast(gray, brightness, contrast)

    # Get palette
    palette_cls = get_palette(palette)

    # Braille uses subpixel rendering
    if palette_cls.supports_subpixel():
        return palette_cls.render_frame(gray, width, height)

    # Resize to target resolution
    resized = cv2.resize(gray, (width, height))

    # Dithering for extended palette
    if dither and palette == "extended":
        return _frame_to_ascii_dithered(resized, palette_cls)

    # Simple conversion
    lines = []
    for row in resized:
        line = ''.join(palette_cls.get_char(val) for val in row)
        lines.append(line)

    return lines


def _frame_to_ascii_dithered(frame: np.ndarray, palette_cls: VideoPalette) -> List[str]:
    """
    Convert frame to ASCII with Floyd-Steinberg dithering.

    Args:
        frame: Grayscale frame (already resized)
        palette_cls: Palette class to use

    Returns:
        List of ASCII lines
    """
    height, width = frame.shape
    img_float = frame.astype(np.float32)

    ascii_art = []
    for y in range(height):
        row = []
        for x in range(width):
            old_val = img_float[y, x]

            # Get character for this pixel
            char = palette_cls.get_char(int(old_val))
            row.append(char)

            # Calculate quantization error
            # Map char back to brightness value
            char_idx = palette_cls.chars.index(char)
            new_val = (char_idx / (len(palette_cls.chars) - 1)) * 255
            error = old_val - new_val

            # Diffuse error to neighbors (Floyd-Steinberg)
            if x + 1 < width:
                img_float[y, x + 1] += error * 7 / 16
            if y + 1 < height:
                if x > 0:
                    img_float[y + 1, x - 1] += error * 3 / 16
                img_float[y + 1, x] += error * 5 / 16
                if x + 1 < width:
                    img_float[y + 1, x + 1] += error * 1 / 16

        ascii_art.append(''.join(row))

    return ascii_art
