"""JSON-to-ASS subtitle generator with proportional word-timing estimation and style overrides."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from core.paths import get_fonts_dir
from core.presets import SubtitlePreset

_PUNCT_STRIP = ".,!?;:\"'()[]{}-"
_BEZIER_CIRCLE_K = 0.55228475
_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
_BUNDLED_FONTS_LOADED = False
_HEADLESS_QT_APP: object | None = None

_NEWSPAPER_PAPER_BGR = "&HE2E2E2&"
_NEWSPAPER_EMPH_TEXT_BGR = "&HF5F5F5&"
_NEWSPAPER_TILT_DEG = 1.6
_NEWSPAPER_PAUSE_GAP_SEC = 0.220
_NEWSPAPER_STAGGER_FALLBACK_SEC = 0.07
_NEWSPAPER_POPUP_TAGS = (
    "\\fscx60\\fscy60\\t(0,80,\\fscx110\\fscy110)\\t(80,140,\\fscx100\\fscy100)"
)
_NEWSPAPER_ID_TIME_WORDS = frozenset(
    {
        "senin",
        "selasa",
        "rabu",
        "kamis",
        "jumat",
        "jum'at",
        "sabtu",
        "minggu",
        "januari",
        "februari",
        "maret",
        "april",
        "mei",
        "juni",
        "juli",
        "agustus",
        "september",
        "oktober",
        "november",
        "desember",
    }
)
_NEWSPAPER_STOPWORDS = frozenset(
    {
        # Indonesian common stopwords
        "di",
        "ke",
        "dari",
        "yang",
        "dan",
        "atau",
        "ini",
        "itu",
        "luar",
        "dalam",
        "pada",
        "untuk",
        "dengan",
        "oleh",
        "sebagai",
        "adalah",
        "akan",
        "telah",
        "sudah",
        "belum",
        "tidak",
        "tak",
        "bukan",
        "juga",
        "pun",
        "saja",
        "hanya",
        "karena",
        "sebab",
        "jika",
        "kalau",
        "bila",
        "saat",
        "ketika",
        "waktu",
        "sementara",
        "agar",
        "supaya",
        "bahwa",
        "namun",
        "tetapi",
        "tapi",
        "melainkan",
        "sedangkan",
        "bahkan",
        "lalu",
        "kemudian",
        "serta",
        "para",
        "sang",
        "si",
        "sebuah",
        "suatu",
        "seorang",
        "beberapa",
        "semua",
        "setiap",
        "tiap",
        "ada",
        "bisa",
        "dapat",
        "harus",
        "mau",
        "ingin",
        "perlu",
        "masih",
        "lagi",
        "baru",
        "lebih",
        "paling",
        "sangat",
        "terlalu",
        "cukup",
        "kurang",
        "sama",
        "seperti",
        "bagai",
        "antara",
        "tanpa",
        "hingga",
        "sampai",
        "sejak",
        "selama",
        "tentang",
        "mengenai",
        "terhadap",
        "atas",
        "bawah",
        "depan",
        "belakang",
        "sini",
        "situ",
        "sana",
        "mereka",
        "kami",
        "kita",
        "saya",
        "aku",
        "kamu",
        "anda",
        "dia",
        "ia",
        "nya",
        # English common stopwords
        "the",
        "a",
        "an",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "and",
        "or",
        "but",
        "if",
        "then",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "he",
        "she",
        "they",
        "we",
        "you",
        "i",
        "my",
        "your",
        "his",
        "her",
        "their",
        "our",
        "not",
        "no",
        "so",
        "very",
        "just",
        "about",
        "into",
        "over",
        "after",
        "before",
    }
)


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


def ass_color_to_bgr_tag(ass_color: str) -> str:
    """Convert ``&HAABBGGRR`` (or ``&HBBGGRR``) into inline ASS ``&HBBGGRR&``."""
    raw = str(ass_color).strip().upper()
    if raw.startswith("&H"):
        raw = raw[2:]
    raw = raw.rstrip("&")
    if len(raw) == 8:
        bgr = raw[2:]
    elif len(raw) == 6:
        bgr = raw
    else:
        raise ValueError(f"Format warna ASS tidak valid: {ass_color!r}")
    return f"&H{bgr}&"


def hex_to_ass_bgr(hex_rgb: str) -> str:
    """Convert RGB hex ``#RRGGBB`` directly to inline ASS ``&HBBGGRR&``."""
    return ass_color_to_bgr_tag(hex_to_ass_color(hex_rgb, 0))


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


def _build_dialogue_line(
    start: float,
    end: float,
    text: str,
    layer: int = 0,
) -> str:
    return (
        f"Dialogue: {int(layer)},{format_ass_time(start)},{format_ass_time(end)},"
        f"Default,,0,0,0,,{text}"
    )


def _ensure_qt_font_metrics(
    font_name: str,
    font_size_px: int,
    bold: bool = True,
):
    """Create a DPI-independent QFontMetricsF using setPixelSize (never setPointSize)."""
    global _BUNDLED_FONTS_LOADED, _HEADLESS_QT_APP

    from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF, QGuiApplication

    if QGuiApplication.instance() is None and _HEADLESS_QT_APP is None:
        _HEADLESS_QT_APP = QGuiApplication([])

    if not _BUNDLED_FONTS_LOADED:
        fonts_dir = get_fonts_dir()
        if fonts_dir.is_dir():
            try:
                for entry in sorted(fonts_dir.iterdir(), key=lambda p: p.name.lower()):
                    if entry.is_file() and entry.suffix.lower() in _FONT_EXTENSIONS:
                        QFontDatabase.addApplicationFont(str(entry))
            except OSError:
                pass
        _BUNDLED_FONTS_LOADED = True

    font = QFont(font_name)
    font.setPixelSize(max(12, int(font_size_px)))
    font.setBold(bool(bold))
    return QFontMetricsF(font)


def _bridge_timed_word_gaps(
    words: list[TimedWord],
    max_gap_sec: float = 0.15,
) -> list[TimedWord]:
    """Bridge inter-word gaps < 150 ms and clamp overlaps within a phrase/block."""
    if len(words) < 2:
        return list(words)

    starts = [w.start for w in words]
    ends = [max(w.start + 0.01, w.end) for w in words]

    for idx in range(len(words) - 1):
        gap = starts[idx + 1] - ends[idx]
        if 0.0 < gap < max_gap_sec:
            ends[idx] = starts[idx + 1]
        elif gap < 0.0:
            clamped_end = max(starts[idx] + 0.01, starts[idx + 1])
            ends[idx] = clamped_end
            if starts[idx + 1] < clamped_end:
                starts[idx + 1] = clamped_end
                if ends[idx + 1] < clamped_end + 0.01:
                    ends[idx + 1] = clamped_end + 0.01

    return [
        TimedWord(text=w.text, start=s, end=e)
        for w, s, e in zip(words, starts, ends)
    ]


def _build_rounded_rect_ass_path(
    x: float,
    y: float,
    w: float,
    h: float,
    radius: float,
) -> str:
    """Build an ASS ``\\p1`` cubic Bezier vector drawing path for a rounded rectangle."""
    safe_w = max(2.0, float(w))
    safe_h = max(2.0, float(h))
    r = max(0.0, min(float(radius), safe_w / 2.0, safe_h / 2.0))

    x0 = float(x)
    y0 = float(y)
    x1 = x0 + safe_w
    y1 = y0 + safe_h

    def _i(val: float) -> int:
        return int(round(val))

    if r <= 0.5:
        return (
            f"m {_i(x0)} {_i(y0)} "
            f"l {_i(x1)} {_i(y0)} "
            f"l {_i(x1)} {_i(y1)} "
            f"l {_i(x0)} {_i(y1)}"
        )

    c = r * _BEZIER_CIRCLE_K
    return (
        f"m {_i(x0 + r)} {_i(y0)} "
        f"l {_i(x1 - r)} {_i(y0)} "
        f"b {_i(x1 - r + c)} {_i(y0)} {_i(x1)} {_i(y0 + r - c)} {_i(x1)} {_i(y0 + r)} "
        f"l {_i(x1)} {_i(y1 - r)} "
        f"b {_i(x1)} {_i(y1 - r + c)} {_i(x1 - r + c)} {_i(y1)} {_i(x1 - r)} {_i(y1)} "
        f"l {_i(x0 + r)} {_i(y1)} "
        f"b {_i(x0 + r - c)} {_i(y1)} {_i(x0)} {_i(y1 - r + c)} {_i(x0)} {_i(y1 - r)} "
        f"l {_i(x0)} {_i(y0 + r)} "
        f"b {_i(x0)} {_i(y0 + r - c)} {_i(x0 + r - c)} {_i(y0)} {_i(x0 + r)} {_i(y0)}"
    )


def _group_words_into_pill_blocks(
    words: list[TimedWord],
    metrics,
    max_line_width: float,
) -> list[list[list[TimedWord]]]:
    """Group consecutive words into blocks of at most 2 lines within max_line_width."""
    if not words:
        return []

    blocks: list[list[list[TimedWord]]] = []
    current_lines: list[list[TimedWord]] = [[]]

    for word in words:
        active_line = current_lines[-1]
        if not active_line:
            active_line.append(word)
            continue

        candidate_text = " ".join(w.text for w in (*active_line, word))
        if metrics.horizontalAdvance(candidate_text) <= max_line_width:
            active_line.append(word)
        elif len(current_lines) < 2:
            current_lines.append([word])
        else:
            blocks.append(current_lines)
            current_lines = [[word]]

    if current_lines and current_lines[0]:
        blocks.append(current_lines)

    # Gently balance 2-line blocks when line 2 is a 1-word orphan and moving one word fits.
    balanced_blocks: list[list[list[TimedWord]]] = []
    for block in blocks:
        if len(block) == 2 and len(block[1]) == 1 and len(block[0]) >= 3:
            new_l1 = block[0][:-1]
            new_l2 = [block[0][-1], *block[1]]
            w_old_1 = metrics.horizontalAdvance(" ".join(w.text for w in block[0]))
            w_old_2 = metrics.horizontalAdvance(" ".join(w.text for w in block[1]))
            w_new_1 = metrics.horizontalAdvance(" ".join(w.text for w in new_l1))
            w_new_2 = metrics.horizontalAdvance(" ".join(w.text for w in new_l2))
            if w_new_2 <= max_line_width and abs(w_new_1 - w_new_2) < abs(w_old_1 - w_old_2):
                block = [new_l1, new_l2]
        balanced_blocks.append(block)

    return balanced_blocks


def _render_capcut_pill_events(
    timed_words: list[TimedWord],
    metrics,
    res_x: int,
    res_y: int,
    font_size: int,
    margin_v: int,
    base_text_ass: str,
    highlight_ass: str,
) -> list[str]:
    """Generate dual-layer ASS events: Layer 0 rounded pill vectors + Layer 1 static block text."""
    if not timed_words:
        return []

    max_line_width = max(64.0, float(res_x) * 0.80)
    blocks = _group_words_into_pill_blocks(timed_words, metrics, max_line_width)

    base_scale = min(float(res_x), float(res_y)) / 1080.0
    pad_x = 10.0 * base_scale
    pad_y = 6.0 * base_scale
    corner_radius = 10.0 * base_scale

    ref_rect = metrics.tightBoundingRect("Hg")
    min_visual_h = max(float(font_size) * 0.65, float(metrics.xHeight()) * 1.35)
    glyph_h = max(float(ref_rect.height()), min_visual_h)

    # Shift from \an5 font-box center to the visual midpoint of the glyphs.
    # For \an5, baseline sits at text_center_y + (ascent - descent) / 2.
    visual_y_offset = (
        (float(metrics.ascent()) - float(metrics.descent())) / 2.0
    ) + float(ref_rect.center().y())

    pill_h = glyph_h + (2.0 * pad_y)
    pill_half_h = pill_h / 2.0
    line_step = max(pill_h + (8.0 * base_scale), float(metrics.height()) * 1.05)
    cx = float(res_x) / 2.0

    # Scale UI vertical margin proportionally to video height (1080p reference).
    scaled_margin_v = max(0.0, float(margin_v)) * (float(res_y) / 1080.0)

    min_line_cy = pill_half_h - visual_y_offset
    max_line_cy = max(min_line_cy, float(res_y) - pill_half_h - visual_y_offset)
    bottom_line_cy = max(
        min_line_cy,
        min(max_line_cy, float(res_y) - scaled_margin_v - pill_half_h - visual_y_offset),
    )

    base_text_bgr = ass_color_to_bgr_tag(base_text_ass)
    highlight_bgr = ass_color_to_bgr_tag(highlight_ass)

    events: list[str] = []

    for block_lines in blocks:
        line_lengths = [len(line) for line in block_lines]
        flat_words = [w for line in block_lines for w in line]
        bridged_flat = _bridge_timed_word_gaps(flat_words, max_gap_sec=0.15)

        # Reconstruct 1-or-2 line structure with bridged timestamps
        bridged_lines: list[list[TimedWord]] = []
        cursor = 0
        for length in line_lengths:
            bridged_lines.append(bridged_flat[cursor : cursor + length])
            cursor += length

        block_start = bridged_flat[0].start
        block_end = max(block_start + 0.05, bridged_flat[-1].end)
        num_lines = len(bridged_lines)

        # Precompute exact per-word center anchors shared by Layer 0 pills and Layer 1 words
        positioned_words: list[tuple[TimedWord, int, int, float]] = []
        for line_idx, line_words in enumerate(bridged_lines):
            line_cy = max(
                min_line_cy,
                min(max_line_cy, bottom_line_cy - ((num_lines - 1 - line_idx) * line_step)),
            )
            text_center_y = int(round(line_cy))
            full_line_text = " ".join(w.text for w in line_words)
            line_width = float(metrics.horizontalAdvance(full_line_text))
            line_left_x = cx - (line_width / 2.0)

            for word_idx, word in enumerate(line_words):
                if word_idx == 0:
                    prefix_w = 0.0
                else:
                    prefix_text = " ".join(lw.text for lw in line_words[:word_idx]) + " "
                    prefix_w = float(metrics.horizontalAdvance(prefix_text))

                upto_text = " ".join(lw.text for lw in line_words[: word_idx + 1])
                upto_w = float(metrics.horizontalAdvance(upto_text))
                word_w = max(1.0, upto_w - prefix_w)
                word_center_x = int(round(line_left_x + prefix_w + (word_w / 2.0)))
                positioned_words.append((word, word_center_x, text_center_y, word_w))

        # Layer 0: Active-word rounded pill centered on exact word_center_x & visual pill_center_y
        for word, word_center_x, text_center_y, word_w in positioned_words:
            pill_center_y = float(text_center_y) + visual_y_offset
            pill_x = float(word_center_x) - (word_w / 2.0) - pad_x
            pill_y = pill_center_y - pill_half_h
            pill_w = word_w + (2.0 * pad_x)

            vec_path = _build_rounded_rect_ass_path(
                pill_x, pill_y, pill_w, pill_h, corner_radius
            )
            pill_tag = (
                f"{{\\an7\\pos(0,0)\\p1\\1c{highlight_bgr}\\1a&H00&\\bord0\\shad0}}"
                f"{vec_path}{{\\p0}}"
            )
            events.append(
                _build_dialogue_line(word.start, word.end, pill_tag, layer=0)
            )

        # Layer 1: Individual stationary words anchored at exact word_center_x (eliminates Qt/libass drift)
        for word, word_center_x, text_center_y, _word_w in positioned_words:
            escaped_word = escape_ass_text(word.text)
            text_tag = (
                f"{{\\an5\\pos({word_center_x},{text_center_y})\\1c{base_text_bgr}\\bord0\\shad2}}"
                f"{escaped_word}"
            )
            events.append(
                _build_dialogue_line(block_start, block_end, text_tag, layer=1)
            )

    return events


def _format_ass_float(value: float) -> str:
    """Format a non-negative float compactly for ASS override tags (e.g. 3.5 -> '3.5', 2.0 -> '2')."""
    formatted = f"{round(max(0.0, float(value)), 2):.2f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _format_ass_signed_float(value: float) -> str:
    """Format a signed float compactly for ASS override tags (e.g. -1.6 -> '-1.6', 0.0 -> '0')."""
    rounded = round(float(value), 2)
    if abs(rounded) < 1e-6:
        return "0"
    formatted = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return formatted or "0"


@dataclass
class _CutoutWord:
    """Internal word representation for Newspaper Cutout grouping and emphasis."""

    text: str
    start: float
    end: float
    emphasized: bool = False
    manual_emphasized: bool = False


def _resolve_newspaper_serif_font() -> str:
    """Return an installed bold serif font family for emphasized cutout words."""
    global _HEADLESS_QT_APP

    from PySide6.QtGui import QFontDatabase, QGuiApplication

    if QGuiApplication.instance() is None and _HEADLESS_QT_APP is None:
        _HEADLESS_QT_APP = QGuiApplication([])

    installed = {fam.lower(): fam for fam in QFontDatabase.families()}
    for preferred in ("georgia", "times new roman", "cambria", "garamond"):
        if preferred in installed:
            return installed[preferred]
    return "Georgia"


def _build_rotated_rect_ass_path(
    cx: float,
    cy: float,
    w: float,
    h: float,
    angle_deg: float,
) -> str:
    """Build a sharp 90-degree ASS ``\\p1`` rectangle rotated around ``(cx, cy)`` matching ``\\frz``."""
    half_w = max(1.0, float(w) / 2.0)
    half_h = max(1.0, float(h) / 2.0)
    corners = (
        (-half_w, -half_h),
        (half_w, -half_h),
        (half_w, half_h),
        (-half_w, half_h),
    )

    if abs(angle_deg) <= 1e-6:
        pts = [(int(round(cx + dx)), int(round(cy + dy))) for dx, dy in corners]
    else:
        rad = math.radians(float(angle_deg))
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        # ASS \frz rotates counter-clockwise in screen coordinates (+X right, +Y down).
        pts = [
            (
                int(round(cx + (dx * cos_a) + (dy * sin_a))),
                int(round(cy - (dx * sin_a) + (dy * cos_a))),
            )
            for dx, dy in corners
        ]

    return (
        f"m {pts[0][0]} {pts[0][1]} "
        f"l {pts[1][0]} {pts[1][1]} "
        f"l {pts[2][0]} {pts[2][1]} "
        f"l {pts[3][0]} {pts[3][1]}"
    )


def _clean_word_char_len(text: str) -> int:
    core = text.strip(_PUNCT_STRIP)
    return len(core) if core else len(text)


def _prepare_newspaper_cutout_words(
    timed_words: list[TimedWord],
) -> tuple[list[_CutoutWord], bool]:
    """Parse manual ``*asterisk*`` emphasis overrides and apply automatic emphasis rules."""
    parsed: list[_CutoutWord] = []
    in_span = False

    for idx, tw in enumerate(timed_words):
        raw = str(tw.text)
        has_star = "*" in raw
        manual = False

        if in_span:
            manual = True
            if raw.rstrip(_PUNCT_STRIP).endswith("*"):
                in_span = False
            clean = raw.replace("*", "")
        elif has_star:
            stripped_punct = raw.strip(_PUNCT_STRIP)
            if (
                stripped_punct.startswith("*")
                and stripped_punct.endswith("*")
                and len(stripped_punct) >= 2
            ):
                manual = True
                clean = raw.replace("*", "")
            elif stripped_punct.startswith("*"):
                manual = True
                if any("*" in later.text for later in timed_words[idx + 1 :]):
                    in_span = True
                clean = raw.replace("*", "")
            else:
                manual = True
                clean = raw.replace("*", "")
        else:
            clean = raw

        clean = clean.strip()
        if not clean:
            continue

        parsed.append(
            _CutoutWord(
                text=clean,
                start=tw.start,
                end=tw.end,
                emphasized=manual,
                manual_emphasized=manual,
            )
        )

    cue_has_manual = any(w.manual_emphasized for w in parsed)

    for idx, word in enumerate(parsed):
        if word.manual_emphasized:
            word.emphasized = True
            continue

        core = word.text.strip(_PUNCT_STRIP)
        core_lower = core.lower()
        is_number = any(ch.isdigit() for ch in core)
        is_id_date = core_lower in _NEWSPAPER_ID_TIME_WORDS

        prev_ends_sentence = (
            idx == 0
            or parsed[idx - 1].text.rstrip("\"' )]}").endswith((".", "!", "?"))
        )
        is_proper_noun = (
            (not prev_ends_sentence)
            and bool(core)
            and core[0].isupper()
            and (core_lower not in _NEWSPAPER_STOPWORDS)
            and (len(core) >= 2)
        )

        if is_number or is_id_date:
            word.emphasized = True
        elif (not cue_has_manual) and is_proper_noun:
            word.emphasized = True

    return parsed, cue_has_manual


def _group_newspaper_cutout_words(
    words: list[_CutoutWord],
    cue_has_manual: bool,
    sans_metrics,
    serif_metrics,
    pad_x: float,
    box_gap: float,
    max_row_width: float,
) -> list[list[_CutoutWord]]:
    """Group consecutive words into dynamic 1-to-3 word horizontal editorial cutout blocks."""
    if not words:
        return []

    def _estimate_box_width(w: _CutoutWord) -> float:
        m = serif_metrics if w.emphasized else sans_metrics
        return max(1.0, float(m.horizontalAdvance(w.text))) + (2.0 * pad_x)

    def _group_width(group: list[_CutoutWord]) -> float:
        if not group:
            return 0.0
        return sum(_estimate_box_width(w) for w in group) + (
            box_gap * max(0, len(group) - 1)
        )

    groups: list[list[_CutoutWord]] = []
    current: list[_CutoutWord] = []

    for word in words:
        w_len = _clean_word_char_len(word.text)

        # Long words (>= 9 chars) are emitted solo as a 1-word impact block.
        if w_len >= 9:
            if current:
                groups.append(current)
                current = []
            groups.append([word])
            continue

        if not current:
            current = [word]
            continue

        # Break early if speech pause between consecutive words exceeds 220 ms.
        if (word.start - current[-1].end) > _NEWSPAPER_PAUSE_GAP_SEC:
            groups.append(current)
            current = [word]
            continue

        candidate = [*current, word]
        fits_width = _group_width(candidate) <= max_row_width

        if len(current) == 1:
            if fits_width:
                current.append(word)
            else:
                groups.append(current)
                current = [word]
        elif len(current) == 2:
            all_short = all(_clean_word_char_len(w.text) <= 4 for w in candidate)
            total_chars = len(" ".join(w.text for w in candidate))
            if all_short and total_chars <= 16 and fits_width:
                current.append(word)
            else:
                groups.append(current)
                current = [word]
        else:
            groups.append(current)
            current = [word]

    if current:
        groups.append(current)

    # For multi-word phrases without manual * tags or auto emphasis, highlight longest content word.
    if not cue_has_manual:
        for group in groups:
            if len(group) < 2 or any(w.emphasized for w in group):
                continue
            candidates = [
                (idx, _clean_word_char_len(w.text))
                for idx, w in enumerate(group)
                if w.text.strip(_PUNCT_STRIP).lower() not in _NEWSPAPER_STOPWORDS
                and _clean_word_char_len(w.text) >= 3
            ]
            if candidates:
                best_idx, _ = max(candidates, key=lambda item: (item[1], item[0]))
                group[best_idx].emphasized = True

    return groups


def _compute_font_box_metrics(metrics, font_size: int, pad_y: float) -> tuple[float, float]:
    """Return ``(box_height, visual_y_offset)`` for vertically centering glyphs inside a cutout box."""
    ref_rect = metrics.tightBoundingRect("Hg")
    min_visual_h = max(float(font_size) * 0.65, float(metrics.xHeight()) * 1.35)
    glyph_h = max(float(ref_rect.height()), min_visual_h)
    visual_y_offset = (
        (float(metrics.ascent()) - float(metrics.descent())) / 2.0
    ) + float(ref_rect.center().y())
    box_h = glyph_h + (2.0 * pad_y)
    return box_h, visual_y_offset


def _render_newspaper_cutout_events(
    timed_words: list[TimedWord],
    sans_font: str,
    serif_font: str,
    sans_metrics,
    serif_metrics,
    res_x: int,
    res_y: int,
    font_size: int,
    margin_v: int,
    base_text_ass: str,
    highlight_ass: str,
    emph_counter_start: int = 0,
) -> tuple[list[str], int]:
    """Generate dual-layer ASS events for Newspaper Cutout (Editorial) captions."""
    if not timed_words:
        return [], emph_counter_start

    cutout_words, cue_has_manual = _prepare_newspaper_cutout_words(timed_words)
    if not cutout_words:
        return [], emph_counter_start

    base_scale = min(float(res_x), float(res_y)) / 1080.0
    pad_x = 12.0 * base_scale
    pad_y = 6.0 * base_scale
    box_gap = 12.0 * base_scale
    scaled_shad = _format_ass_float(3.0 * base_scale)
    max_row_width = max(64.0, float(res_x) * 0.88)

    groups = _group_newspaper_cutout_words(
        words=cutout_words,
        cue_has_manual=cue_has_manual,
        sans_metrics=sans_metrics,
        serif_metrics=serif_metrics,
        pad_x=pad_x,
        box_gap=box_gap,
        max_row_width=max_row_width,
    )
    if not groups:
        return [], emph_counter_start

    norm_box_h, norm_vis_y_off = _compute_font_box_metrics(sans_metrics, font_size, pad_y)
    emph_box_h, emph_vis_y_off = _compute_font_box_metrics(serif_metrics, font_size, pad_y)
    row_box_h = max(norm_box_h, emph_box_h)
    row_half_h = row_box_h / 2.0

    scaled_margin_v = max(0.0, float(margin_v)) * (float(res_y) / 1080.0)
    safe_pad = 4.0 * base_scale
    min_row_cy = row_half_h + safe_pad
    max_row_cy = max(min_row_cy, float(res_y) - row_half_h - safe_pad)
    row_center_y = max(
        min_row_cy,
        min(max_row_cy, float(res_y) - scaled_margin_v - row_half_h),
    )

    normal_text_bgr = ass_color_to_bgr_tag(base_text_ass)
    highlight_bgr = ass_color_to_bgr_tag(highlight_ass)

    events: list[str] = []
    emph_counter = int(emph_counter_start)

    for g_idx, group in enumerate(groups):
        group_start = group[0].start
        group_end = max(group_start + 0.05, group[-1].end)
        if g_idx + 1 < len(groups):
            next_start = groups[g_idx + 1][0].start
            if next_start > group_start + 0.02 and group_end > next_start:
                group_end = next_start

        measured_items: list[tuple[_CutoutWord, float, float, float]] = []
        for word in group:
            if word.emphasized:
                w_px = max(1.0, float(serif_metrics.horizontalAdvance(word.text)))
                b_h = emph_box_h
                v_off = emph_vis_y_off
            else:
                w_px = max(1.0, float(sans_metrics.horizontalAdvance(word.text)))
                b_h = norm_box_h
                v_off = norm_vis_y_off
            measured_items.append((word, w_px + (2.0 * pad_x), b_h, v_off))

        total_row_w = sum(item[1] for item in measured_items) + (
            box_gap * max(0, len(measured_items) - 1)
        )
        cursor_x = (float(res_x) - total_row_w) / 2.0

        prev_word_start: float | None = None
        for word_idx, (word, box_w, box_h, vis_y_off) in enumerate(measured_items):
            word_cx = cursor_x + (box_w / 2.0)
            cursor_x += box_w + box_gap

            word_start = max(group_start, word.start)
            if (
                word_idx > 0
                and prev_word_start is not None
                and word_start <= prev_word_start + 1e-6
            ):
                word_start = max(
                    group_start + (_NEWSPAPER_STAGGER_FALLBACK_SEC * word_idx),
                    prev_word_start + _NEWSPAPER_STAGGER_FALLBACK_SEC,
                )
            max_allowed_start = max(group_start, group_end - 0.02)
            word_start = min(word_start, max_allowed_start)
            prev_word_start = word_start

            box_cy = row_center_y
            text_cy = box_cy - vis_y_off
            cx_i = int(round(word_cx))
            box_cy_i = int(round(box_cy))
            text_cy_i = int(round(text_cy))
            escaped_word = escape_ass_text(word.text)

            if word.emphasized:
                angle = _NEWSPAPER_TILT_DEG if (emph_counter % 2 == 0) else -_NEWSPAPER_TILT_DEG
                emph_counter += 1
                angle_str = _format_ass_signed_float(angle)

                vec_path = _build_rotated_rect_ass_path(0.0, 0.0, box_w, box_h, angle)
                box_tag = (
                    f"{{\\an7\\pos({cx_i},{box_cy_i})\\p1\\1c{highlight_bgr}\\1a&H00&"
                    f"\\bord0\\shad{scaled_shad}\\4c&H000000&\\4a&H80&"
                    f"{_NEWSPAPER_POPUP_TAGS}}}"
                    f"{vec_path}{{\\p0}}"
                )
                text_tag = (
                    f"{{\\an5\\pos({cx_i},{text_cy_i})\\org({cx_i},{box_cy_i})"
                    f"\\fn{serif_font}\\fs{font_size}\\b1\\frz{angle_str}"
                    f"\\1c{_NEWSPAPER_EMPH_TEXT_BGR}\\bord0\\shad0"
                    f"{_NEWSPAPER_POPUP_TAGS}}}"
                    f"{escaped_word}"
                )
            else:
                vec_path = _build_rotated_rect_ass_path(0.0, 0.0, box_w, box_h, 0.0)
                box_tag = (
                    f"{{\\an7\\pos({cx_i},{box_cy_i})\\p1\\1c{_NEWSPAPER_PAPER_BGR}\\1a&H00&"
                    f"\\bord0\\shad{scaled_shad}\\4c&H000000&\\4a&H80&"
                    f"{_NEWSPAPER_POPUP_TAGS}}}"
                    f"{vec_path}{{\\p0}}"
                )
                text_tag = (
                    f"{{\\an5\\pos({cx_i},{text_cy_i})"
                    f"\\fn{sans_font}\\fs{font_size}\\b1\\frz0"
                    f"\\1c{normal_text_bgr}\\bord0\\shad0"
                    f"{_NEWSPAPER_POPUP_TAGS}}}"
                    f"{escaped_word}"
                )

            events.append(_build_dialogue_line(word_start, group_end, box_tag, layer=0))
            events.append(_build_dialogue_line(word_start, group_end, text_tag, layer=1))

    return events, emph_counter


def _render_active_word_color_events(
    timed_words: list[TimedWord],
    cue_start: float,
    cue_end: float,
    metrics,
    res_x: int,
    res_y: int,
    font_size: int,
    margin_v: int,
    outline_width: float,
    shadow: float,
    border_style: int,
    base_text_ass: str,
    highlight_ass: str,
    outline_ass: str,
) -> list[str]:
    """Generate stationary 1-to-2 line ASS events with inline \\1c active-word color highlighting."""
    if not timed_words:
        return []

    max_line_width = max(64.0, float(res_x) * 0.80)
    blocks = _group_words_into_pill_blocks(timed_words, metrics, max_line_width)
    if not blocks:
        return []

    base_scale = min(float(res_x), float(res_y)) / 1080.0
    scaled_bord = _format_ass_float(max(0.0, float(outline_width)) * base_scale)
    scaled_shad = _format_ass_float(max(0.0, float(shadow)) * base_scale)
    cx = int(round(float(res_x) / 2.0))
    scaled_margin_v = max(0.0, float(margin_v)) * (float(res_y) / 1080.0)

    base_text_bgr = ass_color_to_bgr_tag(base_text_ass)
    highlight_bgr = ass_color_to_bgr_tag(highlight_ass)
    outline_bgr = ass_color_to_bgr_tag(outline_ass)

    events: list[str] = []

    def _emit_if_nonempty(t_start: float, t_end: float, line_text: str) -> None:
        if int(round(float(t_end) * 100)) > int(round(float(t_start) * 100)):
            events.append(_build_dialogue_line(t_start, t_end, line_text, layer=0))

    for block_idx, block_lines in enumerate(blocks):
        line_lengths = [len(line) for line in block_lines]
        flat_words = [w for line in block_lines for w in line]
        bridged_flat = _bridge_timed_word_gaps(flat_words, max_gap_sec=0.15)

        bridged_lines: list[list[TimedWord]] = []
        cursor = 0
        for length in line_lengths:
            bridged_lines.append(bridged_flat[cursor : cursor + length])
            cursor += length

        min_y = min(float(res_y), float(font_size) * len(bridged_lines))
        pos_y = int(round(max(min_y, min(float(res_y), float(res_y) - scaled_margin_v))))

        if int(border_style) == 1:
            block_prefix = (
                f"{{\\an2\\pos({cx},{pos_y})\\1c{base_text_bgr}"
                f"\\3c{outline_bgr}\\bord{scaled_bord}\\shad{scaled_shad}}}"
            )
        else:
            block_prefix = f"{{\\an2\\pos({cx},{pos_y})\\1c{base_text_bgr}}}"

        def _format_block_text(active_flat_idx: int | None) -> str:
            rendered_lines: list[str] = []
            flat_cursor = 0
            for line_words in bridged_lines:
                tokens: list[str] = []
                for word in line_words:
                    escaped = escape_ass_text(word.text)
                    if active_flat_idx is not None and flat_cursor == active_flat_idx:
                        tokens.append(
                            f"{{\\1c{highlight_bgr}}}{escaped}{{\\1c{base_text_bgr}}}"
                        )
                    else:
                        tokens.append(escaped)
                    flat_cursor += 1
                rendered_lines.append(" ".join(tokens))
            return "\\N".join(rendered_lines)

        plain_block = block_prefix + _format_block_text(None)

        # Keep full block visible in base font color during any gap before the first word
        if block_idx == 0 and bridged_flat[0].start > cue_start:
            _emit_if_nonempty(cue_start, bridged_flat[0].start, plain_block)

        for word_idx, word in enumerate(bridged_flat):
            if word_idx > 0:
                prev_end = bridged_flat[word_idx - 1].end
                if word.start > prev_end:
                    _emit_if_nonempty(prev_end, word.start, plain_block)

            w_start = word.start
            w_end = max(w_start + 0.01, word.end)
            _emit_if_nonempty(
                w_start, w_end, block_prefix + _format_block_text(word_idx)
            )

        # Keep full block visible in base font color during any gap after the last word
        if block_idx == len(blocks) - 1 and cue_end > bridged_flat[-1].end:
            _emit_if_nonempty(bridged_flat[-1].end, cue_end, plain_block)

    return events


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

    if preset.animation_mode in ("capcut_pill", "newspaper_cutout"):
        border_style = 1
        chosen_outline = 0.0
        style_outline_colour = "&H00000000"
        style_back_colour = "&H80000000"
        style_shadow = 3.0 if preset.animation_mode == "newspaper_cutout" else 2.0
    elif bg_box_enabled:
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

    base_scale = min(float(res_x), float(res_y)) / 1080.0
    effective_font_size = max(12, int(round(float(style["font_size"]) * base_scale)))
    effective_margin_v = int(round(max(0.0, float(style["margin_v"])) * (float(res_y) / 1080.0)))
    effective_outline = _format_ass_float(max(0.0, float(style["outline"])) * base_scale)
    effective_shadow = _format_ass_float(max(0.0, float(style["shadow"])) * base_scale)

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
            f"Style: Default,{style['font_name']},{effective_font_size},"
            f"{style['primary_colour']},{style['secondary_colour']},"
            f"{style['outline_colour']},{style['back_colour']},"
            f"{preset.bold},0,0,0,100,100,0,0,"
            f"{style['border_style']},{effective_outline},{effective_shadow},"
            f"{preset.alignment},{preset.margin_l},{preset.margin_r},{effective_margin_v},1"
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

    if preset.animation_mode == "capcut_pill":
        pill_metrics = _ensure_qt_font_metrics(
            font_name=str(style["font_name"]),
            font_size_px=effective_font_size,
            bold=(preset.bold != 0),
        )
        for start, end, text, words_meta in valid_cues:
            timed_words = resolve_cue_word_timings(start, end, text, words_meta)
            event_lines.extend(
                _render_capcut_pill_events(
                    timed_words=timed_words,
                    metrics=pill_metrics,
                    res_x=res_x,
                    res_y=res_y,
                    font_size=effective_font_size,
                    margin_v=int(style["margin_v"]),
                    base_text_ass=base_text_ass,
                    highlight_ass=highlight_ass,
                )
            )
    elif preset.animation_mode == "active_word_color":
        block_metrics = _ensure_qt_font_metrics(
            font_name=str(style["font_name"]),
            font_size_px=effective_font_size,
            bold=(preset.bold != 0),
        )
        outline_ass = str(style["outline_colour"])
        for start, end, text, words_meta in valid_cues:
            timed_words = resolve_cue_word_timings(start, end, text, words_meta)
            event_lines.extend(
                _render_active_word_color_events(
                    timed_words=timed_words,
                    cue_start=start,
                    cue_end=end,
                    metrics=block_metrics,
                    res_x=res_x,
                    res_y=res_y,
                    font_size=effective_font_size,
                    margin_v=int(style["margin_v"]),
                    outline_width=float(style["outline"]),
                    shadow=float(style["shadow"]),
                    border_style=int(style["border_style"]),
                    base_text_ass=base_text_ass,
                    highlight_ass=highlight_ass,
                    outline_ass=outline_ass,
                )
            )
    elif preset.animation_mode == "newspaper_cutout":
        sans_font = str(style["font_name"])
        serif_font = _resolve_newspaper_serif_font()
        chosen_size = effective_font_size
        sans_metrics = _ensure_qt_font_metrics(
            font_name=sans_font,
            font_size_px=chosen_size,
            bold=True,
        )
        serif_metrics = _ensure_qt_font_metrics(
            font_name=serif_font,
            font_size_px=chosen_size,
            bold=True,
        )
        emph_counter = 0
        for start, end, text, words_meta in valid_cues:
            timed_words = resolve_cue_word_timings(start, end, text, words_meta)
            cue_events, emph_counter = _render_newspaper_cutout_events(
                timed_words=timed_words,
                sans_font=sans_font,
                serif_font=serif_font,
                sans_metrics=sans_metrics,
                serif_metrics=serif_metrics,
                res_x=res_x,
                res_y=res_y,
                font_size=chosen_size,
                margin_v=int(style["margin_v"]),
                base_text_ass=base_text_ass,
                highlight_ass=highlight_ass,
                emph_counter_start=emph_counter,
            )
            event_lines.extend(cue_events)
    else:
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
