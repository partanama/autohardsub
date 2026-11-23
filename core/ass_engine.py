"""JSON-to-ASS subtitle generator with proportional word-timing estimation and style overrides."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.presets import SubtitlePreset

_PUNCT_STRIP = ".,!?;:\"'()[]{}-"


@dataclass(frozen=True)
class TimedWord:
    """A single word with estimated start and end timestamps in seconds."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class AssConfig:
    """Custom subtitle styling overrides applied on top of a SubtitlePreset."""

    font_name: str | None = None
    font_size: int | None = None
    margin_v: int | None = None
    outline_width: float | None = None
    primary_text_color: str | None = None  # RGB hex "#RRGGBB"
    highlight_color: str | None = None  # RGB hex "#RRGGBB"
    outline_color: str | None = None  # RGB hex "#RRGGBB"
    enable_bg_box: bool | None = None  # True -> BorderStyle=3, False -> BorderStyle=1
    bg_box_color: str | None = None  # RGB hex "#RRGGBB"
    bg_box_opacity: int | None = None  # 0 (transparent) .. 100 (solid opaque)


def hex_to_ass_color(hex_rgb: str, alpha: int = 0) -> str:
    """Convert standard RGB hex (``#RRGGBB``) and ASS alpha (0=opaque..255=transparent) to ``&HAABBGGRR``."""
    cleaned = str(hex_rgb).strip().lstrip("#")
    if len(cleaned) == 3:
        cleaned = "".join(ch * 2 for ch in cleaned)
    if len(cleaned) != 6:
        raise ValueError(f"Format warna hex RGB tidak valid: {hex_rgb!r}")
    try:
        r = int(cleaned[0:2], 16)
        g = int(cleaned[2:4], 16)
        b = int(cleaned[4:6], 16)
    except ValueError as exc:
        raise ValueError(f"Format warna hex RGB tidak valid: {hex_rgb!r}") from exc

    clamped_alpha = max(0, min(255, int(alpha)))
    return f"&H{clamped_alpha:02X}{b:02X}{g:02X}{r:02X}"


def opacity_percent_to_ass_alpha(opacity_pct: int) -> int:
    """Convert UI opacity percentage (0%=transparent, 100%=opaque) to ASS alpha (255..0)."""
    clamped = max(0, min(100, int(opacity_pct)))
    return max(0, min(255, int(round((100 - clamped) * 255 / 100.0))))


def format_ass_time(seconds: float) -> str:
    """Format seconds into ASS timestamp ``H:MM:SS.cc`` without centisecond overflow."""
    total_cs = max(0, int(round(float(seconds) * 100)))
    cs = total_cs % 100
    total_sec = total_cs // 100
    sec = total_sec % 60
    total_min = total_sec // 60
    minute = total_min % 60
    hour = total_min // 60
    return f"{hour}:{minute:02d}:{sec:02d}.{cs:02d}"


def escape_ass_text(text: str) -> str:
    """Normalize whitespace and neutralize ASS control characters in plain text."""
    normalized = " ".join(str(text).split())
    # Prevent accidental \n, \N, \h or {...} override tag parsing from user text.
    escaped = normalized.replace("\\", "\\\u200b")
    escaped = escaped.replace("{", "(").replace("}", ")")
    return escaped


def estimate_word_timings(start: float, end: float, text: str) -> list[TimedWord]:
    """Split a cue into words and allocate duration proportionally by character length."""
    words = [w for w in str(text).split() if w]
    if not words:
        return []

    safe_start = max(0.0, float(start))
    safe_end = max(safe_start + 0.1, float(end))
    total_dur = safe_end - safe_start

    if len(words) == 1:
        return [TimedWord(text=words[0], start=safe_start, end=safe_end)]

    gap = min(0.03, (total_dur * 0.15) / (len(words) - 1))
    speaking_dur = max(0.05 * len(words), total_dur - gap * (len(words) - 1))

    weights = [max(1, len(w.strip(_PUNCT_STRIP)) or len(w)) for w in words]
    total_weight = sum(weights)

    timed: list[TimedWord] = []
    cursor = safe_start
    for idx, (word, weight) in enumerate(zip(words, weights)):
        word_dur = speaking_dur * (weight / total_weight)
        word_end = safe_end if idx == len(words) - 1 else min(safe_end, cursor + word_dur)
        if word_end <= cursor:
            word_end = min(safe_end, cursor + 0.01)
        timed.append(TimedWord(text=word, start=cursor, end=word_end))
        cursor = word_end + gap

    return timed


def split_into_chunks(words: list[TimedWord], max_words: int) -> list[list[TimedWord]]:
    """Split timed words into balanced readable chunks without 1-word orphans."""
    if not words:
        return []
    limit = max(1, int(max_words))
    if len(words) <= limit:
        return [words]

    num_chunks = math.ceil(len(words) / limit)
    base_size, remainder = divmod(len(words), num_chunks)

    chunks: list[list[TimedWord]] = []
    idx = 0
    for chunk_idx in range(num_chunks):
        size = base_size + (1 if chunk_idx < remainder else 0)
        chunks.append(words[idx : idx + size])
        idx += size
    return chunks


def _allocate_karaoke_centiseconds(chunk: list[TimedWord]) -> list[int]:
    """Compute integer centisecond durations matching word onset slots across the chunk."""
    chunk_start_cs = max(0, int(round(chunk[0].start * 100)))
    chunk_end_cs = max(chunk_start_cs + len(chunk), int(round(chunk[-1].end * 100)))
    total_cs = chunk_end_cs - chunk_start_cs

    raw_durations: list[float] = []
    for idx, word in enumerate(chunk):
        slot_end = chunk[idx + 1].start if idx + 1 < len(chunk) else word.end
        raw_durations.append(max(0.01, slot_end - word.start))

    raw_sum = sum(raw_durations) or float(len(chunk))

    cs_list = [max(1, int(round((dur / raw_sum) * total_cs))) for dur in raw_durations]
    diff = total_cs - sum(cs_list)
    if diff != 0:
        # Adjust the longest word first so timing discrepancy stays imperceptible.
        target_idx = max(range(len(cs_list)), key=lambda i: cs_list[i])
        cs_list[target_idx] = max(1, cs_list[target_idx] + diff)
    return cs_list


def resolve_cue_word_timings(
    start: float,
    end: float,
    text: str,
    words_meta: list[dict] | None = None,
) -> list[TimedWord]:
    """Resolve word-level timings using Whisper metadata while respecting user edits."""
    edited_words = [w for w in str(text).split() if w]
    if not edited_words:
        return []

    safe_start = max(0.0, float(start))
    safe_end = max(safe_start + 0.1, float(end))

    if not words_meta:
        return estimate_word_timings(safe_start, safe_end, text)

    orig_words: list[TimedWord] = []
    for item in words_meta:
        if not isinstance(item, dict):
            continue
        w_text = str(item.get("word", "")).strip()
        if not w_text:
            continue
        try:
            w_start = max(0.0, float(item.get("start", safe_start)))
            w_end = float(item.get("end", w_start))
        except (TypeError, ValueError):
            continue
        if orig_words and w_start < orig_words[-1].start:
            w_start = orig_words[-1].start
        if w_end < w_start + 0.02:
            w_end = w_start + 0.02
        orig_words.append(TimedWord(text=w_text, start=w_start, end=w_end))

    if not orig_words:
        return estimate_word_timings(safe_start, safe_end, text)

    orig_start = orig_words[0].start
    orig_end = orig_words[-1].end

    # If user shifted cue bounds so original words fall outside [start, end], re-estimate.
    if orig_start < safe_start - 0.15 or orig_end > safe_end + 0.15:
        return estimate_word_timings(safe_start, safe_end, text)

    if len(edited_words) == len(orig_words):
        resolved: list[TimedWord] = []
        for ed_word, orig in zip(edited_words, orig_words):
            clamped_start = max(safe_start, min(orig.start, safe_end - 0.02))
            clamped_end = min(safe_end, max(clamped_start + 0.02, orig.end))
            if resolved and clamped_start < resolved[-1].start:
                clamped_start = resolved[-1].start
                clamped_end = max(clamped_start + 0.02, clamped_end)
            resolved.append(TimedWord(text=ed_word, start=clamped_start, end=clamped_end))
        return resolved

    bound_start = max(safe_start, orig_start)
    bound_end = min(safe_end, orig_end)
    if bound_end <= bound_start + 0.05:
        return estimate_word_timings(safe_start, safe_end, text)
    return estimate_word_timings(bound_start, bound_end, text)


def _build_dialogue_line(start: float, end: float, text: str) -> str:
    return f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},Default,,0,0,0,,{text}"


def _resolve_effective_style(
    preset: SubtitlePreset,
    ass_config: AssConfig | None,
    font_size: int | None,
    margin_v: int | None,
    font_name: str | None,
) -> dict[str, object]:
    """Merge SubtitlePreset defaults with optional AssConfig overrides."""
    cfg = ass_config or AssConfig()

    chosen_font = cfg.font_name or font_name or preset.font_name
    chosen_size = max(
        12,
        int(
            cfg.font_size
            if cfg.font_size is not None
            else (font_size if font_size is not None else preset.default_font_size)
        ),
    )
    chosen_margin_v = max(
        0,
        int(
            cfg.margin_v
            if cfg.margin_v is not None
            else (margin_v if margin_v is not None else preset.default_margin_v)
        ),
    )
    chosen_outline = max(
        0.0,
        float(cfg.outline_width if cfg.outline_width is not None else preset.outline),
    )

    primary_text_ass = (
        hex_to_ass_color(cfg.primary_text_color, 0)
        if cfg.primary_text_color
        else hex_to_ass_color(preset.primary_text_hex, 0)
    )
    highlight_ass = (
        hex_to_ass_color(cfg.highlight_color, 0)
        if cfg.highlight_color
        else preset.highlight_colour
    )

    if preset.animation_mode == "karaoke_wipe":
        # In ASS \kf karaoke, SecondaryColour is initial text and PrimaryColour is filled highlight.
        style_primary = highlight_ass
        style_secondary = primary_text_ass
    else:
        style_primary = primary_text_ass
        style_secondary = primary_text_ass

    bg_box_enabled = (
        cfg.enable_bg_box if cfg.enable_bg_box is not None else preset.bg_box_enabled
    )

    if bg_box_enabled:
        bg_hex = cfg.bg_box_color or preset.bg_box_hex
        bg_opacity = (
            cfg.bg_box_opacity if cfg.bg_box_opacity is not None else preset.bg_box_opacity
        )
        bg_alpha = opacity_percent_to_ass_alpha(bg_opacity)
        box_ass = hex_to_ass_color(bg_hex, bg_alpha)
        border_style = 3
        style_outline_colour = box_ass
        style_back_colour = box_ass
        style_shadow = 0.0
    else:
        outline_hex = cfg.outline_color or preset.outline_hex
        border_style = 1
        style_outline_colour = hex_to_ass_color(outline_hex, 0)
        style_back_colour = "&H80000000"
        style_shadow = preset.shadow if preset.shadow > 0 else 2.0

    return {
        "font_name": chosen_font,
        "font_size": chosen_size,
        "margin_v": chosen_margin_v,
        "outline": chosen_outline,
        "shadow": style_shadow,
        "border_style": border_style,
        "primary_colour": style_primary,
        "secondary_colour": style_secondary,
        "outline_colour": style_outline_colour,
        "back_colour": style_back_colour,
        "base_text_ass": primary_text_ass,
        "highlight_ass": highlight_ass,
    }


def _render_chunk_events(
    chunk: list[TimedWord],
    preset: SubtitlePreset,
    base_text_ass: str,
    highlight_ass: str,
) -> list[str]:
    mode = preset.animation_mode
    chunk_start = chunk[0].start
    chunk_end = max(chunk_start + 0.05, chunk[-1].end)

    if mode in ("static", "box"):
        line_text = " ".join(escape_ass_text(w.text) for w in chunk)
        return [_build_dialogue_line(chunk_start, chunk_end, line_text)]

    if mode == "karaoke_wipe":
        cs_durations = _allocate_karaoke_centiseconds(chunk)
        parts = []
        for idx, (word, cs) in enumerate(zip(chunk, cs_durations)):
            escaped = escape_ass_text(word.text)
            suffix = " " if idx < len(chunk) - 1 else ""
            parts.append(f"{{\\kf{cs}}}{escaped}{suffix}")
        return [_build_dialogue_line(chunk_start, chunk_end, "".join(parts))]

    if mode == "word_pop":
        events: list[str] = []
        for active_idx, active_word in enumerate(chunk):
            step_start = active_word.start
            step_end = (
                chunk[active_idx + 1].start
                if active_idx + 1 < len(chunk)
                else active_word.end
            )
            if step_end <= step_start + 0.01:
                step_end = step_start + 0.02

            word_ms = max(40, int(round((active_word.end - active_word.start) * 1000)))
            bounce_ms = min(140, max(40, int(round(word_ms * 0.45))))

            tokens: list[str] = []
            for idx, word in enumerate(chunk):
                escaped = escape_ass_text(word.text)
                if idx == active_idx:
                    tokens.append(
                        f"{{\\1c{highlight_ass}&\\fscx118\\fscy118"
                        f"\\t(0,{bounce_ms},\\fscx100\\fscy100)}}"
                        f"{escaped}"
                        f"{{\\1c{base_text_ass}&\\fscx100\\fscy100}}"
                    )
                else:
                    tokens.append(escaped)

            events.append(_build_dialogue_line(step_start, step_end, " ".join(tokens)))
        return events

    line_text = " ".join(escape_ass_text(w.text) for w in chunk)
    return [_build_dialogue_line(chunk_start, chunk_end, line_text)]


def generate_ass_content(
    cues: Iterable[dict],
    preset: SubtitlePreset,
    play_res_x: int,
    play_res_y: int,
    font_size: int | None = None,
    margin_v: int | None = None,
    font_name: str | None = None,
    ass_config: AssConfig | None = None,
) -> str:
    """Build complete ASS v4+ script content adapted to video resolution, preset, and custom overrides."""
    res_x = max(16, int(play_res_x))
    res_y = max(16, int(play_res_y))

    style = _resolve_effective_style(
        preset=preset,
        ass_config=ass_config,
        font_size=font_size,
        margin_v=margin_v,
        font_name=font_name,
    )

    # Vertical 9:16 videos fit fewer words per line than 16:9 horizontal videos.
    max_words_per_chunk = 4 if res_y > res_x else 9

    header_lines = [
        "[Script Info]",
        "Title: AutoHardsub Generated Subtitles",
        "ScriptType: v4.00+",
        f"PlayResX: {res_x}",
        f"PlayResY: {res_y}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Default,{style['font_name']},{style['font_size']},"
            f"{style['primary_colour']},{style['secondary_colour']},"
            f"{style['outline_colour']},{style['back_colour']},"
            f"{preset.bold},0,0,0,100,100,0,0,"
            f"{style['border_style']},{style['outline']},{style['shadow']},"
            f"{preset.alignment},{preset.margin_l},{preset.margin_r},{style['margin_v']},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    valid_cues: list[tuple[float, float, str, list[dict] | None]] = []
    for cue in cues:
        text = str(cue.get("text", "")).strip()
        if not text:
            continue
        try:
            start = max(0.0, float(cue.get("start", 0.0)))
            end = float(cue.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        if end <= start:
            end = start + 0.5
        words_meta = cue.get("words")
        if not isinstance(words_meta, list):
            words_meta = None
        valid_cues.append((start, end, text, words_meta))

    valid_cues.sort(key=lambda item: (item[0], item[1]))

    event_lines: list[str] = []
    base_text_ass = str(style["base_text_ass"])
    highlight_ass = str(style["highlight_ass"])
    for start, end, text, words_meta in valid_cues:
        timed_words = resolve_cue_word_timings(start, end, text, words_meta)
        for chunk in split_into_chunks(timed_words, max_words_per_chunk):
            event_lines.extend(
                _render_chunk_events(chunk, preset, base_text_ass, highlight_ass)
            )

    return "\n".join([*header_lines, *event_lines]) + "\n"


def write_ass_file(
    cues: Iterable[dict],
    preset: SubtitlePreset,
    play_res_x: int,
    play_res_y: int,
    output_path: str | Path,
    font_size: int | None = None,
    margin_v: int | None = None,
    font_name: str | None = None,
    ass_config: AssConfig | None = None,
) -> Path:
    """Generate and write an ASS subtitle file using UTF-8 with BOM (utf-8-sig)."""
    content = generate_ass_content(
        cues=cues,
        preset=preset,
        play_res_x=play_res_x,
        play_res_y=play_res_y,
        font_size=font_size,
        margin_v=margin_v,
        font_name=font_name,
        ass_config=ass_config,
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write(content)
    return target
