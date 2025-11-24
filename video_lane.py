"""
Video lane support for tau with thumbnail strip caching.
Integrates with screentool TRS pattern for shared recordings.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
import pickle
import json
import time


@dataclass
class VideoMetadata:
    """Video file metadata."""

    path: Path
    fps: float
    frame_count: int
    duration: float
    width: int
    height: int
    codec: str
    created: float = field(default_factory=time.time)


@dataclass
class ThumbnailStrip:
    """Pre-rendered thumbnail strip for efficient playback."""

    frames: List[List[str]]  # List of ASCII frames (each frame is list of lines)
    timestamps: List[float]  # Timestamp for each frame
    thumbnail_size: int      # NxN resolution
    sampling_interval: float # Frames per second sampled
    created: float = field(default_factory=time.time)


class VideoLane:
    """
    Video lane with thumbnail strip caching.

    Workflow:
    1. Load video file
    2. Pre-process: generate thumbnail strip at sampling interval
    3. Cache strip to context_dir/[epoch]/cache/video_strip.pkl
    4. Runtime: lookup frames from cached strip (fast, no decoding)
    """

    def __init__(
        self,
        video_path: Path,
        context_dir: Path,
        thumbnail_size: int = 4,
        sampling_interval: float = 1.0
    ):
        """
        Initialize video lane.

        Args:
            video_path: Path to video file
            context_dir: Context directory for cache
            thumbnail_size: NxN thumbnail resolution (default 4x4)
            sampling_interval: Frames per second to sample (default 1.0)
        """
        self.video_path = video_path
        self.context_dir = context_dir
        self.thumbnail_size = thumbnail_size
        self.sampling_interval = sampling_interval

        self.metadata: Optional[VideoMetadata] = None
        self.thumbnail_strip: Optional[ThumbnailStrip] = None

        # Lazy opencv import
        self.cv2 = None

    def _ensure_cv2(self):
        """Lazily import opencv."""
        if self.cv2 is None:
            import cv2
            self.cv2 = cv2

    def load(self) -> bool:
        """
        Load video and generate/load cached thumbnail strip.

        Returns:
            True if successful
        """
        self._ensure_cv2()

        # Try to load cached strip first
        cache_path = self._get_cache_path()
        if cache_path.exists():
            try:
                if self._load_cached_strip(cache_path):
                    print(f"Loaded cached video strip: {cache_path.name}")
                    return True
            except Exception as e:
                print(f"Warning: Failed to load cache, regenerating: {e}")

        # Generate new strip
        print(f"Generating video thumbnail strip (sampling at {self.sampling_interval} fps)...")
        if self._generate_thumbnail_strip():
            # Save to cache
            try:
                self._save_cached_strip(cache_path)
                print(f"Cached video strip: {cache_path}")
            except Exception as e:
                print(f"Warning: Failed to save cache: {e}")
            return True

        return False

    def _get_cache_path(self) -> Path:
        """Get cache file path for this video."""
        # Use video file's modification time as part of cache key
        mtime = int(self.video_path.stat().st_mtime)
        cache_name = f"video_{self.video_path.stem}_{mtime}_{self.thumbnail_size}_{self.sampling_interval}.pkl"

        cache_dir = self.context_dir / ".cache" / "video"
        cache_dir.mkdir(parents=True, exist_ok=True)

        return cache_dir / cache_name

    def _get_metadata_path(self) -> Path:
        """Get metadata file path for this video."""
        mtime = int(self.video_path.stat().st_mtime)
        meta_name = f"video_{self.video_path.stem}_{mtime}_meta.json"

        cache_dir = self.context_dir / ".cache" / "video"
        cache_dir.mkdir(parents=True, exist_ok=True)

        return cache_dir / meta_name

    def _generate_thumbnail_strip(self) -> bool:
        """Generate thumbnail strip by sampling video."""
        try:
            cap = self.cv2.VideoCapture(str(self.video_path))

            # Get video properties
            fps = cap.get(self.cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(self.cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(self.cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(self.cv2.CAP_PROP_FRAME_HEIGHT))
            codec_fourcc = int(cap.get(self.cv2.CAP_PROP_FOURCC))
            codec = "".join([chr((codec_fourcc >> 8 * i) & 0xFF) for i in range(4)])
            duration = frame_count / fps if fps > 0 else 0

            # Store metadata
            self.metadata = VideoMetadata(
                path=self.video_path,
                fps=fps,
                frame_count=frame_count,
                duration=duration,
                width=width,
                height=height,
                codec=codec
            )

            # Sample frames
            frames = []
            timestamps = []

            # Calculate sampling: every N frames
            frame_interval = int(fps / self.sampling_interval) if fps > 0 else 1
            frame_interval = max(1, frame_interval)

            frame_idx = 0
            while frame_idx < frame_count:
                cap.set(self.cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()

                if not ret:
                    break

                # Convert to ASCII thumbnail
                ascii_frame = self._frame_to_ascii(frame, self.thumbnail_size)
                timestamp = frame_idx / fps if fps > 0 else frame_idx

                frames.append(ascii_frame)
                timestamps.append(timestamp)

                frame_idx += frame_interval

            cap.release()

            # Create thumbnail strip
            self.thumbnail_strip = ThumbnailStrip(
                frames=frames,
                timestamps=timestamps,
                thumbnail_size=self.thumbnail_size,
                sampling_interval=self.sampling_interval
            )

            print(f"Generated {len(frames)} thumbnails from {duration:.1f}s video")
            return True

        except Exception as e:
            print(f"Error generating thumbnail strip: {e}")
            return False

    def _frame_to_ascii(self, frame, size: int) -> List[str]:
        """
        Convert video frame to ASCII art.

        Args:
            frame: OpenCV frame (BGR)
            size: Target size (NxN)

        Returns:
            List of ASCII lines
        """
        # Resize to target size
        small = self.cv2.resize(frame, (size, size))

        # Convert to grayscale
        gray = self.cv2.cvtColor(small, self.cv2.COLOR_BGR2GRAY)

        # ASCII character ramp (dark to light)
        chars = " .:-=+*#%@"

        # Convert to ASCII
        ascii_lines = []
        for row in gray:
            line = ''.join(chars[min(val // 26, 9)] for val in row)
            ascii_lines.append(line)

        return ascii_lines

    def _save_cached_strip(self, cache_path: Path):
        """Save thumbnail strip to cache file."""
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, 'wb') as f:
            pickle.dump(self.thumbnail_strip, f)

        # Also save metadata as JSON for inspection
        if self.metadata:
            meta_path = self._get_metadata_path()
            with open(meta_path, 'w') as f:
                json.dump({
                    'path': str(self.metadata.path),
                    'fps': self.metadata.fps,
                    'frame_count': self.metadata.frame_count,
                    'duration': self.metadata.duration,
                    'width': self.metadata.width,
                    'height': self.metadata.height,
                    'codec': self.metadata.codec,
                    'thumbnail_size': self.thumbnail_size,
                    'sampling_interval': self.sampling_interval,
                    'num_thumbnails': len(self.thumbnail_strip.frames),
                    'created': self.metadata.created
                }, f, indent=2)

    def _load_cached_strip(self, cache_path: Path) -> bool:
        """Load thumbnail strip from cache file."""
        try:
            with open(cache_path, 'rb') as f:
                self.thumbnail_strip = pickle.load(f)

            # Load metadata if available
            meta_path = self._get_metadata_path()
            if meta_path.exists():
                with open(meta_path, 'r') as f:
                    meta_dict = json.load(f)
                    self.metadata = VideoMetadata(
                        path=Path(meta_dict['path']),
                        fps=meta_dict['fps'],
                        frame_count=meta_dict['frame_count'],
                        duration=meta_dict['duration'],
                        width=meta_dict['width'],
                        height=meta_dict['height'],
                        codec=meta_dict['codec'],
                        created=meta_dict.get('created', time.time())
                    )

            return True

        except Exception as e:
            print(f"Error loading cached strip: {e}")
            return False

    def get_frame_at_time(self, t: float) -> Optional[List[str]]:
        """
        Get ASCII frame at given time.

        Args:
            t: Time in seconds

        Returns:
            ASCII frame (list of lines) or None
        """
        if not self.thumbnail_strip or not self.thumbnail_strip.timestamps:
            return None

        # Binary search for nearest timestamp
        timestamps = self.thumbnail_strip.timestamps

        # Clamp to valid range
        if t <= timestamps[0]:
            return self.thumbnail_strip.frames[0]
        if t >= timestamps[-1]:
            return self.thumbnail_strip.frames[-1]

        # Binary search
        left, right = 0, len(timestamps) - 1
        while left < right:
            mid = (left + right) // 2
            if timestamps[mid] < t:
                left = mid + 1
            else:
                right = mid

        # Return closest frame
        if left > 0 and abs(timestamps[left-1] - t) < abs(timestamps[left] - t):
            return self.thumbnail_strip.frames[left-1]
        return self.thumbnail_strip.frames[left]

    def get_info(self) -> dict:
        """Get video information."""
        if not self.metadata:
            return {}

        return {
            'path': str(self.metadata.path),
            'duration': self.metadata.duration,
            'fps': self.metadata.fps,
            'resolution': f"{self.metadata.width}x{self.metadata.height}",
            'codec': self.metadata.codec,
            'thumbnail_size': self.thumbnail_size,
            'sampling_interval': self.sampling_interval,
            'num_thumbnails': len(self.thumbnail_strip.frames) if self.thumbnail_strip else 0
        }


def load_video_from_screentool_session(context_dir: Path, epoch: str, thumbnail_size: int = 4, sampling_interval: float = 1.0) -> Optional[VideoLane]:
    """
    Load video from screentool session using TRS pattern.

    Args:
        context_dir: Context directory (shared with screentool)
        epoch: Session epoch timestamp
        thumbnail_size: NxN thumbnail resolution
        sampling_interval: Frames per second to sample

    Returns:
        VideoLane or None if not found
    """
    # TRS pattern: context_dir/[epoch]/db/[epoch].video.raw.mp4
    video_path = context_dir / epoch / "db" / f"{epoch}.video.raw.mp4"

    if not video_path.exists():
        # Try alternative: context_dir/[epoch]/recording.mp4
        video_path = context_dir / epoch / "recording.mp4"
        if not video_path.exists():
            return None

    # Create video lane
    video_lane = VideoLane(
        video_path=video_path,
        context_dir=context_dir,
        thumbnail_size=thumbnail_size,
        sampling_interval=sampling_interval
    )

    return video_lane
