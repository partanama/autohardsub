"""Automatic *keyword* tagger for Newspaper Cutout (Editorial) subtitles."""

from __future__ import annotations

import re

from core.ass_engine import _NEWSPAPER_ID_TIME_WORDS, _NEWSPAPER_STOPWORDS

_LEADING_PUNCT_RE = re.compile(r'^([.,!?;:"\'()\[\]{}\-—–«»“”‘’]*)')
_TRAILING_PUNCT_RE = re.compile(r'([.,!?;:"\'()\[\]{}\-—–«»“”‘’]*)$')

_EN_TIME_WORDS = frozenset(
    {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }
)

_ALL_TIME_WORDS = _NEWSPAPER_ID_TIME_WORDS | _EN_TIME_WORDS

_HIGH_IMPACT_WORDS = frozenset(
    {
        # Indonesian dramatic / news verbs & nouns
        "dilahap",
        "api",
        "tewas",
        "hilang",
        "misteri",
        "rahasia",
        "terungkap",
        "ledakan",
        "meledak",
        "kebakaran",
        "terbakar",
        "korban",
        "tragedi",
        "viral",
        "darurat",
        "bahaya",
        "bencana",
        "gempa",
        "banjir",
        "tsunami",
        "longsor",
        "krisis",
        "skandal",
        "korupsi",
        "teror",
        "serangan",
        "kecelakaan",
        "maut",
        "kematian",
        "pembunuhan",
        "kejahatan",
        "penjara",
        "vonis",
        "heboh",
        "gempar",
        "panik",
        "runtuh",
        "hancur",
        "musnah",
        "tenggelam",
        "ancaman",
        "peringatan",
        "waspada",
        "kritis",
        "fatal",
        "ekstrem",
        "dramatis",
        "mengejutkan",
        "fakta",
        "bukti",
        "saksi",
        "pelaku",
        "tersangka",
        "investigasi",
        "dugaan",
        "kerugian",
        "miliaran",
        "triliunan",
        "jutaan",
        # English dramatic / news verbs & nouns
        "breaking",
        "urgent",
        "danger",
        "warning",
        "secret",
        "mystery",
        "tragedy",
        "disaster",
        "explosion",
        "fire",
        "dead",
        "killed",
        "missing",
        "crash",
        "crisis",
        "scandal",
        "exposed",
        "shocking",
        "emergency",
        "victim",
        "victims",
        "viral",
        "collapse",
        "destroyed",
        "attack",
        "murder",
        "crime",
        "arrested",
        "guilty",
        "verdict",
        "evidence",
        "investigation",
        "million",
        "billion",
    }
)

_CURRENCY_PREFIXES = ("rp", "idr", "usd", "eur", "$", "€", "£", "¥")


def _split_token_punctuation(token: str) -> tuple[str, str, str]:
    """Split a word token into (leading_punct, core_word, trailing_punct)."""
    lead_match = _LEADING_PUNCT_RE.match(token)
    lead = lead_match.group(1) if lead_match else ""
    rest = token[len(lead) :]
    if not rest:
        return lead, "", ""

    trail_match = _TRAILING_PUNCT_RE.search(rest)
    trail = trail_match.group(1) if trail_match else ""
    core = rest[: len(rest) - len(trail)] if trail else rest
    return lead, core, trail


def _is_numeric_or_currency(core: str) -> bool:
    """Return True if core contains digits (numbers, years, %, Rp500.000, $100)."""
    if not core:
        return False
    if any(ch.isdigit() for ch in core):
        return True
    lower = core.lower()
    if lower in ("rp", "idr", "usd"):
        return False
    for prefix in _CURRENCY_PREFIXES:
        if lower.startswith(prefix) and len(lower) > len(prefix) and any(
            ch.isdigit() for ch in lower[len(prefix) :]
        ):
            return True
    return False


def auto_tag_line(text: str) -> tuple[str, int]:
    """Wrap high-impact keywords in a subtitle line with ``*asterisks*``.

    Lines that already contain ``*`` are returned unchanged so manual emphasis
    tags are never overwritten or double-wrapped.
    """
    raw = str(text)
    if not raw.strip() or "*" in raw:
        return raw, 0

    tokens = raw.split()
    tagged_tokens: list[str] = []
    tagged_count = 0

    for idx, token in enumerate(tokens):
        lead, core, trail = _split_token_punctuation(token)
        if not core:
            tagged_tokens.append(token)
            continue

        core_lower = core.lower()
        prev_ends_sentence = (
            idx == 0
            or tokens[idx - 1].rstrip("\"' )]}”’").endswith((".", "!", "?"))
        )

        is_number = _is_numeric_or_currency(core)
        is_date_word = core_lower in _ALL_TIME_WORDS
        is_impact_word = core_lower in _HIGH_IMPACT_WORDS
        is_mid_sentence_proper_noun = (
            (not prev_ends_sentence)
            and core[0].isupper()
            and len(core) >= 2
            and core_lower not in _NEWSPAPER_STOPWORDS
        )

        if is_number or is_date_word or is_impact_word or is_mid_sentence_proper_noun:
            tagged_tokens.append(f"{lead}*{core}*{trail}")
            tagged_count += 1
        else:
            tagged_tokens.append(token)

    return " ".join(tagged_tokens), tagged_count
