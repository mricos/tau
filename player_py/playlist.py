"""Playlist: ordered track list with navigation and repeat modes."""

from enum import Enum
from player_py.scanner import MediaFile


class RepeatMode(Enum):
    NONE = "none"
    ALL = "all"
    ONE = "one"


class SortMode(Enum):
    PATH = "path"
    NAME = "name"


class Playlist:
    def __init__(self, tracks: list[MediaFile] | None = None):
        self.tracks: list[MediaFile] = tracks or []
        self.current_index: int = 0
        self.repeat: RepeatMode = RepeatMode.NONE
        self.sort: SortMode = SortMode.PATH

    @property
    def empty(self) -> bool:
        return len(self.tracks) == 0

    def current(self) -> MediaFile | None:
        if self.empty:
            return None
        self.current_index = max(0, min(self.current_index, len(self.tracks) - 1))
        return self.tracks[self.current_index]

    def next(self) -> MediaFile | None:
        if self.empty:
            return None
        if self.repeat == RepeatMode.ONE:
            return self.current()
        self.current_index += 1
        if self.current_index >= len(self.tracks):
            if self.repeat == RepeatMode.ALL:
                self.current_index = 0
            else:
                self.current_index = len(self.tracks) - 1
                return None  # end of playlist
        return self.current()

    def prev(self) -> MediaFile | None:
        if self.empty:
            return None
        self.current_index = max(0, self.current_index - 1)
        return self.current()

    def select(self, index: int) -> MediaFile | None:
        if 0 <= index < len(self.tracks):
            self.current_index = index
            return self.current()
        return None

    def cycle_repeat(self) -> RepeatMode:
        modes = list(RepeatMode)
        idx = modes.index(self.repeat)
        self.repeat = modes[(idx + 1) % len(modes)]
        return self.repeat

    def cycle_sort(self) -> SortMode:
        modes = list(SortMode)
        idx = modes.index(self.sort)
        self.sort = modes[(idx + 1) % len(modes)]
        self._apply_sort()
        return self.sort

    def _apply_sort(self):
        if self.sort == SortMode.PATH:
            self.tracks.sort(key=lambda t: str(t.path))
        elif self.sort == SortMode.NAME:
            self.tracks.sort(key=lambda t: t.name.lower())
