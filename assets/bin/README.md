# Bundled External Binaries (`assets/bin/`)

Place the required external Windows executables in this directory before running or packaging with PyInstaller:

- `whisper-cli.exe` — `whisper.cpp` CLI (with Vulkan GPU DLLs) for word-level `-ojf` transcription and confidence scoring
- `opencaption.exe` — OpenCaption CLI fallback for speech transcription and model management
- `ffmpeg.exe` — FFmpeg binary with `libass` (`ass` filter) and H.264 encoder support (`h264_nvenc` / `libx264`)
- `ffprobe.exe` — FFprobe binary for extracting video dimensions and duration

Required runtime DLLs (such as `libwhisper.dll`, `ggml*.dll`, and MSYS2 UCRT64 runtime libraries) must reside alongside `whisper-cli.exe` and `opencaption.exe` in this folder.

## Resolution Order

1. This `assets/bin/` directory (next to the executable or inside PyInstaller `_MEIPASS`).
2. System `PATH` fallback if a binary is not present here.
