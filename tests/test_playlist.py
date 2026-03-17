"""Tests for player_py.playlist — navigation, repeat, sort, filter."""

import pytest
from pathlib import Path
from player_py.playlist import Playlist, RepeatMode, SortMode
from player_py.scanner import MediaFile


def _make_track(name, artist="", album="", duration=0.0, vox_id="", vox_voice="", genre=""):
    """Create a MediaFile without touching the filesystem."""
    return MediaFile(
        path=Path(f"/music/{name}"),
        name=name,
        extension=Path(name).suffix.lower(),
        _duration=duration,
        title=Path(name).stem,
        artist=artist,
        album=album,
        genre=genre,
        vox_id=vox_id,
        vox_voice=vox_voice,
    )


@pytest.fixture
def tracks():
    return [
        _make_track("c.mp3", artist="Zed", album="B-Album", duration=180.0),
        _make_track("a.mp3", artist="Alice", album="A-Album", duration=240.0),
        _make_track("b.mp3", artist="Bob", album="C-Album", duration=120.0),
    ]


@pytest.fixture
def playlist(tracks):
    return Playlist(tracks)


# --- Empty playlist ---

class TestEmptyPlaylist:
    def test_empty(self):
        p = Playlist()
        assert p.empty
        assert p.current() is None
        assert p.next() is None
        assert p.prev() is None
        assert p.select(0) is None


# --- Navigation ---

class TestNavigation:
    def test_current(self, playlist, tracks):
        assert playlist.current() == tracks[0]

    def test_next(self, playlist, tracks):
        assert playlist.next() == tracks[1]
        assert playlist.next() == tracks[2]

    def test_next_end_of_list(self, playlist):
        playlist.current_index = 2
        assert playlist.next() is None  # returns None at end
        assert playlist.current_index == 2  # stays at last

    def test_prev(self, playlist, tracks):
        playlist.current_index = 2
        assert playlist.prev() == tracks[1]
        assert playlist.prev() == tracks[0]

    def test_prev_at_start(self, playlist, tracks):
        assert playlist.prev() == tracks[0]  # stays at 0

    def test_select_valid(self, playlist, tracks):
        assert playlist.select(2) == tracks[2]
        assert playlist.current_index == 2

    def test_select_invalid(self, playlist):
        assert playlist.select(-1) is None
        assert playlist.select(99) is None

    def test_current_clamps_index(self, playlist, tracks):
        playlist.current_index = 999
        assert playlist.current() == tracks[2]  # clamped to last


# --- Repeat modes ---

class TestRepeat:
    def test_repeat_none(self, playlist):
        """NONE: stops at end."""
        playlist.current_index = 2
        assert playlist.next() is None

    def test_repeat_all(self, playlist, tracks):
        """ALL: wraps to start."""
        playlist.repeat = RepeatMode.ALL
        playlist.current_index = 2
        assert playlist.next() == tracks[0]

    def test_repeat_one(self, playlist, tracks):
        """ONE: stays on current."""
        playlist.repeat = RepeatMode.ONE
        playlist.current_index = 1
        assert playlist.next() == tracks[1]
        assert playlist.next() == tracks[1]

    def test_cycle_repeat(self, playlist):
        assert playlist.cycle_repeat() == RepeatMode.ALL
        assert playlist.cycle_repeat() == RepeatMode.ONE
        assert playlist.cycle_repeat() == RepeatMode.NONE


# --- Sort modes ---

class TestSort:
    def test_sort_name(self, playlist):
        playlist.sort = SortMode.NAME
        playlist._apply_sort()
        names = [t.name for t in playlist.tracks]
        assert names == ["a.mp3", "b.mp3", "c.mp3"]

    def test_sort_artist(self, playlist):
        playlist.sort = SortMode.ARTIST
        playlist._apply_sort()
        artists = [t.artist for t in playlist.tracks]
        assert artists == ["Alice", "Bob", "Zed"]

    def test_sort_duration(self, playlist):
        playlist.sort = SortMode.DURATION
        playlist._apply_sort()
        durations = [t.duration for t in playlist.tracks]
        assert durations == [120.0, 180.0, 240.0]

    def test_cycle_sort(self, playlist):
        assert playlist.cycle_sort() == SortMode.NAME


# --- Filter ---

class TestFilter:
    def test_filter_by_name(self, playlist):
        playlist.set_filter("a.mp3")
        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].name == "a.mp3"

    def test_filter_by_artist(self, playlist):
        playlist.set_filter("bob")
        assert len(playlist.tracks) == 1
        assert playlist.tracks[0].artist == "Bob"

    def test_filter_clears(self, playlist):
        playlist.set_filter("bob")
        playlist.set_filter("")
        assert len(playlist.tracks) == 3

    def test_filter_resets_index(self, playlist):
        playlist.current_index = 2
        playlist.set_filter("alice")
        assert playlist.current_index == 0

    def test_filter_no_match(self, playlist):
        playlist.set_filter("nonexistent")
        assert playlist.empty

    def test_clear_filter(self, playlist):
        playlist.set_filter("bob")
        playlist.clear_filter()
        assert len(playlist.tracks) == 3
        assert playlist.filter_text == ""

    def test_filter_annotated(self):
        tracks = [
            _make_track("a.mp3", vox_id="v1"),
            _make_track("b.mp3"),
            _make_track("c.mp3", vox_id="v2"),
        ]
        p = Playlist(tracks)
        p.filter_annotated()
        assert len(p.tracks) == 2
        assert all(t.vox_id for t in p.tracks)

    def test_filter_by_genre(self):
        tracks = [
            _make_track("a.mp3", genre="rock"),
            _make_track("b.mp3", genre="jazz"),
        ]
        p = Playlist(tracks)
        p.set_filter("jazz")
        assert len(p.tracks) == 1
