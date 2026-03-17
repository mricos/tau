"""Tests for tau_lib.core.state — dataclasses, transport, markers, channels."""

import pytest
from tau_lib.core.state import (
    KernelParams,
    Channel,
    ChannelManager,
    Transport,
    Marker,
    MarkerManager,
    DisplayState,
    LayoutConfig,
)


# --- KernelParams ---

class TestKernelParams:
    def test_defaults_valid(self):
        k = KernelParams()
        assert k.validate()

    def test_invalid_tau_order(self):
        """tau_a must be less than tau_r."""
        k = KernelParams(tau_a=0.01, tau_r=0.005)
        assert not k.validate()

    def test_invalid_zero_threshold(self):
        k = KernelParams(threshold=0.0)
        assert not k.validate()

    def test_invalid_negative_fs(self):
        k = KernelParams(fs=-1)
        assert not k.validate()

    def test_to_tscale_args(self):
        k = KernelParams(tau_a=0.001, tau_r=0.005, threshold=3.0, refractory=0.015)
        args = k.to_tscale_args()
        assert args == ['-ta', '0.001', '-tr', '0.005', '-th', '3.0', '-ref', '0.015']

    def test_copy(self):
        k = KernelParams(tau_a=0.002)
        c = k.copy()
        assert c.tau_a == 0.002
        c.tau_a = 0.999
        assert k.tau_a == 0.002  # original unchanged


# --- Channel & ChannelManager ---

class TestChannel:
    def test_reset(self):
        ch = Channel(id=0, name="test", visible=False, gain=5.0, offset=2.0)
        ch.reset()
        assert ch.visible is True
        assert ch.gain == 1.0
        assert ch.offset == 0.0


class TestChannelManager:
    def test_init(self):
        cm = ChannelManager()
        assert len(cm.channels) == 4

    def test_get_valid(self):
        cm = ChannelManager()
        ch = cm.get(0)
        assert ch.name == "audio"

    def test_get_invalid(self):
        cm = ChannelManager()
        with pytest.raises(ValueError):
            cm.get(99)

    def test_toggle_visibility(self):
        cm = ChannelManager()
        assert cm.get(0).visible is True
        cm.toggle_visibility(0)
        assert cm.get(0).visible is False
        cm.toggle_visibility(0)
        assert cm.get(0).visible is True

    def test_set_gain(self):
        cm = ChannelManager()
        cm.set_gain(1, 0.5)
        assert cm.get(1).gain == 0.5

    def test_multiply_gain(self):
        cm = ChannelManager()
        cm.set_gain(0, 2.0)
        cm.multiply_gain(0, 0.5)
        assert cm.get(0).gain == 1.0

    def test_offset(self):
        cm = ChannelManager()
        cm.set_offset(0, 5.0)
        assert cm.get(0).offset == 5.0
        cm.adjust_offset(0, -2.0)
        assert cm.get(0).offset == 3.0

    def test_all_visible(self):
        cm = ChannelManager()
        assert len(cm.all_visible()) == 4
        cm.toggle_visibility(0)
        cm.toggle_visibility(2)
        assert len(cm.all_visible()) == 2

    def test_reset_channel(self):
        cm = ChannelManager()
        cm.set_gain(0, 10.0)
        cm.reset_channel(0)
        assert cm.get(0).gain == 1.0


# --- Transport (pure state, no tau connection) ---

class TestTransport:
    def test_defaults(self):
        t = Transport()
        assert t.playing is False
        assert t.position == 0.0
        assert t.span == 1.0

    def test_seek(self):
        t = Transport(duration=10.0)
        t.seek(5.0)
        assert t.position == 5.0

    def test_seek_clamps(self):
        t = Transport(duration=10.0)
        t.seek(-5.0)
        assert t.position == 0.0
        t.seek(99.0)
        assert t.position == 10.0

    def test_scrub(self):
        t = Transport(duration=10.0)
        t.seek(5.0)
        t.scrub(2.0)
        assert t.position == 7.0
        t.scrub(-3.0)
        assert t.position == 4.0

    def test_scrub_pct(self):
        t = Transport(duration=100.0)
        t.scrub_pct(10.0)
        assert t.position == 10.0

    def test_home(self):
        t = Transport(duration=10.0, playing=True)
        t.seek(5.0)
        t.home()
        assert t.position == 0.0
        assert t.playing is False

    def test_end(self):
        t = Transport(duration=10.0, span=2.0)
        t.end()
        assert t.position == 8.0  # duration - span
        assert t.playing is False

    def test_zoom(self):
        t = Transport(duration=10.0, span=5.0)
        t.zoom(2.0)
        assert t.span == 2.0

    def test_zoom_clamps(self):
        t = Transport(duration=10.0)
        t.zoom(0.0)
        assert t.span == 0.01  # minimum
        t.zoom(999.0)
        assert t.span == 10.0  # max = duration

    def test_zoom_in_out(self):
        t = Transport(duration=10.0, span=4.0)
        t.zoom_in(2.0)
        assert t.span == 2.0
        t.zoom_out(2.0)
        assert t.span == 4.0

    def test_compute_window(self):
        t = Transport(duration=10.0, span=3.0)
        t.seek(2.0)
        left, right = t.compute_window()
        assert left == 2.0
        assert right == 5.0

    def test_update_advances_position(self):
        t = Transport(duration=10.0, playing=True)
        t.update(dt=0.5)
        assert t.position == 0.5

    def test_update_stops_at_end(self):
        t = Transport(duration=1.0, playing=True, position=0.9)
        t.update(dt=0.5)
        assert t.position == 1.0
        assert t.playing is False

    def test_update_noop_when_paused(self):
        t = Transport(duration=10.0, playing=False)
        t.update(dt=1.0)
        assert t.position == 0.0


# --- MarkerManager ---

class TestMarkerManager:
    def test_add_and_retrieve(self):
        mm = MarkerManager()
        mm.add(1.0, "intro")
        assert mm.get_by_label("intro").time == 1.0

    def test_sorted_by_time(self):
        mm = MarkerManager()
        mm.add(3.0, "c")
        mm.add(1.0, "a")
        mm.add(2.0, "b")
        times = [m.time for m in mm.all()]
        assert times == [1.0, 2.0, 3.0]

    def test_duplicate_label_raises(self):
        mm = MarkerManager()
        mm.add(1.0, "intro")
        with pytest.raises(ValueError):
            mm.add(2.0, "intro")

    def test_remove(self):
        mm = MarkerManager()
        mm.add(1.0, "intro")
        assert mm.remove("intro") is True
        assert mm.get_by_label("intro") is None

    def test_remove_nonexistent(self):
        mm = MarkerManager()
        assert mm.remove("nope") is False

    def test_find_nearest(self):
        mm = MarkerManager()
        mm.add(1.0, "a")
        mm.add(5.0, "b")
        mm.add(9.0, "c")
        assert mm.find_nearest(4.0).label == "b"
        assert mm.find_nearest(0.0).label == "a"

    def test_find_next(self):
        mm = MarkerManager()
        mm.add(1.0, "a")
        mm.add(5.0, "b")
        assert mm.find_next(0.0).label == "a"
        assert mm.find_next(3.0).label == "b"
        assert mm.find_next(10.0) is None

    def test_find_prev(self):
        mm = MarkerManager()
        mm.add(1.0, "a")
        mm.add(5.0, "b")
        assert mm.find_prev(10.0).label == "b"
        assert mm.find_prev(3.0).label == "a"
        assert mm.find_prev(0.0) is None

    def test_find_on_empty(self):
        mm = MarkerManager()
        assert mm.find_nearest(1.0) is None
        assert mm.find_next(1.0) is None
        assert mm.find_prev(1.0) is None


# --- DisplayState ---

class TestDisplayState:
    def test_toggle_mode(self):
        ds = DisplayState()
        assert ds.mode == "envelope"
        ds.toggle_mode()
        assert ds.mode == "points"
        ds.toggle_mode()
        assert ds.mode == "envelope"
