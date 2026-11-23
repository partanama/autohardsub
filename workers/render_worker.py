"""Non-blocking QThread worker for FFmpeg ASS subtitle burn-in and progress tracking."""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections import deque
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, QThread, Signal

from core.ass_engine import AssConfig, write_ass_file
from core.media_probe import VideoInfo
from core.paths import SUBPROCESS_NO_WINDOW, get_ffmpeg_path, get_fonts_dir
from core.presets import SubtitlePreset
from workers import iter_subprocess_lines

_TIME_RE = re.compile(r"time=(\d{2,}):(\d{2}):(\d{2}(?:\.\d+)?)")


def escape_ffmpeg_filter_path(path: str | Path) -> str:
    """Escape a filesystem path for FFmpeg libass filter arguments on Windows.

    Converts backslashes to forward slashes and escapes drive colons and single
    quotes so paths such as ``D:\\app\\sub.ass`` become ``D\\:/app/sub.ass``.
    """
    normalized = str(Path(path).resolve()).replace("\\", "/")
    normalized = normalized.replace(":", "\\:")
    normalized = normalized.replace("'", "\\'")
    return normalized


def _parse_ffmpeg_time_seconds(line: str) -> float | None:
    match = _TIME_RE.search(line)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return (hours * 3600.0) + (minutes * 60.0) + seconds


def _build_codec_args(encoder_name: str) -> tuple[list[str], str]:
    """Return FFmpeg video/audio codec flags and a human-readable encoder label."""
    if encoder_name == "h264_nvenc":
        return (
            [
                "-c:v",
                "h264_nvenc",
                "-bf",
                "0",
                "-preset",
                "p4",
                "-cq",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
            ],
            "GPU NVIDIA (NVENC)",
        )
    if encoder_name == "h264_qsv":
        return (
            [
                "-c:v",
                "h264_qsv",
                "-global_quality",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
            ],
            "GPU Intel (QuickSync)",
        )
    if encoder_name == "h264_mf":
        return (
            [
                "-c:v",
                "h264_mf",
                "-rate_control",
                "quality",
                "-quality",
                "80",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "copy",
            ],
            "GPU Windows (MediaFoundation)",
        )
    return (
        [
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
        ],
        "CPU (libx264)",
    )


class RenderWorker(QThread):
    """Generate a temporary ASS file and burn subtitles into video via FFmpeg."""

    progress_changed = Signal(int)
    status_changed = Signal(str)
    finished_success = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        video_info: VideoInfo,
        cues: list[dict],
        preset: SubtitlePreset,
        output_path: str,
        use_gpu: bool = False,
        encoder_name: str | None = None,
        font_size: int | None = None,
        margin_v: int | None = None,
        ass_config: AssConfig | None = None,
        ffmpeg_path: str | None = None,
        fonts_dir: Path | str | None = None,
        extra_temp_files: Iterable[str | Path] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._video_info = video_info
        self._cues = [dict(c) for c in cues]
        self._preset = preset
        self._output_path = output_path
        self._use_gpu = use_gpu
        self._encoder_name = encoder_name or ("h264_nvenc" if use_gpu else "libx264")
        self._font_size = font_size
        self._margin_v = margin_v
        self._ass_config = ass_config
        self._ffmpeg_path = ffmpeg_path
        self._fonts_dir = Path(fonts_dir) if fonts_dir else None
        self._extra_temp_files = [Path(p) for p in (extra_temp_files or ())]
        self._process: subprocess.Popen[bytes] | None = None
        self._cancelled = False

    def cancel(self) -> None:
        """Request cancellation and terminate the running FFmpeg process."""
        self._cancelled = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _cleanup_extra_temps(self) -> None:
        for temp_path in self._extra_temp_files:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _cleanup_incomplete_output(self) -> None:
        try:
            Path(self._output_path).unlink(missing_ok=True)
        except OSError:
            pass

    def run(self) -> None:
        try:
            ffmpeg_bin = self._ffmpeg_path or get_ffmpeg_path()
            if not ffmpeg_bin:
                self.error_occurred.emit(
                    "ffmpeg.exe tidak ditemukan. Letakkan di folder assets/bin/ "
                    "atau tambahkan ke PATH sistem."
                )
                return

            if not Path(self._video_info.path).is_file():
                self.error_occurred.emit(
                    f"File video sumber tidak ditemukan: {self._video_info.path}"
                )
                return

            if not self._cues:
                self.error_occurred.emit("Tidak ada baris subtitle untuk dirender.")
                return

            output_file = Path(self._output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.TemporaryDirectory(prefix="autohardsub_render_") as tmpdir:
                temp_ass = Path(tmpdir) / "subtitles.ass"
                self.status_changed.emit("Menyiapkan file subtitle ASS...")
                write_ass_file(
                    cues=self._cues,
                    preset=self._preset,
                    play_res_x=self._video_info.width,
                    play_res_y=self._video_info.height,
                    output_path=temp_ass,
                    font_size=self._font_size,
                    margin_v=self._margin_v,
                    ass_config=self._ass_config,
                )

                ass_escaped = escape_ffmpeg_filter_path(temp_ass)
                fonts_dir = self._fonts_dir or get_fonts_dir()
                if fonts_dir.is_dir():
                    fonts_escaped = escape_ffmpeg_filter_path(fonts_dir)
                    vf_filter = f"ass='{ass_escaped}':fontsdir='{fonts_escaped}'"
                else:
                    vf_filter = f"ass='{ass_escaped}'"

                codec_args, encoder_label = _build_codec_args(self._encoder_name)

                cmd = [
                    ffmpeg_bin,
                    "-y",
                    "-hide_banner",
                    "-i",
                    str(self._video_info.path),
                    "-vf",
                    vf_filter,
                    *codec_args,
                    "-movflags",
                    "+faststart",
                    str(output_file),
                ]

                self.progress_changed.emit(0)
                self.status_changed.emit(
                    f"Merender video dengan {encoder_label}... 0%"
                )

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    creationflags=SUBPROCESS_NO_WINDOW,
                )

                total_duration = max(0.01, float(self._video_info.duration_seconds))
                last_pct = 0
                tail_logs: deque[str] = deque(maxlen=30)

                for line in iter_subprocess_lines(self._process.stderr):
                    tail_logs.append(line)
                    if self._cancelled:
                        break
                    current_sec = _parse_ffmpeg_time_seconds(line)
                    if current_sec is not None:
                        pct = int(min(99, max(0, (current_sec / total_duration) * 100.0)))
                        if pct != last_pct:
                            last_pct = pct
                            self.progress_changed.emit(pct)
                            self.status_changed.emit(
                                f"Merender video dengan {encoder_label}... {pct}%"
                            )

                if self._cancelled and self._process.poll() is None:
                    try:
                        self._process.kill()
                    except OSError:
                        pass

                return_code = self._process.wait()
                self._process = None

                if self._cancelled:
                    self._cleanup_incomplete_output()
                    self.error_occurred.emit("Proses render dibatalkan.")
                    return

                if return_code != 0:
                    self._cleanup_incomplete_output()
                    detail = "\n".join(tail_logs) or f"Exit code {return_code}"
                    self.error_occurred.emit(
                        f"FFmpeg gagal merender video (kode {return_code}):\n{detail}"
                    )
                    return

                if not output_file.is_file():
                    self.error_occurred.emit(
                        "FFmpeg selesai tetapi file output video tidak ditemukan."
                    )
                    return

                self.progress_changed.emit(100)
                self.status_changed.emit("Export video hardsub selesai!")
                self.finished_success.emit(str(output_file))

        except OSError as exc:
            self._cleanup_incomplete_output()
            self.error_occurred.emit(f"Gagal menjalankan ffmpeg.exe: {exc}")
        except Exception as exc:
            self._cleanup_incomplete_output()
            self.error_occurred.emit(f"Kesalahan saat render video: {exc}")
        finally:
            self._process = None
            self._cleanup_extra_temps()
