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
    ARTIST = "artist"
    ALBUM = "album"
    DURATION = "dur"
    VOX_ID = "vox"


class Playlist:
    def __init__(self, tracks: list[MediaFile] | None = None):
        self._all_tracks: list[MediaFile] = tracks or []
        self.tracks: list[MediaFile] = list(self._all_tracks)
        self.current_index: int = 0
        self.repeat: RepeatMode = RepeatMode.NONE
        self.sort: SortMode = SortMode.PATH
        self.filter_text: str = ""

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

    def set_filter(self, text: str):
        """Filter tracks across name, title, artist, album, genre, vox_voice."""
        self.filter_text = text
        if not text:
            self.tracks = list(self._all_tracks)
        else:
            t = text.lower()
            self.tracks = [
                f for f in self._all_tracks
                if t in f.name.lower()
                or t in f.title.lower()
                or t in f.artist.lower()
                or t in f.album.lower()
                or t in f.genre.lower()
                or t in f.vox_voice.lower()
            ]
        self._apply_sort()
        self.current_index = 0

    def filter_annotated(self):
        """Show only tracks that have vox annotations."""
        self.tracks = [f for f in self._all_tracks if f.vox_id]
        self._apply_sort()
        self.current_index = 0

    def clear_filter(self):
        self.filter_text = ""
        self.tracks = list(self._all_tracks)
        self._apply_sort()

    def _apply_sort(self):
        if self.sort == SortMode.PATH:
            self.tracks.sort(key=lambda t: str(t.path))
        elif self.sort == SortMode.NAME:
            self.tracks.sort(key=lambda t: t.name.lower())
        elif self.sort == SortMode.ARTIST:
            self.tracks.sort(key=lambda t: (t.artist.lower(), t.album.lower(), t.track_num))
        elif self.sort == SortMode.ALBUM:
            self.tracks.sort(key=lambda t: (t.album.lower(), t.track_num))
        elif self.sort == SortMode.DURATION:
            self.tracks.sort(key=lambda t: t.duration)
        elif self.sort == SortMode.VOX_ID:
            self.tracks.sort(key=lambda t: (t.vox_id or "z", t.vox_voice))
