"""
Scene compositor for fade transitions.

Manages layered rendering with opacity for smooth transitions.
Each layer is a render function that accepts (scr, h, w, opacity).
"""

import curses
from typing import Callable


class SceneCompositor:
    """
    Manages multiple scene layers for transitions.

    Layers are rendered back-to-front, each with their own opacity.
    The render functions are responsible for applying fade effects.
    """

    def __init__(self, height: int, width: int):
        self.height = height
        self.width = width
        self._layers: dict[str, Callable] = {}

    def set_layer_render(self, name: str, render_func: Callable):
        """Set the render function for a layer."""
        self._layers[name] = render_func

    def resize(self, height: int, width: int):
        """Update dimensions."""
        self.height = height
        self.width = width

    def composite(self, stdscr, layers: list[tuple[str, float]]):
        """
        Composite multiple scene layers onto screen.

        Args:
            stdscr: Main curses screen
            layers: List of (layer_name, opacity) tuples.
                   Rendered back-to-front (first = back, last = front)
        """
        stdscr.erase()

        for name, opacity in layers:
            if name not in self._layers:
                continue
            if opacity < 0.1:
                continue

            try:
                self._layers[name](stdscr, self.height, self.width, opacity)
            except curses.error:
                pass


# Helper function for opacity-based attribute selection
def opacity_to_attr(opacity: float, base_attr: int = 0) -> int:
    """
    Convert opacity to curses attributes.

    Args:
        opacity: 0.0-1.0
        base_attr: Base attributes to combine with

    Returns:
        Curses attribute value
    """
    if opacity < 0.3:
        return base_attr | curses.A_DIM
    elif opacity > 0.8:
        return base_attr | curses.A_BOLD
    else:
        return base_attr
