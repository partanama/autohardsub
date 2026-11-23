"""Persistent user settings stored outside the app directory in %LOCALAPPDATA%."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from core.i18n import normalize_lang
from core.presets import PRESET_MAP, PRESETS

logger = logging.getLogger(__name__)

_VALID_ASPECTS = {"16:9", "9:16"}
_VALID_AUDIO_LANGS = {"auto", "id", "en"}
_VALID_MODELS = {"base", "small", "large-v3"}

DEFAULT_SETTINGS: dict[str, Any] = {
    "language": "en",
    "subtitle_style": PRESETS[0].id,
    "font_family": PRESETS[0].font_name,
    "font_size": PRESETS[0].default_font_size,
    "outline_width": float(PRESETS[0].outline),
    "font_color": PRESETS[0].primary_text_hex,
    "highlight_color": PRESETS[0].highlight_hex,
    "outline_color": PRESETS[0].outline_hex,
    "bg_box_color": PRESETS[0].bg_box_hex,
    "enable_bg_box": bool(PRESETS[0].bg_box_enabled),
    "box_opacity": int(PRESETS[0].bg_box_opacity),
    "vertical_margin": int(PRESETS[0].default_margin_v),
    "preview_aspect": "16:9",
    "whisper_model": "base",
    "audio_language": "auto",
}


def get_settings_path() -> Path:
    """Return the persistent user_settings.json path inside %LOCALAPPDATA%\\AutoHardsub."""
    base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(os.path.join(base_dir, "AutoHardsub", "user_settings.json"))


def _is_valid_hex_color(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    cleaned = value.strip()
    if len(cleaned) != 7 or not cleaned.startswith("#"):
        return False
    try:
        int(cleaned[1:], 16)
        return True
    except ValueError:
        return False


def _sanitize_settings(raw: Any) -> dict[str, Any]:
    """Validate and merge raw JSON data with defaults, ignoring missing or corrupt keys."""
    if not isinstance(raw, dict):
        return {}

    cleaned: dict[str, Any] = {}

    if "language" in raw and isinstance(raw["language"], str):
        cleaned["language"] = normalize_lang(raw["language"])

    if "subtitle_style" in raw and isinstance(raw["subtitle_style"], str):
        style_id = raw["subtitle_style"].strip()
        if style_id in PRESET_MAP:
            cleaned["subtitle_style"] = style_id

    if "font_family" in raw and isinstance(raw["font_family"], str):
        font_family = raw["font_family"].strip()
        if font_family:
            cleaned["font_family"] = font_family

    if "font_size" in raw:
        try:
            size = int(raw["font_size"])
            cleaned["font_size"] = max(16, min(150, size))
        except (TypeError, ValueError):
            pass

    if "outline_width" in raw:
        try:
            outline = float(raw["outline_width"])
            cleaned["outline_width"] = round(max(0.0, min(20.0, outline)), 1)
        except (TypeError, ValueError):
            pass

    for color_key in ("font_color", "highlight_color", "outline_color", "bg_box_color"):
        if color_key in raw and _is_valid_hex_color(raw[color_key]):
            cleaned[color_key] = str(raw[color_key]).strip().upper()

    if "enable_bg_box" in raw and isinstance(raw["enable_bg_box"], bool):
        cleaned["enable_bg_box"] = raw["enable_bg_box"]

    if "box_opacity" in raw:
        try:
            opacity = int(raw["box_opacity"])
            cleaned["box_opacity"] = max(0, min(100, opacity))
        except (TypeError, ValueError):
            pass

    if "vertical_margin" in raw:
        try:
            margin = int(raw["vertical_margin"])
            cleaned["vertical_margin"] = max(0, min(960, margin))
        except (TypeError, ValueError):
            pass

    if "preview_aspect" in raw and isinstance(raw["preview_aspect"], str):
        aspect = raw["preview_aspect"].strip()
        if aspect in _VALID_ASPECTS:
            cleaned["preview_aspect"] = aspect

    if "whisper_model" in raw and isinstance(raw["whisper_model"], str):
        model = raw["whisper_model"].strip()
        if model in _VALID_MODELS:
            cleaned["whisper_model"] = model

    if "audio_language" in raw and isinstance(raw["audio_language"], str):
        audio_lang = raw["audio_language"].strip().lower()
        if audio_lang in _VALID_AUDIO_LANGS:
            cleaned["audio_language"] = audio_lang

    return cleaned


def load_user_settings() -> dict[str, Any]:
    """Load and validate user settings from disk. Returns only valid saved keys (empty dict on miss/error)."""
    path = get_settings_path()
    if not path.is_file():
        return {}

    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not load user settings from %s: %s", path, exc)
        return {}

    return _sanitize_settings(data)


def save_user_settings(settings: dict[str, Any]) -> bool:
    """Atomically write validated user settings to %LOCALAPPDATA%\\AutoHardsub\\user_settings.json."""
    path = get_settings_path()
    payload = dict(DEFAULT_SETTINGS)
    payload.update(_sanitize_settings(settings))

    tmp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix="user_settings_",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            json.dump(payload, tmp_file, indent=2, ensure_ascii=False)
            tmp_file.write("\n")
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, path)
        return True
    except OSError as exc:
        logger.warning("Could not save user settings to %s: %s", path, exc)
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        return False
