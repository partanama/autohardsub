"""Video metadata probing via ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.paths import SUBPROCESS_NO_WINDOW, get_ffprobe_path


class MediaProbeError(RuntimeError):
    """Raised when ffprobe fails to inspect a media file."""


@dataclass(frozen=True)
class VideoInfo:
    """Normalized metadata for an input video file."""

    path: str
    width: int
    height: int
    duration_seconds: float
    fps: float | None = None
    has_audio: bool = True

    @property
    def is_vertical(self) -> bool:
        return self.height > self.width

    @property
    def orientation_label(self) -> str:
        if self.height > self.width:
            return "Vertikal (9:16)"
        if self.height == self.width:
            return "Persegi (1:1)"
        return "Horizontal (16:9)"


def _parse_fps(rate_str: str | None) -> float | None:
    if not rate_str:
        return None
    rate_str = rate_str.strip()
    if "/" in rate_str:
        num_s, den_s = rate_str.split("/", 1)
        try:
            num = float(num_s)
            den = float(den_s)
            if den > 0 and num > 0:
                return num / den
        except ValueError:
            return None
    try:
        val = float(rate_str)
        return val if val > 0 else None
    except ValueError:
        return None


def _extract_rotation_degrees(video_stream: dict) -> int:
    tags = video_stream.get("tags") or {}
    raw_rotate = tags.get("rotate")
    if raw_rotate is not None:
        try:
            return int(round(float(raw_rotate)))
        except (TypeError, ValueError):
            pass

    for side_data in video_stream.get("side_data_list") or []:
        if "rotation" in side_data:
            try:
                return int(round(float(side_data["rotation"])))
            except (TypeError, ValueError):
                pass
    return 0


def probe_video(
    video_path: str | Path,
    ffprobe_path: str | None = None,
    timeout: float = 15.0,
) -> VideoInfo:
    """Inspect video width, height, duration, and audio presence with ffprobe."""
    target = Path(video_path)
    if not target.is_file():
        raise MediaProbeError(f"File video tidak ditemukan: {target}")

    ffprobe_bin = ffprobe_path or get_ffprobe_path()
    if not ffprobe_bin:
        raise MediaProbeError(
            "ffprobe.exe tidak ditemukan di assets/bin/ maupun PATH sistem."
        )

    cmd = [
        ffprobe_bin,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(target),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=SUBPROCESS_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError("ffprobe kehabisan waktu saat membaca video.") from exc
    except OSError as exc:
        raise MediaProbeError(f"Gagal menjalankan ffprobe: {exc}") from exc

    if result.returncode != 0:
        err_msg = (result.stderr or "").strip() or f"exit code {result.returncode}"
        raise MediaProbeError(f"ffprobe gagal membaca video: {err_msg}")

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise MediaProbeError("Output JSON dari ffprobe tidak valid.") from exc

    streams = payload.get("streams") or []
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise MediaProbeError("File ini tidak memiliki stream video yang valid.")

    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    try:
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
    except (TypeError, ValueError) as exc:
        raise MediaProbeError("Dimensi video tidak valid.") from exc

    # Match visual dimensions after FFmpeg auto-rotates smartphone footage.
    rotation = _extract_rotation_degrees(video_stream)
    if abs(rotation) % 180 == 90:
        width, height = height, width

    if width <= 0 or height <= 0:
        raise MediaProbeError("Resolusi video (width/height) tidak terbaca.")

    fmt = payload.get("format") or {}
    raw_duration = fmt.get("duration") or video_stream.get("duration")
    try:
        duration_seconds = float(raw_duration) if raw_duration is not None else 0.0
    except (TypeError, ValueError) as exc:
        raise MediaProbeError("Durasi video tidak valid.") from exc

    if duration_seconds <= 0:
        raise MediaProbeError("Durasi video harus lebih besar dari 0 detik.")

    fps = _parse_fps(video_stream.get("avg_frame_rate")) or _parse_fps(
        video_stream.get("r_frame_rate")
    )

    return VideoInfo(
        path=str(target),
        width=width,
        height=height,
        duration_seconds=duration_seconds,
        fps=fps,
        has_audio=has_audio,
    )
