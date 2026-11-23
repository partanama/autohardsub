"""Hardware acceleration detector for multi-GPU encoding, Vulkan transcription, and CPU fallback."""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.paths import (
    SUBPROCESS_NO_WINDOW,
    get_ffmpeg_path,
    get_opencaption_path,
    get_whisper_cli_path,
)

logger = logging.getLogger(__name__)

_VULKAN_COUNT_RE = re.compile(r"ggml_vulkan:\s*Found\s+(\d+)\s+Vulkan\s+device", re.IGNORECASE)
_VULKAN_DEVICE_RE = re.compile(r"ggml_vulkan:\s*\d+\s*=\s*([^|\r\n]+)", re.IGNORECASE)

# Priority cascade: (encoder_name, extra_probe_args, display_label, mode_key)
_ENCODER_CASCADE: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    ("h264_nvenc", ("-bf", "0"), "GPU NVIDIA (NVENC)", "nvenc"),
    ("h264_qsv", (), "GPU Intel (QuickSync)", "qsv"),
    ("h264_mf", (), "GPU Windows (MediaFoundation)", "mf"),
)


@dataclass(frozen=True)
class HardwareProfile:
    """Detected encoding and transcription acceleration capabilities."""

    use_gpu: bool
    encoder_name: str
    opencaption_device: str
    status_label: str
    detail: str = ""
    vulkan_available: bool = False
    vulkan_devices: tuple[str, ...] = ()
    mode_key: str = "cpu"  # "nvenc", "qsv", "mf", "vulkan_cpu", or "cpu"
    render_label: str = "CPU"


def _probe_encoder(
    ffmpeg_bin: str,
    encoder_name: str,
    extra_args: tuple[str, ...],
    timeout: float,
) -> tuple[bool, str]:
    """Probe a single FFmpeg H.264 hardware encoder using a 256x256 test frame."""
    probe_cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=256x256:d=0.1",
        "-c:v",
        encoder_name,
        *extra_args,
        "-f",
        "null",
        "-",
    ]

    try:
        result = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=SUBPROCESS_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        msg = f"{encoder_name}: probe timeout."
        logger.warning("Encoder probe timeout for %s (%s)", encoder_name, ffmpeg_bin)
        return False, msg
    except OSError as exc:
        msg = f"{encoder_name}: gagal menjalankan pemeriksaan ({exc})."
        logger.warning("Encoder probe OS error for %s: %s", encoder_name, exc)
        return False, msg

    stderr_text = (result.stderr or "").strip()
    if result.returncode == 0:
        extra_str = f" ({' '.join(extra_args)})" if extra_args else ""
        logger.info("Encoder probe succeeded: %s using %s", encoder_name, ffmpeg_bin)
        return True, f"Hardware encoding {encoder_name} aktif{extra_str}."

    if stderr_text:
        logger.info(
            "Encoder probe failed for %s (rc=%s): %s",
            encoder_name,
            result.returncode,
            stderr_text,
        )
        first_meaningful = next(
            (line.strip() for line in stderr_text.splitlines() if line.strip()),
            f"{encoder_name} tidak tersedia.",
        )
    else:
        logger.info(
            "Encoder probe failed for %s (rc=%s) with empty stderr.",
            encoder_name,
            result.returncode,
        )
        first_meaningful = f"{encoder_name} tidak tersedia (kode {result.returncode})."
    return False, f"{encoder_name}: {first_meaningful}"


def _probe_encoder_cascade(
    ffmpeg_bin: str | None,
    timeout: float,
) -> tuple[str, str, str, bool, list[str]]:
    """Probe hardware encoders in priority order: NVENC -> QSV -> MF -> libx264."""
    if not ffmpeg_bin or not Path(ffmpeg_bin).is_file():
        msg = "FFmpeg tidak ditemukan; menggunakan mode CPU (libx264)."
        logger.warning("Hardware encoder cascade skipped: %s", msg)
        return "libx264", "CPU", "cpu", False, [msg]

    notes: list[str] = []
    for encoder_name, extra_args, display_label, mode_key in _ENCODER_CASCADE:
        ok, detail = _probe_encoder(
            ffmpeg_bin=ffmpeg_bin,
            encoder_name=encoder_name,
            extra_args=extra_args,
            timeout=timeout,
        )
        notes.append(detail)
        if ok:
            return encoder_name, display_label, mode_key, True, notes

    notes.append("Fallback ke software encoding libx264 (CPU).")
    return "libx264", "CPU", "cpu", False, notes


def _probe_vulkan(
    whisper_cli_bin: str | None,
    opencaption_bin: str | None,
    timeout: float,
) -> tuple[bool, tuple[str, ...], str]:
    """Probe whisper-cli / opencaption independently for Vulkan GPU support."""
    candidates: list[tuple[str, str]] = []
    if whisper_cli_bin and Path(whisper_cli_bin).is_file():
        candidates.append(("whisper-cli", whisper_cli_bin))
    if opencaption_bin and Path(opencaption_bin).is_file():
        candidates.append(("opencaption", opencaption_bin))

    for label, binary in candidates:
        try:
            result = subprocess.run(
                [binary, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=SUBPROCESS_NO_WINDOW,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Vulkan probe timeout for %s (%s)", label, binary)
            continue
        except OSError as exc:
            logger.warning("Vulkan probe OS error for %s: %s", label, exc)
            continue

        combined = "\n".join(
            part for part in ((result.stderr or "").strip(), (result.stdout or "").strip()) if part
        )
        if result.stderr and result.stderr.strip():
            logger.debug("Vulkan probe stderr (%s): %s", label, result.stderr.strip())

        devices = tuple(
            m.group(1).strip() for m in _VULKAN_DEVICE_RE.finditer(combined) if m.group(1).strip()
        )
        count_match = _VULKAN_COUNT_RE.search(combined)
        device_count = int(count_match.group(1)) if count_match else len(devices)

        if device_count > 0 or devices:
            dev_summary = ", ".join(devices) if devices else f"{device_count} Vulkan device(s)"
            logger.info("Vulkan GPU detected via %s: %s", label, dev_summary)
            return True, devices, f"Vulkan aktif ({label}): {dev_summary}"

        # Secondary check for builds where ggml-vulkan.dll is colocated and vulkan is mentioned.
        bin_dir = Path(binary).parent
        if (bin_dir / "ggml-vulkan.dll").is_file() and "vulkan" in combined.lower():
            logger.info("Vulkan support detected via %s and ggml-vulkan.dll", label)
            return True, (), f"Vulkan aktif ({label})."

    return False, (), ""


def detect_hardware(
    ffmpeg_path: str | None = None,
    whisper_cli_path: str | None = None,
    opencaption_path: str | None = None,
    timeout: float = 8.0,
) -> HardwareProfile:
    """Detect multi-GPU render encoding (NVENC -> QSV -> MF -> CPU) and Vulkan transcription.

    Probes the resolved ``ffmpeg.exe`` from ``core/paths.py`` with a 256x256
    test frame across ``h264_nvenc`` (with ``-bf 0``), ``h264_qsv``, and
    ``h264_mf`` before falling back to ``libx264``, and independently probes
    ``whisper-cli.exe`` / ``opencaption.exe`` for Vulkan GPU support.
    """
    ffmpeg_bin = ffmpeg_path or get_ffmpeg_path()
    whisper_cli_bin = whisper_cli_path or get_whisper_cli_path()
    opencaption_bin = opencaption_path or get_opencaption_path()

    encoder_name, render_label, render_mode, use_gpu, encoder_notes = _probe_encoder_cascade(
        ffmpeg_bin, timeout=timeout
    )
    vulkan_ok, vulkan_devices, vulkan_detail = _probe_vulkan(
        whisper_cli_bin, opencaption_bin, timeout=timeout
    )

    detail_parts = [*encoder_notes]
    if vulkan_detail:
        detail_parts.append(vulkan_detail)
    combined_detail = "\n".join(part for part in detail_parts if part)

    transcribe_label = "GPU Vulkan" if vulkan_ok else "CPU"
    if use_gpu:
        mode_key = render_mode
        status_label = (
            f"Mode Performa: {transcribe_label} (Transkrip) + {render_label} (Render)"
        )
    elif vulkan_ok:
        mode_key = "vulkan_cpu"
        status_label = "Mode Performa: GPU Vulkan (Transkrip) + CPU (Render)"
    else:
        mode_key = "cpu"
        status_label = "Mode Performa: CPU Standard"

    opencaption_device = "auto" if (vulkan_ok or encoder_name == "h264_nvenc") else "cpu"

    return HardwareProfile(
        use_gpu=use_gpu,
        encoder_name=encoder_name,
        opencaption_device=opencaption_device,
        status_label=status_label,
        detail=combined_detail,
        vulkan_available=vulkan_ok,
        vulkan_devices=vulkan_devices,
        mode_key=mode_key,
        render_label=render_label,
    )
