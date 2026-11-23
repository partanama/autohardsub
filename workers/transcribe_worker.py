"""Non-blocking QThread worker for word-level Whisper transcription and OpenCaption fallback."""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

from core.i18n import tr
from core.paths import (
    SUBPROCESS_NO_WINDOW,
    get_ffmpeg_path,
    get_models_dir,
    get_opencaption_path,
    get_whisper_cli_path,
)
from workers import iter_subprocess_lines

_SPECIAL_TOKEN_RE = re.compile(r"^(\[_.*\]|<\|.*\|>)$")
_FFMPEG_TIME_RE = re.compile(r"time=(\d{2,}):(\d{2}):(\d{2}(?:\.\d+)?)")
_WHISPER_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d{1,3})\s*%", re.IGNORECASE)
_PERCENT_FALLBACK_RE = re.compile(r"(\d{1,3})\s*%")
_WHISPER_TS_RE = re.compile(
    r"\[\d{2}:\d{2}:\d{2}\.\d+\s*-->\s*(\d{2}):(\d{2}):(\d{2}\.\d+)\]"
)

_MODEL_URLS: dict[str, str] = {
    "tiny": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
    "tiny.en": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin",
    "base": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
    "base.en": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin",
    "small": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
    "small.en": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin",
    "medium": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.bin",
    "medium.en": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.en.bin",
    "large-v1": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v1.bin",
    "large-v2": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v2.bin",
    "large-v3": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin",
    "large": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin",
    "large-v3-turbo": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin",
}


def _clamp_prob(value: object, default: float = 1.0) -> float:
    try:
        prob = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, prob))


def _read_offsets_seconds(item: dict) -> tuple[float, float] | None:
    offsets = item.get("offsets")
    if not isinstance(offsets, dict):
        return None
    if "from" not in offsets or "to" not in offsets:
        return None
    try:
        start = max(0.0, float(offsets["from"]) / 1000.0)
        end = max(start, float(offsets["to"]) / 1000.0)
    except (TypeError, ValueError):
        return None
    return start, end


def _flush_bpe_word(
    tokens: list[dict],
    fallback_start: float,
) -> dict | None:
    if not tokens:
        return None

    word_text = "".join(str(tok.get("text", "")) for tok in tokens).strip()
    if not word_text:
        return None

    first_span = next(
        (span for tok in tokens if (span := _read_offsets_seconds(tok)) is not None),
        None,
    )
    last_span = next(
        (
            span
            for tok in reversed(tokens)
            if (span := _read_offsets_seconds(tok)) is not None
        ),
        None,
    )

    word_start = first_span[0] if first_span is not None else fallback_start
    word_end = last_span[1] if last_span is not None else word_start
    if word_end < word_start:
        word_end = word_start

    confidence = min(_clamp_prob(tok.get("p"), 1.0) for tok in tokens)
    return {
        "word": word_text,
        "start": word_start,
        "end": word_end,
        "confidence": confidence,
    }


def bridge_word_gaps(words: list[dict], max_gap_sec: float = 0.15) -> list[dict]:
    """Bridge short inter-word gaps (< 150 ms) so active-word pills transition without flicker."""
    if len(words) < 2:
        return words
    for idx in range(len(words) - 1):
        curr = words[idx]
        nxt = words[idx + 1]
        curr_start = float(curr["start"])
        curr_end = float(curr["end"])
        next_start = float(nxt["start"])
        gap = next_start - curr_end
        if 0.0 < gap < max_gap_sec:
            curr["end"] = next_start
        elif gap < 0.0:
            clamped_end = max(curr_start + 0.01, next_start)
            curr["end"] = clamped_end
            if float(nxt["start"]) < clamped_end:
                nxt["start"] = clamped_end
                if float(nxt["end"]) < clamped_end:
                    nxt["end"] = clamped_end
    return words


def parse_whisper_ojf_json(payload: dict) -> list[dict]:
    """Parse whisper-cli ``-ojf`` JSON output into cues with merged whole-word timings."""
    raw_segments = payload.get("transcription")
    if not isinstance(raw_segments, list):
        raise ValueError("Format JSON whisper-cli tidak memiliki daftar 'transcription'.")

    cues: list[dict] = []
    for seg in raw_segments:
        if not isinstance(seg, dict):
            continue

        seg_span = _read_offsets_seconds(seg)
        seg_start = seg_span[0] if seg_span is not None else 0.0
        seg_end = seg_span[1] if seg_span is not None else seg_start

        tokens = seg.get("tokens")
        words: list[dict] = []
        if isinstance(tokens, list) and tokens:
            current_tokens: list[dict] = []
            force_new_word = False
            cursor = seg_start

            for tok in tokens:
                if not isinstance(tok, dict):
                    continue
                raw_text = str(tok.get("text", ""))
                stripped = raw_text.strip()

                if not stripped:
                    if raw_text:
                        force_new_word = True
                    continue

                if _SPECIAL_TOKEN_RE.match(stripped):
                    force_new_word = True
                    continue

                starts_new_word = (
                    force_new_word
                    or not current_tokens
                    or raw_text[0].isspace()
                )
                if starts_new_word and current_tokens:
                    flushed = _flush_bpe_word(current_tokens, cursor)
                    if flushed is not None:
                        words.append(flushed)
                        cursor = flushed["end"]
                    current_tokens = []

                force_new_word = False
                current_tokens.append(tok)

            if current_tokens:
                flushed = _flush_bpe_word(current_tokens, cursor)
                if flushed is not None:
                    words.append(flushed)

            bridge_word_gaps(words, max_gap_sec=0.15)

        if words:
            cue_text = " ".join(w["word"] for w in words)
            cue_start = seg_start if seg_span is not None else words[0]["start"]
            cue_end = (
                seg_end
                if seg_span is not None and seg_end > cue_start
                else max(cue_start + 0.5, words[-1]["end"])
            )
            min_confidence = min(w["confidence"] for w in words)
        else:
            cue_text = " ".join(str(seg.get("text", "")).split())
            if not cue_text or _SPECIAL_TOKEN_RE.match(cue_text):
                continue
            cue_start = seg_start
            cue_end = seg_end if seg_end > cue_start else cue_start + 0.5
            min_confidence = 1.0

        cues.append(
            {
                "start": cue_start,
                "end": cue_end,
                "text": cue_text,
                "min_confidence": min_confidence,
                "words": words,
            }
        )

    return cues


class TranscribeWorker(QThread):
    """Run whisper-cli -ojf (with opencaption fallback) in a background thread."""

    progress_changed = Signal(int, str)
    status_changed = Signal(str)
    finished_success = Signal(list)
    error_occurred = Signal(str)

    def __init__(
        self,
        video_path: str,
        language: str = "auto",
        model_name: str = "base",
        device: str = "auto",
        opencaption_path: str | None = None,
        models_dir: Path | str | None = None,
        whisper_cli_path: str | None = None,
        ffmpeg_path: str | None = None,
        lang: str = "en",
        duration_seconds: float = 0.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._video_path = video_path
        self._language = language
        self._model_name = model_name
        self._device = device
        self._opencaption_path = opencaption_path
        self._models_dir = Path(models_dir) if models_dir else None
        self._whisper_cli_path = whisper_cli_path
        self._ffmpeg_path = ffmpeg_path
        self._lang = lang
        self._duration_seconds = max(0.0, float(duration_seconds or 0.0))
        self._process: subprocess.Popen[bytes] | None = None
        self._cancelled = False

    @property
    def was_cancelled(self) -> bool:
        return self._cancelled

    def _emit_progress(self, percent: int, text: str) -> None:
        clamped = max(0, min(100, int(percent)))
        self.progress_changed.emit(clamped, text)
        self.status_changed.emit(text)

    def cancel(self) -> None:
        """Request cancellation and terminate any active transcription subprocess."""
        self._cancelled = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _run_cli_process(
        self,
        cmd: list[str],
        on_line: Callable[[str], None] | None = None,
    ) -> tuple[int, str]:
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            creationflags=SUBPROCESS_NO_WINDOW,
        )

        tail_logs: deque[str] = deque(maxlen=30)
        for line in iter_subprocess_lines(self._process.stdout):
            tail_logs.append(line)
            if self._cancelled:
                break
            if on_line is not None:
                on_line(line)

        if self._cancelled and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.5)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    self._process.kill()
                except OSError:
                    pass

        try:
            return_code = self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
            except OSError:
                pass
            return_code = self._process.wait()
        finally:
            if self._process.stdout is not None:
                try:
                    self._process.stdout.close()
                except OSError:
                    pass
            self._process = None

        return return_code, "\n".join(tail_logs)

    def _ensure_model_file(self, models_dir: Path) -> Path:
        raw_path = Path(self._model_name)
        if raw_path.is_file() and raw_path.stat().st_size > 0:
            return raw_path

        filename = raw_path.name
        if filename.endswith(".bin"):
            direct = models_dir / filename
            if direct.is_file() and direct.stat().st_size > 0:
                return direct
            base_name = filename[:-4].removeprefix("ggml-")
        else:
            base_name = filename.removeprefix("ggml-")

        target_path = models_dir / f"ggml-{base_name}.bin"
        if target_path.is_file() and target_path.stat().st_size > 0:
            return target_path

        url = _MODEL_URLS.get(
            base_name,
            f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{base_name}.bin",
        )
        part_path = target_path.with_suffix(".bin.part")
        self._emit_progress(
            0,
            tr(self._lang, "transcribe_stage_download", model=base_name),
        )

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AutoHardsub/1.0"},
        )
        downloaded = 0
        last_reported = 0

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                total_header = resp.headers.get("Content-Length")
                total_bytes = int(total_header) if total_header and total_header.isdigit() else 0

                with part_path.open("wb") as fh:
                    while True:
                        if self._cancelled:
                            raise InterruptedError("Unduhan model dibatalkan.")
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)

                        if downloaded - last_reported >= 2 * 1024 * 1024:
                            last_reported = downloaded
                            dl_mb = downloaded / (1024 * 1024)
                            if total_bytes > 0:
                                total_mb = total_bytes / (1024 * 1024)
                                pct = int(min(100, (downloaded / total_bytes) * 100))
                                self._emit_progress(
                                    0,
                                    tr(
                                        self._lang,
                                        "transcribe_stage_download_pct",
                                        model=base_name,
                                        dl_mb=dl_mb,
                                        total_mb=total_mb,
                                        pct=pct,
                                    ),
                                )
                            else:
                                self._emit_progress(
                                    0,
                                    tr(
                                        self._lang,
                                        "transcribe_stage_download_mb",
                                        model=base_name,
                                        dl_mb=dl_mb,
                                    ),
                                )

            part_path.replace(target_path)
            return target_path
        except Exception:
            part_path.unlink(missing_ok=True)
            raise

    def _run_whisper_cli_pipeline(
        self,
        whisper_cli_bin: str,
        ffmpeg_bin: str,
        models_dir: Path,
    ) -> list[dict] | None:
        model_bin_path = self._ensure_model_file(models_dir)
        if self._cancelled:
            return None

        with tempfile.TemporaryDirectory(
            prefix="autohardsub_tr_", ignore_cleanup_errors=True
        ) as tmpdir:
            tmp_root = Path(tmpdir)
            temp_wav = tmp_root / "audio_16k.wav"
            temp_json_prefix = tmp_root / "transcript"
            temp_json = tmp_root / "transcript.json"

            # Stage 1: Extracting audio track via FFmpeg (0% -> 15%)
            extract_text = tr(self._lang, "transcribe_stage_extract_audio")
            self._emit_progress(2, extract_text)

            ffmpeg_cmd = [
                ffmpeg_bin,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-stats",
                "-i",
                str(self._video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(temp_wav),
            ]

            last_ff_pct = 2

            def _on_ffmpeg_line(line: str) -> None:
                nonlocal last_ff_pct
                if self._duration_seconds <= 0.0:
                    return
                m = _FFMPEG_TIME_RE.search(line)
                if not m:
                    return
                secs = (
                    int(m.group(1)) * 3600.0
                    + int(m.group(2)) * 60.0
                    + float(m.group(3))
                )
                ratio = max(0.0, min(1.0, secs / self._duration_seconds))
                pct = 2 + int(round(ratio * 12))  # 2% -> 14%
                if pct > last_ff_pct:
                    last_ff_pct = pct
                    self._emit_progress(pct, extract_text)

            rc, err_detail = self._run_cli_process(ffmpeg_cmd, on_line=_on_ffmpeg_line)
            if self._cancelled:
                return None
            if rc != 0 or not temp_wav.is_file():
                raise RuntimeError(
                    f"FFmpeg gagal mengekstrak audio WAV (kode {rc}):\n{err_detail}"
                )

            # Stage 2: Loading Whisper model & transcribing audio (15% -> 92%)
            loading_text = tr(
                self._lang, "transcribe_stage_loading_model", model=self._model_name
            )
            self._emit_progress(15, loading_text)

            lang_arg = (
                "auto"
                if not self._language or self._language == "auto"
                else self._language
            )
            whisper_cmd = [
                whisper_cli_bin,
                "-m",
                str(model_bin_path),
                "-l",
                lang_arg,
                "-pp",
                "-ojf",
                "-of",
                str(temp_json_prefix),
                str(temp_wav),
            ]

            last_whisper_pct = 15
            last_raw_pct = -1

            def _on_whisper_line(line: str) -> None:
                nonlocal last_whisper_pct, last_raw_pct
                raw_pct: int | None = None

                match = _WHISPER_PROGRESS_RE.search(line)
                if match:
                    raw_pct = max(0, min(100, int(match.group(1))))
                elif "progress" in line.lower() and "%" in line:
                    fallback = _PERCENT_FALLBACK_RE.search(line)
                    if fallback:
                        raw_pct = max(0, min(100, int(fallback.group(1))))
                elif self._duration_seconds > 0.0:
                    ts_match = _WHISPER_TS_RE.search(line)
                    if ts_match:
                        end_sec = (
                            int(ts_match.group(1)) * 3600.0
                            + int(ts_match.group(2)) * 60.0
                            + float(ts_match.group(3))
                        )
                        raw_pct = max(
                            0,
                            min(100, int(round((end_sec / self._duration_seconds) * 100))),
                        )

                if raw_pct is not None:
                    mapped = 18 + int(round(raw_pct * 0.74))  # 18% -> 92%
                    if mapped > last_whisper_pct or raw_pct > last_raw_pct:
                        last_whisper_pct = max(last_whisper_pct, mapped)
                        last_raw_pct = max(last_raw_pct, raw_pct)
                        self._emit_progress(
                            last_whisper_pct,
                            tr(
                                self._lang,
                                "transcribe_stage_transcribing",
                                model=self._model_name,
                                pct=last_raw_pct,
                            ),
                        )
                elif last_whisper_pct < 17 and (
                    "whisper_init_state" in line or "ggml_vulkan" in line.lower()
                ):
                    last_whisper_pct = 17
                    self._emit_progress(17, loading_text)

            rc, err_detail = self._run_cli_process(whisper_cmd, on_line=_on_whisper_line)
            if self._cancelled:
                return None
            if rc != 0:
                raise RuntimeError(
                    f"whisper-cli gagal menjalankan transkripsi (kode {rc}):\n{err_detail}"
                )
            if not temp_json.is_file():
                raise RuntimeError(
                    "whisper-cli selesai tanpa menghasilkan file JSON -ojf."
                )

            # Stage 3: Parsing -ojf word-level JSON timestamps & bridging BPE sub-words (92% -> 100%)
            self._emit_progress(93, tr(self._lang, "transcribe_stage_parsing"))
            with temp_json.open("r", encoding="utf-8-sig") as fh:
                payload = json.load(fh)
            cues = parse_whisper_ojf_json(payload)
            if self._cancelled:
                return None
            self._emit_progress(100, tr(self._lang, "transcribe_dlg_done"))
            return cues

    def _parse_opencaption_json(self, json_path: Path) -> list[dict]:
        with json_path.open("r", encoding="utf-8-sig") as fh:
            payload = json.load(fh)

        raw_cues = payload.get("cues")
        if not isinstance(raw_cues, list):
            raise ValueError("Format JSON OpenCaption tidak memiliki daftar 'cues'.")

        cues: list[dict] = []
        for item in raw_cues:
            if not isinstance(item, dict):
                continue
            text = " ".join(str(item.get("text", "")).split())
            if not text:
                continue
            try:
                start = max(0.0, float(item.get("start", 0.0)))
                end = float(item.get("end", 0.0))
            except (TypeError, ValueError):
                continue
            if end <= start:
                end = start + 0.5
            cues.append(
                {
                    "start": start,
                    "end": end,
                    "text": text,
                    "min_confidence": 1.0,
                    "words": [],
                }
            )
        return cues

    def _run_opencaption_fallback(
        self,
        opencaption_bin: str,
        models_dir: Path,
    ) -> list[dict] | None:
        with tempfile.TemporaryDirectory(
            prefix="autohardsub_tr_", ignore_cleanup_errors=True
        ) as tmpdir:
            temp_json = Path(tmpdir) / "transcript.json"
            cmd = [
                opencaption_bin,
                "-in",
                str(self._video_path),
                "-format",
                "json",
                "-lang",
                self._language,
                "-model",
                self._model_name,
                "-model-dir",
                str(models_dir),
                "-device",
                self._device,
                "-out",
                str(temp_json),
            ]

            self._emit_progress(
                10,
                tr(self._lang, "transcribe_stage_opencaption", model=self._model_name),
            )
            downloading_notified = False
            transcribing_notified = False

            def _on_oc_line(line: str) -> None:
                nonlocal downloading_notified, transcribing_notified
                lower = line.lower()
                if not downloading_notified and any(
                    kw in lower for kw in ("download", "mengunduh", "fetch", "http")
                ):
                    downloading_notified = True
                    self._emit_progress(
                        0,
                        tr(
                            self._lang,
                            "transcribe_stage_download",
                            model=self._model_name,
                        ),
                    )
                elif not transcribing_notified and any(
                    kw in lower for kw in ("transcrib", "whisper", "audio", "process")
                ):
                    transcribing_notified = True
                    self._emit_progress(
                        25,
                        tr(
                            self._lang,
                            "transcribe_stage_loading_model",
                            model=self._model_name,
                        ),
                    )

            rc, err_detail = self._run_cli_process(cmd, on_line=_on_oc_line)
            if self._cancelled:
                return None
            if rc != 0:
                raise RuntimeError(
                    f"OpenCaption gagal menjalankan transkripsi (kode {rc}):\n{err_detail}"
                )
            if not temp_json.is_file():
                raise RuntimeError(
                    "OpenCaption selesai tanpa menghasilkan file JSON transkrip."
                )

            self._emit_progress(93, tr(self._lang, "transcribe_stage_parsing"))
            cues = self._parse_opencaption_json(temp_json)
            if self._cancelled:
                return None
            self._emit_progress(100, tr(self._lang, "transcribe_dlg_done"))
            return cues

    def run(self) -> None:
        if not Path(self._video_path).is_file():
            self.error_occurred.emit(f"File video tidak ditemukan: {self._video_path}")
            return

        models_dir = self._models_dir or get_models_dir()
        try:
            models_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.error_occurred.emit(f"Gagal menyiapkan folder model: {exc}")
            return

        whisper_cli_bin = self._whisper_cli_path or get_whisper_cli_path()
        ffmpeg_bin = self._ffmpeg_path or get_ffmpeg_path()
        opencaption_bin = self._opencaption_path or get_opencaption_path()

        try:
            if whisper_cli_bin and ffmpeg_bin:
                cues = self._run_whisper_cli_pipeline(
                    whisper_cli_bin=whisper_cli_bin,
                    ffmpeg_bin=ffmpeg_bin,
                    models_dir=models_dir,
                )
            elif opencaption_bin:
                cues = self._run_opencaption_fallback(
                    opencaption_bin=opencaption_bin,
                    models_dir=models_dir,
                )
            else:
                missing_hint = (
                    "whisper-cli.exe / ffmpeg.exe"
                    if not ffmpeg_bin
                    else "whisper-cli.exe atau opencaption.exe"
                )
                self.error_occurred.emit(
                    f"{missing_hint} tidak ditemukan. Letakkan di folder assets/bin/ "
                    "atau tambahkan ke PATH sistem."
                )
                return

            if self._cancelled or cues is None:
                self.error_occurred.emit("Proses transkripsi dibatalkan.")
                return

            self.finished_success.emit(cues)

        except InterruptedError:
            self.error_occurred.emit("Proses transkripsi dibatalkan.")
        except urllib.error.URLError as exc:
            self.error_occurred.emit(f"Gagal mengunduh model Whisper: {exc}")
        except json.JSONDecodeError as exc:
            self.error_occurred.emit(f"Gagal membaca JSON hasil transkripsi: {exc}")
        except (OSError, RuntimeError, ValueError) as exc:
            self.error_occurred.emit(str(exc))
        except Exception as exc:
            self.error_occurred.emit(f"Kesalahan saat transkripsi: {exc}")
        finally:
            self._process = None
