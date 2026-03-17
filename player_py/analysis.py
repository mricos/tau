"""Analysis screen: training data inspector for vox annotation bundles.

Third screen in tau player. Shows RMS envelope, phoneme timeline,
onset markers, word spans, formant summary, and NN training frame
preview. Exports training_frames.tsv for voxlab consumption.
"""

import json
import curses
from pathlib import Path
from dataclasses import dataclass

from tui_py.rendering.helpers import safe_addstr, draw_box, truncate_middle, format_time


# Sparkline chars for RMS envelope
_SPARK = " ▁▂▃▄▅▆▇█"


@dataclass
class VoxBundle:
    """Loaded annotation data for a single vox document."""
    vox_id: str
    voice: str
    source_text: str = ""
    phonemes: list = None      # [{word, ipa, phonemes: [{ipa, duration_ms}]}]
    spans: list = None         # [{word, start, end}]
    rms: dict = None           # {hopMs, values: [float]}
    onsets: list = None        # [float] times in seconds
    vad: dict = None           # {segments: [{start, end}]}
    analysis: dict = None      # {f0_estimate_hz, formants, ...}

    def __post_init__(self):
        self.phonemes = self.phonemes or []
        self.spans = self.spans or []
        self.rms = self.rms or {"hopMs": 20, "values": []}
        self.onsets = self.onsets or []
        self.vad = self.vad or {"segments": []}

    @property
    def has_data(self) -> bool:
        return bool(self.phonemes or self.spans or self.rms.get("values"))

    @property
    def duration(self) -> float:
        vals = self.rms.get("values", [])
        hop = self.rms.get("hopMs", 20)
        if vals:
            return len(vals) * hop / 1000.0
        if self.spans:
            return max(s.get("end", 0) for s in self.spans)
        return 0.0


def load_bundle(directory: Path, vox_id: str, voice: str) -> VoxBundle:
    """Load all available vox annotation files for a document."""
    bundle = VoxBundle(vox_id=vox_id, voice=voice)

    # Source text
    src = directory / f"{vox_id}.vox.source.md"
    if src.exists():
        bundle.source_text = src.read_text().strip()

    # Phonemes
    ph = directory / f"{vox_id}.vox.phonemes.json"
    if ph.exists():
        try:
            data = json.loads(ph.read_text())
            bundle.phonemes = data.get("tokens", data) if isinstance(data, dict) else data
        except (json.JSONDecodeError, KeyError):
            pass

    # Word spans (voice-specific)
    sp = directory / f"{vox_id}.vox.spans.{voice}.json"
    if sp.exists():
        try:
            data = json.loads(sp.read_text())
            # Handle SpanDoc format
            if "timing" in data:
                bundle.spans = [
                    {"start": t["attrs"]["t0"], "end": t["attrs"]["t1"]}
                    for t in data["timing"] if "attrs" in t
                ]
            elif "spans" in data:
                bundle.spans = data["spans"]
            elif isinstance(data, list):
                bundle.spans = data
        except (json.JSONDecodeError, KeyError):
            pass

    # RMS envelope
    rms = directory / f"{vox_id}.vox.rms.json"
    if rms.exists():
        try:
            bundle.rms = json.loads(rms.read_text())
        except json.JSONDecodeError:
            pass

    # Onsets
    ons = directory / f"{vox_id}.vox.onsets.json"
    if ons.exists():
        try:
            bundle.onsets = json.loads(ons.read_text())
        except json.JSONDecodeError:
            pass

    # VAD
    vad = directory / f"{vox_id}.vox.vad.json"
    if vad.exists():
        try:
            bundle.vad = json.loads(vad.read_text())
        except json.JSONDecodeError:
            pass

    # Full analysis (from vox analyze)
    for suffix in [f"{vox_id}.analysis.json", f"{vox_id}.vox.analysis.json"]:
        af = directory / suffix
        if af.exists():
            try:
                bundle.analysis = json.loads(af.read_text())
            except json.JSONDecodeError:
                pass
            break

    return bundle


def sparkline(values: list[float], width: int) -> str:
    """Render a list of floats as a sparkline string of given width."""
    if not values:
        return " " * width

    # Downsample or upsample to fit width
    n = len(values)
    if n == 0:
        return " " * width

    peak = max(values) if values else 1.0
    if peak <= 0:
        return " " * width

    result = []
    for i in range(width):
        # Map column to source index
        idx = int(i * n / width)
        idx = min(idx, n - 1)
        v = values[idx] / peak
        ci = int(v * (len(_SPARK) - 1))
        ci = max(0, min(ci, len(_SPARK) - 1))
        result.append(_SPARK[ci])
    return "".join(result)


def onset_markers(onsets: list[float], duration: float, width: int) -> str:
    """Render onset times as | markers on a timeline."""
    if not onsets or duration <= 0:
        return " " * width

    line = [" "] * width
    for t in onsets:
        col = int(t / duration * width)
        if 0 <= col < width:
            line[col] = "|"
    return "".join(line)


def phoneme_timeline(phonemes: list, spans: list, duration: float, width: int) -> str:
    """Render phoneme labels positioned by their word spans."""
    if not phonemes or duration <= 0:
        return " " * width

    line = [" "] * width

    # If we have word spans, use them for positioning
    if spans and len(spans) >= len(phonemes):
        for i, ph in enumerate(phonemes):
            if i >= len(spans):
                break
            s = spans[i]
            start_col = int(s.get("start", 0) / duration * width)
            word = ph.get("word", ph.get("ipa", "?"))
            for j, ch in enumerate(word[:4]):  # max 4 chars per word
                col = start_col + j
                if 0 <= col < width:
                    line[col] = ch
    else:
        # Evenly space phonemes
        for i, ph in enumerate(phonemes):
            col = int(i * width / max(len(phonemes), 1))
            word = ph.get("word", ph.get("ipa", "?"))
            for j, ch in enumerate(word[:4]):
                c = col + j
                if 0 <= c < width:
                    line[c] = ch

    return "".join(line)


def word_spans_line(spans: list, duration: float, width: int) -> str:
    """Render word spans as bracketed regions."""
    if not spans or duration <= 0:
        return " " * width

    line = [" "] * width
    for s in spans:
        t0 = s.get("start", s.get("t0", 0))
        t1 = s.get("end", s.get("t1", 0))
        word = s.get("word", s.get("text", ""))
        c0 = int(t0 / duration * width)
        c1 = int(t1 / duration * width)
        if c0 >= width:
            continue
        c1 = min(c1, width - 1)
        if c0 < width:
            line[c0] = "["
        if c1 < width:
            line[c1] = "]"
        # Fill word inside brackets
        for j, ch in enumerate(word):
            col = c0 + 1 + j
            if col < c1 and col < width:
                line[col] = ch

    return "".join(line)


# ── Training Frame Export ──


def generate_training_frames(bundle: VoxBundle, hop_ms: int = 20) -> list[dict]:
    """Generate per-frame feature vectors for NN training.

    Each frame:
      time_s, rms, phoneme, word, voiced, onset, f0, f1, f2, f3, tilt
    """
    rms_values = bundle.rms.get("values", [])
    rms_hop = bundle.rms.get("hopMs", hop_ms)
    duration = bundle.duration

    if duration <= 0:
        return []

    n_frames = int(duration * 1000 / hop_ms)
    frames = []

    # Build onset lookup (within 1 hop of frame time)
    onset_set = set()
    for t in bundle.onsets:
        frame_idx = int(t * 1000 / hop_ms)
        onset_set.add(frame_idx)

    # Build VAD lookup
    vad_segments = bundle.vad.get("segments", [])

    # Build phoneme/word lookup from spans + phonemes
    span_lookup = []  # [(start_frame, end_frame, word, ipa)]
    if bundle.spans:
        for i, s in enumerate(bundle.spans):
            t0 = s.get("start", s.get("t0", 0))
            t1 = s.get("end", s.get("t1", 0))
            word = s.get("word", s.get("text", ""))
            ipa = ""
            if i < len(bundle.phonemes):
                ipa = bundle.phonemes[i].get("ipa", "")
            span_lookup.append((
                int(t0 * 1000 / hop_ms),
                int(t1 * 1000 / hop_ms),
                word, ipa
            ))

    # Extract formant info from analysis
    f0 = 0.0
    f1 = f2 = f3 = 0.0
    tilt = 0.0
    if bundle.analysis:
        a = bundle.analysis.get("analysis", bundle.analysis)
        f0 = a.get("f0_estimate_hz", 0)
        tilt = a.get("spectral_tilt", 0)
        fm = a.get("formants", {})
        f1 = fm.get("f1_energy", 0)
        f2 = fm.get("f2_energy", 0)
        f3 = fm.get("f3_energy", 0)

    for i in range(n_frames):
        t = i * hop_ms / 1000.0

        # RMS value (resample if hops differ)
        rms_idx = int(i * hop_ms / rms_hop) if rms_hop > 0 else i
        rms_val = rms_values[rms_idx] if rms_idx < len(rms_values) else 0.0

        # Voiced?
        voiced = 0
        for seg in vad_segments:
            if seg.get("start", 0) <= t <= seg.get("end", 0):
                voiced = 1
                break

        # Onset?
        is_onset = 1 if i in onset_set else 0

        # Phoneme/word at this frame
        phoneme = "_"
        word = "_"
        for (sf, ef, w, ipa) in span_lookup:
            if sf <= i < ef:
                word = w
                phoneme = ipa if ipa else w
                break

        frames.append({
            "time_s": round(t, 3),
            "rms": round(rms_val, 6),
            "phoneme": phoneme,
            "word": word,
            "voiced": voiced,
            "onset": is_onset,
            "f0": round(f0, 1),
            "f1": round(f1, 6),
            "f2": round(f2, 6),
            "f3": round(f3, 6),
            "tilt": round(tilt, 4),
        })

    return frames


def export_training_tsv(frames: list[dict], output_path: Path):
    """Write training_frames.tsv."""
    header = "time_s\trms\tphoneme\tword\tvoiced\tonset\tf0\tf1\tf2\tf3\ttilt"
    with open(output_path, 'w') as f:
        f.write("# " + header + "\n")
        for fr in frames:
            f.write('\t'.join(str(fr[k]) for k in [
                "time_s", "rms", "phoneme", "word", "voiced",
                "onset", "f0", "f1", "f2", "f3", "tilt"
            ]) + '\n')


# ── Curses Rendering ──


class AnalysisScreen:
    """Renders the analysis view inside the tau player."""

    def __init__(self):
        self.bundle: VoxBundle | None = None
        self.scroll: int = 0
        self.cursor_time: float = 0.0  # playback cursor position

    def load(self, audio_path: Path, vox_id: str, voice: str):
        """Load a vox bundle for display."""
        self.bundle = load_bundle(audio_path.parent, vox_id, voice)
        self.scroll = 0

    def set_cursor(self, time_s: float):
        """Update playback cursor position."""
        self.cursor_time = time_s

    def render(self, scr, y: int, x: int, h: int, w: int):
        """Render analysis screen in the given region."""
        b = self.bundle
        if not b or not b.has_data:
            draw_box(scr, y, x, h, w, "Analysis")
            safe_addstr(scr, y + 2, x + 2, "No vox annotations for this track.")
            safe_addstr(scr, y + 3, x + 2, "Select a .vox.audio.*.mp3 file to inspect.")
            return

        title = f"Analysis: {b.vox_id} ({b.voice})"
        draw_box(scr, y, x, h, w, title)

        inner_x = x + 2
        inner_w = w - 4
        row = y + 1

        duration = b.duration
        spark_w = min(inner_w, 60)

        # Source text preview
        if b.source_text and row < y + h - 1:
            preview = b.source_text[:inner_w]
            safe_addstr(scr, row, inner_x, truncate_middle(preview, inner_w), curses.A_DIM)
            row += 2

        # RMS Envelope
        rms_vals = b.rms.get("values", [])
        if rms_vals and row + 2 < y + h - 1:
            safe_addstr(scr, row, inner_x, "RMS Envelope", curses.A_BOLD)
            row += 1
            sl = sparkline(rms_vals, spark_w)
            safe_addstr(scr, row, inner_x, sl)
            # Time axis
            row += 1
            if duration > 0:
                axis = f"0.0s{' ' * max(0, spark_w - 12)}{duration:.1f}s"
                safe_addstr(scr, row, inner_x, axis[:inner_w], curses.A_DIM)
            row += 2

        # Phoneme Timeline
        if b.phonemes and row + 2 < y + h - 1:
            safe_addstr(scr, row, inner_x, "Phoneme Timeline", curses.A_BOLD)
            row += 1
            pt = phoneme_timeline(b.phonemes, b.spans, duration, spark_w)
            safe_addstr(scr, row, inner_x, pt)
            row += 2

        # Onset Markers
        if b.onsets and row + 2 < y + h - 1:
            safe_addstr(scr, row, inner_x, f"Onsets ({len(b.onsets)})", curses.A_BOLD)
            row += 1
            om = onset_markers(b.onsets, duration, spark_w)
            safe_addstr(scr, row, inner_x, om)
            row += 2

        # Word Spans
        if b.spans and row + 2 < y + h - 1:
            safe_addstr(scr, row, inner_x, f"Word Spans ({len(b.spans)})", curses.A_BOLD)
            row += 1
            ws = word_spans_line(b.spans, duration, spark_w)
            safe_addstr(scr, row, inner_x, ws)
            row += 2

        # Formant Summary
        if b.analysis and row + 2 < y + h - 1:
            a = b.analysis.get("analysis", b.analysis)
            safe_addstr(scr, row, inner_x, "Formants", curses.A_BOLD)
            row += 1
            f0 = a.get("f0_estimate_hz", 0)
            tilt = a.get("spectral_tilt", 0)
            fm = a.get("formants", {})
            line = f"F0: {f0:.0f}Hz  Tilt: {tilt:.2f}  "
            line += f"F1: {fm.get('f1_energy', 0):.4f}  "
            line += f"F2: {fm.get('f2_energy', 0):.4f}  "
            line += f"F3: {fm.get('f3_energy', 0):.4f}"
            safe_addstr(scr, row, inner_x, line[:inner_w])
            row += 2

        # Training Frame Preview
        if row + 4 < y + h - 1:
            frames = generate_training_frames(b, hop_ms=20)
            n_frames = len(frames)
            n_voiced = sum(1 for f in frames if f["voiced"])
            n_onsets = sum(1 for f in frames if f["onset"])
            n_phonemes = len(set(f["phoneme"] for f in frames if f["phoneme"] != "_"))

            safe_addstr(scr, row, inner_x, "NN Training Features (per frame @ 20ms)", curses.A_BOLD)
            row += 1
            stats = f"Frames: {n_frames}  Phoneme labels: {n_phonemes}  "
            stats += f"Voiced: {n_voiced}  Onsets: {n_onsets}"
            safe_addstr(scr, row, inner_x, stats[:inner_w])
            row += 1

            # Show first few frames
            if row + 2 < y + h - 1:
                header = "time    rms      phoneme  word     voiced onset"
                safe_addstr(scr, row, inner_x, header[:inner_w], curses.A_DIM)
                row += 1
                # Show frames near cursor or first frames
                start_frame = 0
                if self.cursor_time > 0 and n_frames > 0:
                    start_frame = max(0, int(self.cursor_time * 50) - 2)
                for fi in range(start_frame, min(start_frame + 5, n_frames)):
                    if row >= y + h - 2:
                        break
                    fr = frames[fi]
                    line = f"{fr['time_s']:6.3f}  {fr['rms']:7.4f}  "
                    line += f"{fr['phoneme']:<8s} {fr['word']:<8s} "
                    line += f"{fr['voiced']}      {fr['onset']}"
                    safe_addstr(scr, row, inner_x, line[:inner_w])
                    row += 1

        # Controls
        if y + h - 2 > row:
            controls = "[a]back [e]xport TSV [E]xport all"
            safe_addstr(scr, y + h - 2, inner_x, controls[:inner_w], curses.A_DIM)

    def handle_export(self, output_dir: Path) -> str:
        """Export training frames for current bundle. Returns output path."""
        if not self.bundle or not self.bundle.has_data:
            return ""

        frames = generate_training_frames(self.bundle)
        if not frames:
            return ""

        filename = f"{self.bundle.vox_id}.{self.bundle.voice}.training_frames.tsv"
        out = output_dir / filename
        export_training_tsv(frames, out)
        return str(out)
