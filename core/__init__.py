"""Core engines for path resolution, hardware probing, media inspection, and ASS generation."""

from core.ass_engine import (
    TimedWord,
    escape_ass_text,
    estimate_word_timings,
    format_ass_time,
    generate_ass_content,
    resolve_cue_word_timings,
    split_into_chunks,
    write_ass_file,
)
from core.hw_detect import HardwareProfile, detect_hardware
from core.media_probe import MediaProbeError, VideoInfo, probe_video
from core.paths import (
    SUBPROCESS_NO_WINDOW,
    get_app_root,
    get_binary_status,
    get_bundle_root,
    get_ffmpeg_path,
    get_ffprobe_path,
    get_fonts_dir,
    get_models_dir,
    get_opencaption_path,
    get_whisper_cli_path,
    resolve_binary,
)
from core.presets import PRESETS, PRESET_MAP, SubtitlePreset, get_preset

__all__ = [
    "HardwareProfile",
    "MediaProbeError",
    "PRESETS",
    "PRESET_MAP",
    "SUBPROCESS_NO_WINDOW",
    "SubtitlePreset",
    "TimedWord",
    "VideoInfo",
    "detect_hardware",
    "escape_ass_text",
    "estimate_word_timings",
    "format_ass_time",
    "generate_ass_content",
    "get_app_root",
    "get_binary_status",
    "get_bundle_root",
    "get_ffmpeg_path",
    "get_ffprobe_path",
    "get_fonts_dir",
    "get_models_dir",
    "get_opencaption_path",
    "get_preset",
    "get_whisper_cli_path",
    "probe_video",
    "resolve_binary",
    "resolve_cue_word_timings",
    "split_into_chunks",
    "write_ass_file",
]
