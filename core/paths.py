"""Path and binary resolution utilities for development and PyInstaller builds."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Suppress console window popups when invoking CLI tools on Windows.
SUBPROCESS_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}


def is_frozen() -> bool:
    """Return True when running inside a PyInstaller frozen executable."""
    return bool(getattr(sys, "frozen", False))


def get_bundle_root() -> Path:
    """Return the read-only bundle root (sys._MEIPASS when frozen, repo root in dev)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parent.parent


def get_app_root() -> Path:
    """Return the writable application root directory."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_bin_dirs() -> list[Path]:
    """Return candidate directories for bundled executables in priority order."""
    candidates = [
        get_app_root() / "assets" / "bin",
        get_bundle_root() / "assets" / "bin",
    ]
    unique_dirs: list[Path] = []
    for path in candidates:
        if path not in unique_dirs:
            unique_dirs.append(path)
    return unique_dirs


def _dir_has_fonts(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    try:
        return any(
            entry.is_file() and entry.suffix.lower() in _FONT_EXTENSIONS
            for entry in directory.iterdir()
        )
    except OSError:
        return False


def get_fonts_dir() -> Path:
    """Return the directory containing bundled .ttf/.otf subtitle fonts."""
    app_fonts = get_app_root() / "assets" / "fonts"
    bundle_fonts = get_bundle_root() / "assets" / "fonts"

    if _dir_has_fonts(app_fonts):
        return app_fonts
    if _dir_has_fonts(bundle_fonts) or bundle_fonts.is_dir():
        return bundle_fonts

    app_fonts.mkdir(parents=True, exist_ok=True)
    return app_fonts


def get_models_dir() -> Path:
    """Return the writable directory for Whisper models, creating it if missing."""
    primary = get_app_root() / "assets" / "models"
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except OSError:
        fallback = Path.home() / ".autohardsub" / "models"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def resolve_binary(name: str) -> str | None:
    """Resolve an executable from assets/bin/ first, then fall back to system PATH."""
    base_name = name[:-4] if name.lower().endswith(".exe") else name
    filenames = (
        [f"{base_name}.exe", base_name]
        if os.name == "nt"
        else [base_name, f"{base_name}.exe"]
    )

    for bin_dir in get_bin_dirs():
        if not bin_dir.is_dir():
            continue
        for filename in filenames:
            candidate = bin_dir / filename
            if candidate.is_file():
                return str(candidate)

    for filename in filenames:
        found = shutil.which(filename)
        if found:
            return found

    return None


def get_whisper_cli_path() -> str | None:
    """Resolve the path to whisper-cli(.exe)."""
    return resolve_binary("whisper-cli")


def get_opencaption_path() -> str | None:
    """Resolve the path to opencaption(.exe)."""
    return resolve_binary("opencaption")


def get_ffmpeg_path() -> str | None:
    """Resolve the path to ffmpeg(.exe)."""
    return resolve_binary("ffmpeg")


def get_ffprobe_path() -> str | None:
    """Resolve the path to ffprobe(.exe)."""
    return resolve_binary("ffprobe")


def get_binary_status() -> dict[str, str | None]:
    """Return resolved paths (or None) for all required external binaries."""
    return {
        "whisper_cli": get_whisper_cli_path(),
        "opencaption": get_opencaption_path(),
        "ffmpeg": get_ffmpeg_path(),
        "ffprobe": get_ffprobe_path(),
    }
