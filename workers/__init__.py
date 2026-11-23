"""Background QThread workers for transcription and hardsub rendering."""

from __future__ import annotations

import codecs
from typing import IO, Iterator


def iter_subprocess_lines(stream: IO[bytes] | None) -> Iterator[str]:
    """Yield lines from an unbuffered binary subprocess stream, splitting on CR and LF.

    FFmpeg and CLI progress bars emit carriage-return (``\\r``) updates without
    newlines; reading raw byte chunks avoids Python line-buffering stalls.
    """
    if stream is None:
        return

    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buffer = ""

    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        buffer += decoder.decode(chunk, final=False)
        while True:
            cr_idx = buffer.find("\r")
            lf_idx = buffer.find("\n")
            if cr_idx == -1 and lf_idx == -1:
                break
            if cr_idx != -1 and (lf_idx == -1 or cr_idx < lf_idx):
                split_idx = cr_idx
            else:
                split_idx = lf_idx
            line = buffer[:split_idx].strip()
            buffer = buffer[split_idx + 1 :]
            if line:
                yield line

    buffer += decoder.decode(b"", final=True)
    tail = buffer.strip()
    if tail:
        yield tail


from workers.render_worker import RenderWorker, escape_ffmpeg_filter_path
from workers.transcribe_worker import TranscribeWorker, parse_whisper_ojf_json

__all__ = [
    "RenderWorker",
    "TranscribeWorker",
    "escape_ffmpeg_filter_path",
    "iter_subprocess_lines",
    "parse_whisper_ojf_json",
]
