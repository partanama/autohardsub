"""Bilingual internationalization (Indonesian & English) for AutoHardsub."""

from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "id"
SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("Indonesia (ID)", "id"),
    ("English (EN)", "en"),
)

TRANSLATIONS: dict[str, dict[str, str]] = {
    "id": {
        # Window & Header
        "window_title": "AutoHardsub — Transkrip AI & Burn-In Subtitle Otomatis",
        "app_title": "AutoHardsub",
        "app_subtitle": "Buat subtitle otomatis dengan AI lalu tempel permanen (hardsub) dalam satu aplikasi.",
        "ui_lang_label": "Bahasa UI:",
        "ui_lang_tooltip": "Ganti bahasa antarmuka aplikasi (Indonesia / English)",
        # Hardware badges
        "hw_badge_format": "Mode Performa: {transcribe} (Transkrip) + {render} (Render)",
        "hw_badge_cpu_only": "Mode Performa: CPU Standard",
        "hw_transcribe_vulkan": "GPU Vulkan",
        "hw_transcribe_cpu": "CPU",
        "hw_render_nvenc": "GPU NVIDIA (NVENC)",
        "hw_render_qsv": "GPU Intel (QuickSync)",
        "hw_render_mf": "GPU Windows (MediaFoundation)",
        "hw_render_cpu": "CPU",
        # Warning banner
        "warning_missing_bins": (
            "Perhatian: Program eksternal belum ditemukan ({missing}). "
            "Letakkan file tersebut di folder assets/bin/ atau tambahkan ke PATH sistem."
        ),
        # Step 1
        "step1_title": "Langkah 1 — Pilih Video & Pengaturan Transkrip AI",
        "drop_prompt": "Tarik & lepas file video ke sini, atau klik 'Pilih Video'",
        "drop_hint": "Mendukung MP4, MKV, MOV, AVI, WEBM (otomatis mendeteksi 16:9 & 9:16)",
        "btn_browse_video": "Pilih Video",
        "label_audio_lang": "Bahasa:",
        "lang_auto": "Otomatis",
        "lang_id": "Indonesia",
        "lang_en": "Inggris",
        "label_ai_model": "Model AI:",
        "model_base": "Cepat - Base",
        "model_small": "Akurat - Small",
        "model_large_v3": "Maksimal - Large-v3",
        "tooltip_model": "Model Whisper akan diunduh otomatis ke:\n{models_dir}",
        "btn_transcribe": "1. Buat Transkrip",
        "orientation_vertical": "Vertikal (9:16)",
        "orientation_square": "Persegi (1:1)",
        "orientation_horizontal": "Horizontal (16:9)",
        "video_meta_format": "{width}×{height} • {orientation} • Durasi {duration}",
        # Step 2
        "step2_title": "Langkah 2 — Periksa & Edit Teks Subtitle",
        "cue_count": "{count} baris",
        "btn_add_row": "Tambah Baris",
        "btn_remove_row": "Hapus Baris",
        "confidence_legend": (
            "Baris berwarna kuning/merah menandakan kata dengan tingkat keyakinan AI rendah "
            "— klik sel teks untuk koreksi."
        ),
        "col_start": "Mulai",
        "col_end": "Selesai",
        "col_text": "Teks Subtitle",
        "tooltip_typo_words": "Periksa kemungkinan typo: {words}",
        "tooltip_typo_conf": "Periksa kemungkinan typo (keyakinan AI: {pct}%)",
        # Step 3 — Styling & Export
        "step3_title": "Langkah 3 — Gaya Subtitle & Export Video",
        "label_preset": "Gaya Subtitle:",
        "label_font_family": "Jenis Font:",
        "label_font_size": "Ukuran Font:",
        "label_outline_width": "Tebal Outline:",
        "label_margin_v": "Posisi Vertikal / Y Pos:",
        "label_primary_color": "Warna Font:",
        "label_highlight_color": "Warna Highlight:",
        "label_outline_color": "Warna Outline:",
        "label_bg_box_color": "Warna Background Teks:",
        "chk_enable_bg_box": "Aktifkan Background Box",
        "label_bg_box_opacity": "Transparansi Background:",
        "tooltip_primary_color": "Pilih warna utama teks subtitle",
        "tooltip_highlight_color": "Pilih warna sorotan kata aktif / kotak penekanan (untuk Active Word Color / CapCut Pill / Newspaper Cutout / Pop / Karaoke)",
        "tooltip_outline_color": "Pilih warna garis tepi (outline) huruf",
        "tooltip_bg_box_color": "Pilih warna latar kotak belakang teks",
        "tooltip_bg_box_toggle": "Gunakan kotak latar belakang di belakang teks (ASS BorderStyle=3)",
        "tooltip_bg_box_opacity": "Atur tingkat opasitas kotak latar belakang (0% transparan – 100% solid)",
        "color_dialog_title": "Pilih Warna — {target}",
        "label_output_file": "File Output:",
        "placeholder_output": "Otomatis: <nama_video>_hardsub.mp4",
        "btn_browse_output": "Ubah...",
        "btn_cancel": "Batal",
        "btn_export": "2. Export Video Hardsub",
        # Presets
        "preset_youtube_clean_name": "YouTube Clean",
        "preset_youtube_clean_desc": "Teks putih bersih dengan garis tepi hitam dan bayangan halus.",
        "preset_reels_pop_name": "Reels / Shorts Pop Kuning",
        "preset_reels_pop_desc": "Sorotan kuning per kata dengan efek membal (bounce) untuk video vertikal.",
        "preset_karaoke_wipe_name": "Karaoke Wipe",
        "preset_karaoke_wipe_desc": "Transisi warna halus kiri-ke-kanan dari putih ke kuning per kata.",
        "preset_box_kontras_name": "Box Kontras (TikTok Style)",
        "preset_box_kontras_desc": "Latar kotak hitam semi-transparan dengan teks putih kontras tinggi.",
        "preset_capcut_pill_name": "CapCut Pill (Active Word)",
        "preset_capcut_pill_desc": "Kotak kapsul berwarna mengikuti kata aktif secara halus dengan teks putih tetap diam (gaya CapCut).",
        "preset_active_word_color_name": "Active Word Color (News/Doc)",
        "preset_active_word_color_desc": "Semua kata tetap diam dengan outline hitam tegas, sementara kata yang sedang diucapkan berubah warna highlight (gaya Berita/Dokumenter).",
        "preset_newspaper_cutout_name": "Newspaper Cutout (Editorial)",
        "preset_newspaper_cutout_desc": "Gaya guntingan koran investigatif (1–3 kata): kotak kertas putih lurus dengan teks hitam bold, dan kata penting dalam kotak merah miring ber-font serif putih. Apit kata dengan *bintang* untuk penekanan manual.",
        # Status messages
        "status_ready": "Siap. Pilih video untuk memulai.",
        "status_video_loaded": "Video dimuat. Klik '1. Buat Transkrip' atau tambah subtitle manual.",
        "status_transcribing": "Menjalankan transkripsi AI (model {model})...",
        "status_transcribe_done_flagged": (
            "Transkrip selesai: {count} baris subtitle ({flagged} baris ditandai untuk diperiksa)."
        ),
        "status_transcribe_done": "Transkrip selesai: {count} baris subtitle siap diperiksa.",
        "status_transcribe_empty": "Transkrip selesai, namun tidak ada ucapan terdeteksi di video ini.",
        "status_transcribe_failed": "Transkripsi gagal atau dibatalkan.",
        "status_export_starting": "Memulai proses burn-in subtitle...",
        "status_export_done": "Selesai! Video tersimpan di: {filename}",
        "status_export_failed": "Export video gagal atau dibatalkan.",
        "status_cancel_transcribe": "Membatalkan transkripsi...",
        "status_cancel_render": "Membatalkan proses render...",
        # Dialogs & validation
        "dlg_select_video_title": "Pilih File Video",
        "dlg_video_filter": "File Video (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.flv);;Semua File (*.*)",
        "dlg_save_video_title": "Simpan Video Hardsub",
        "dlg_mp4_filter": "Video MP4 (*.mp4)",
        "dlg_video_error_title": "Gagal Membaca Video",
        "dlg_transcribe_error_title": "Transkripsi Gagal",
        "dlg_check_subtitle_title": "Periksa Subtitle",
        "dlg_invalid_output_title": "Path Output Tidak Valid",
        "dlg_invalid_output_msg": "File output tidak boleh menimpa file video sumber secara langsung.",
        "dlg_export_success_title": "Export Berhasil",
        "dlg_export_success_text": "Video hardsub berhasil dibuat!",
        "dlg_export_success_info": "Lokasi file:\n{path}",
        "btn_open_file": "▶ Buka File",
        "btn_open_folder": "Buka Folder Hasil",
        "btn_open_folder_short": "📂 Buka Folder",
        "btn_close": "Tutup",
        "dlg_export_error_title": "Export Gagal",
        "export_dlg_title": "Export Video Hardsub",
        "export_dlg_heading": "Mengekspor Video Hardsub",
        "export_dlg_done_heading": "Render Selesai!",
        "export_dlg_done": "✓ Render Selesai! Video hardsub siap diputar.",
        "export_dlg_cancelling": "Membatalkan...",
        "dlg_busy_close_title": "Proses Sedang Berjalan",
        "dlg_busy_close_msg": "Ada proses yang masih berjalan. Hentikan proses dan tutup aplikasi?",
        "err_row_prefix": "Baris {row}: {error}",
        "err_row_end_before_start": "Baris {row}: Waktu selesai harus lebih besar dari waktu mulai.",
        "err_empty_cues": "Daftar subtitle masih kosong. Buat transkrip atau tambah baris terlebih dahulu.",
        # Auto-updater
        "btn_check_update": "Cek Update",
        "btn_checking_update": "Mengecek...",
        "tooltip_check_update": "Periksa pembaruan aplikasi dari GitHub",
        "update_dlg_available_title": "Pembaruan Tersedia",
        "update_dlg_available_text": 'Versi baru AutoHardsub tersedia: v{version} ("{codename}")',
        "update_dlg_available_info": (
            "Versi saat ini: v{local_version}\n\n"
            "Catatan Perubahan:\n{changelog}\n\n"
            "Apakah Anda ingin memperbarui sekarang?"
        ),
        "update_no_changelog": "Tidak ada catatan perubahan.",
        "btn_update_now": "Update Sekarang",
        "btn_update_later": "Nanti",
        "update_dlg_uptodate_title": "Aplikasi Sudah Terbaru",
        "update_dlg_uptodate_msg": (
            'Anda sudah menggunakan versi terbaru AutoHardsub (v{version} — "{codename}").'
        ),
        "update_dlg_check_error_title": "Gagal Memeriksa Update",
        "update_dlg_check_error_msg": (
            "Tidak dapat terhubung ke GitHub untuk memeriksa pembaruan.\n\nDetail: {error}"
        ),
        "update_progress_title": "Memperbarui AutoHardsub",
        "update_status_backup": "Membuat cadangan file ke _backup/...",
        "update_status_downloading": "Mengunduh pembaruan dari GitHub...",
        "update_status_extracting": "Mengekstrak dan menerapkan file baru...",
        "update_status_pip": "Memasang dependensi baru (pip)...",
        "update_status_done": "Pembaruan selesai! Memulai ulang aplikasi...",
        "update_dlg_success_title": "Pembaruan Berhasil",
        "update_dlg_success_msg": (
            'AutoHardsub telah diperbarui ke v{version} ("{codename}").\n'
            "Aplikasi akan dimulai ulang sekarang."
        ),
        "update_dlg_failed_title": "Pembaruan Gagal",
        "update_dlg_failed_msg": (
            "Pembaruan gagal dan file sebelumnya telah dipulihkan otomatis dari _backup/.\n\n"
            "Detail: {error}"
        ),
        "update_dlg_busy_msg": (
            "Selesaikan atau batalkan proses transkrip/render yang sedang berjalan sebelum memperbarui."
        ),
        # Live preview
        "preview_title": "Pratinjau Gaya (Live Preview)",
        "tooltip_preview_zoom": "Scroll untuk zoom, seret untuk geser, klik ganda atau klik tombol ini untuk reset ke 100%",
        # Auto-tag keywords
        "btn_auto_tag_keywords": "✨ Auto-Tandai Kata Kunci",
        "tooltip_auto_tag_keywords": (
            "Otomatis mengapit angka, tanggal, nama tempat/tokoh, dan kata dramatis dengan *bintang* "
            "untuk gaya Newspaper Cutout (baris yang sudah memiliki * dilewati)."
        ),
        "status_auto_tag_done": "✨ {words} kata kunci ditandai pada {lines} baris subtitle.",
        "status_auto_tag_none": "Tidak ada kata kunci baru yang ditandai (baris bertanda * dilewati).",
        # Help dialog
        "btn_help": "? Panduan",
        "tooltip_help": "Buka panduan singkat gaya subtitle, font kustom, dan lokasi pengaturan",
        "help_dlg_title": "Panduan AutoHardsub",
        "help_header_title": "Panduan Cepat AutoHardsub",
        "help_header_subtitle": "Tips memilih gaya subtitle, menandai kata kunci editorial, menambah font kustom, dan mengelola pengaturan.",
        "help_sec1_title": "1. Panduan Gaya Subtitle (Presets)",
        "help_sec1_body": (
            "<ul style='margin:0; padding-left:18px;'>"
            "<li><b>CapCut Pill (Active Word):</b> Teks putih tetap diam (1–2 baris) dengan kapsul warna (<i>Highlight Color</i>) yang berpindah mengikuti kata aktif.</li>"
            "<li><b>Active Word Color (News/Doc):</b> Teks tebal dengan outline hitam tegas; hanya kata yang sedang diucapkan yang berubah ke warna <i>Highlight</i>.</li>"
            "<li><b>Newspaper Cutout (Editorial):</b> Blok horizontal 1–3 kata bergaya guntingan koran investigatif — kotak kertas abu-abu terang dengan teks hitam sans-serif, serta kotak merah miring (±1.6°) ber-font serif putih untuk kata penting.</li>"
            "<li><b>Preset Klasik (YouTube Clean, Reels Pop, Karaoke Wipe, Box Kontras):</b> Mendukung kustomisasi penuh warna teks, outline, dan kotak latar semi-transparan.</li>"
            "</ul>"
        ),
        "help_sec2_title": "2. Tips Newspaper Cutout (*Kata Kunci*)",
        "help_sec2_body": (
            "Apit kata apa pun dengan tanda bintang seperti <b>*Baduy*</b> atau <b>*api*</b> di tabel editor untuk "
            "memaksanya tampil dalam kotak merah miring ber-font serif.<br><br>"
            "Gunakan tombol <b>✨ Auto-Tandai Kata Kunci</b> di atas tabel subtitle untuk menandai angka, tanggal/hari, "
            "nama proper di tengah kalimat, dan kata dramatis secara otomatis. Baris yang sudah memiliki tanda <b>*</b> "
            "akan dilewati agar suntingan manual Anda tetap aman."
        ),
        "help_sec3_title": "3. Menambah Font Kustom",
        "help_sec3_body": (
            "Salin file font berformat <b>.ttf</b> atau <b>.otf</b> ke folder berikut lalu mulai ulang AutoHardsub:<br>"
            "<code style='color:#7dd3fc;'>{fonts_dir}</code><br><br>"
            "Font kustom akan otomatis dimuat dan muncul di bagian paling atas daftar <b>Jenis Font</b>."
        ),
        "help_sec4_title": "4. Auto-Update & Lokasi Pengaturan",
        "help_sec4_body": (
            "Semua preferensi terakhir Anda (bahasa UI, preset, font, warna, margin vertikal, dan rasio pratinjau) "
            "disimpan otomatis di luar folder aplikasi agar tidak pernah tertimpa saat pembaruan dari GitHub:<br>"
            "<code style='color:#7dd3fc;'>{settings_dir}\\user_settings.json</code>"
        ),
        "help_btn_open_fonts": "Buka Folder Font (assets/fonts)",
    },
    "en": {
        # Window & Header
        "window_title": "AutoHardsub — AI Transcription & Automatic Subtitle Burn-In",
        "app_title": "AutoHardsub",
        "app_subtitle": "Generate AI subtitles automatically and burn them into your video in one app.",
        "ui_lang_label": "UI Language:",
        "ui_lang_tooltip": "Switch application interface language (Indonesian / English)",
        # Hardware badges
        "hw_badge_format": "Performance Mode: {transcribe} (Transcribe) + {render} (Render)",
        "hw_badge_cpu_only": "Performance Mode: Standard CPU",
        "hw_transcribe_vulkan": "Vulkan GPU",
        "hw_transcribe_cpu": "CPU",
        "hw_render_nvenc": "GPU NVIDIA (NVENC)",
        "hw_render_qsv": "GPU Intel (QuickSync)",
        "hw_render_mf": "GPU Windows (MediaFoundation)",
        "hw_render_cpu": "CPU",
        # Warning banner
        "warning_missing_bins": (
            "Warning: External binaries not found ({missing}). "
            "Place them inside assets/bin/ or add them to your system PATH."
        ),
        # Step 1
        "step1_title": "Step 1 — Select Video & AI Transcription Settings",
        "drop_prompt": "Drag & drop a video file here, or click 'Select Video'",
        "drop_hint": "Supports MP4, MKV, MOV, AVI, WEBM (auto-detects 16:9 & 9:16)",
        "btn_browse_video": "Select Video",
        "label_audio_lang": "Language:",
        "lang_auto": "Auto-Detect",
        "lang_id": "Indonesian",
        "lang_en": "English",
        "label_ai_model": "AI Model:",
        "model_base": "Fast - Base",
        "model_small": "Accurate - Small",
        "model_large_v3": "Best - Large-v3",
        "tooltip_model": "Whisper models will be downloaded automatically to:\n{models_dir}",
        "btn_transcribe": "1. Generate Transcript",
        "orientation_vertical": "Vertical (9:16)",
        "orientation_square": "Square (1:1)",
        "orientation_horizontal": "Horizontal (16:9)",
        "video_meta_format": "{width}×{height} • {orientation} • Duration {duration}",
        # Step 2
        "step2_title": "Step 2 — Review & Edit Subtitle Text",
        "cue_count": "{count} lines",
        "btn_add_row": "Add Row",
        "btn_remove_row": "Delete Row",
        "confidence_legend": (
            "Yellow/red highlighted rows indicate low AI confidence words "
            "— click the text cell to edit."
        ),
        "col_start": "Start",
        "col_end": "End",
        "col_text": "Subtitle Text",
        "tooltip_typo_words": "Check possible typo: {words}",
        "tooltip_typo_conf": "Check possible typo (AI confidence: {pct}%)",
        # Step 3 — Styling & Export
        "step3_title": "Step 3 — Subtitle Styling & Video Export",
        "label_preset": "Subtitle Style:",
        "label_font_family": "Font Family:",
        "label_font_size": "Font Size:",
        "label_outline_width": "Outline Width:",
        "label_margin_v": "Vertical Margin / Y Pos:",
        "label_primary_color": "Font Color:",
        "label_highlight_color": "Highlight Color:",
        "label_outline_color": "Outline Color:",
        "label_bg_box_color": "Text Background Color:",
        "chk_enable_bg_box": "Enable Text Background Box",
        "label_bg_box_opacity": "Box Opacity:",
        "tooltip_primary_color": "Choose the main subtitle text color",
        "tooltip_highlight_color": "Choose the active word / emphasis box highlight color (for Active Word Color / CapCut Pill / Newspaper Cutout / Pop / Karaoke presets)",
        "tooltip_outline_color": "Choose the text outline stroke color",
        "tooltip_bg_box_color": "Choose the text background box color",
        "tooltip_bg_box_toggle": "Draw a background box behind subtitle text (ASS BorderStyle=3)",
        "tooltip_bg_box_opacity": "Adjust background box opacity (0% transparent – 100% solid)",
        "color_dialog_title": "Choose Color — {target}",
        "label_output_file": "Output File:",
        "placeholder_output": "Auto: <video_name>_hardsub.mp4",
        "btn_browse_output": "Browse...",
        "btn_cancel": "Cancel",
        "btn_export": "2. Export Hardsub Video",
        # Presets
        "preset_youtube_clean_name": "YouTube Clean",
        "preset_youtube_clean_desc": "Clean white text with crisp black outline and soft drop shadow.",
        "preset_reels_pop_name": "Reels / Shorts Yellow Pop",
        "preset_reels_pop_desc": "Per-word yellow highlight with bounce effect for vertical videos.",
        "preset_karaoke_wipe_name": "Karaoke Wipe",
        "preset_karaoke_wipe_desc": "Smooth left-to-right color wipe from white to yellow per word.",
        "preset_box_kontras_name": "Contrast Box (TikTok Style)",
        "preset_box_kontras_desc": "Semi-transparent dark box behind high-contrast white text.",
        "preset_capcut_pill_name": "CapCut Pill (Active Word)",
        "preset_capcut_pill_desc": "Rounded highlight pill tracks each active word smoothly underneath stationary white text (CapCut style).",
        "preset_active_word_color_name": "Active Word Color (News/Doc)",
        "preset_active_word_color_desc": "Stationary bold-outlined text where only the currently spoken word changes to the highlight color (News/Documentary style).",
        "preset_newspaper_cutout_name": "Newspaper Cutout (Editorial)",
        "preset_newspaper_cutout_desc": "Investigative newspaper cutout style (1–3 words): crisp white paper boxes with bold black sans-serif text and tilted crimson boxes with bold white serif text. Wrap words in *asterisks* for manual emphasis.",
        # Status messages
        "status_ready": "Ready. Select a video to get started.",
        "status_video_loaded": "Video loaded. Click '1. Generate Transcript' or add subtitles manually.",
        "status_transcribing": "Running AI transcription (model {model})...",
        "status_transcribe_done_flagged": (
            "Transcription complete: {count} subtitle lines ({flagged} flagged for review)."
        ),
        "status_transcribe_done": "Transcription complete: {count} subtitle lines ready for review.",
        "status_transcribe_empty": "Transcription complete, but no speech was detected in this video.",
        "status_transcribe_failed": "Transcription failed or was cancelled.",
        "status_export_starting": "Starting subtitle burn-in render...",
        "status_export_done": "Done! Video saved to: {filename}",
        "status_export_failed": "Video export failed or was cancelled.",
        "status_cancel_transcribe": "Cancelling transcription...",
        "status_cancel_render": "Cancelling video render...",
        # Dialogs & validation
        "dlg_select_video_title": "Select Video File",
        "dlg_video_filter": "Video Files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.flv);;All Files (*.*)",
        "dlg_save_video_title": "Save Hardsub Video",
        "dlg_mp4_filter": "MP4 Video (*.mp4)",
        "dlg_video_error_title": "Failed to Read Video",
        "dlg_transcribe_error_title": "Transcription Failed",
        "dlg_check_subtitle_title": "Check Subtitles",
        "dlg_invalid_output_title": "Invalid Output Path",
        "dlg_invalid_output_msg": "Output file cannot directly overwrite the source video file.",
        "dlg_export_success_title": "Export Complete",
        "dlg_export_success_text": "Hardsub video has been created successfully!",
        "dlg_export_success_info": "File location:\n{path}",
        "btn_open_file": "▶ Open File",
        "btn_open_folder": "Open Output Folder",
        "btn_open_folder_short": "📂 Open Folder",
        "btn_close": "Close",
        "dlg_export_error_title": "Export Failed",
        "export_dlg_title": "Export Hardsub Video",
        "export_dlg_heading": "Exporting Hardsub Video",
        "export_dlg_done_heading": "Export Complete!",
        "export_dlg_done": "✓ Export Complete! Your hardsub video is ready.",
        "export_dlg_cancelling": "Cancelling...",
        "dlg_busy_close_title": "Process Running",
        "dlg_busy_close_msg": "A process is still running. Stop it and close the application?",
        "err_row_prefix": "Row {row}: {error}",
        "err_row_end_before_start": "Row {row}: End time must be greater than start time.",
        "err_empty_cues": "Subtitle list is empty. Generate a transcript or add rows first.",
        # Auto-updater
        "btn_check_update": "Check Updates",
        "btn_checking_update": "Checking...",
        "tooltip_check_update": "Check for application updates from GitHub",
        "update_dlg_available_title": "Update Available",
        "update_dlg_available_text": 'A new version of AutoHardsub is available: v{version} ("{codename}")',
        "update_dlg_available_info": (
            "Current version: v{local_version}\n\n"
            "Changelog:\n{changelog}\n\n"
            "Would you like to update now?"
        ),
        "update_no_changelog": "No changelog provided.",
        "btn_update_now": "Update Now",
        "btn_update_later": "Later",
        "update_dlg_uptodate_title": "Up to Date",
        "update_dlg_uptodate_msg": (
            'You are already running the latest version of AutoHardsub (v{version} — "{codename}").'
        ),
        "update_dlg_check_error_title": "Update Check Failed",
        "update_dlg_check_error_msg": (
            "Could not reach GitHub to check for updates.\n\nDetails: {error}"
        ),
        "update_progress_title": "Updating AutoHardsub",
        "update_status_backup": "Backing up existing files to _backup/...",
        "update_status_downloading": "Downloading update from GitHub...",
        "update_status_extracting": "Extracting and applying updated files...",
        "update_status_pip": "Installing updated dependencies (pip)...",
        "update_status_done": "Update complete! Restarting application...",
        "update_dlg_success_title": "Update Complete",
        "update_dlg_success_msg": (
            'AutoHardsub has been updated to v{version} ("{codename}").\n'
            "The application will restart now."
        ),
        "update_dlg_failed_title": "Update Failed",
        "update_dlg_failed_msg": (
            "The update failed and your previous files were automatically restored from _backup/.\n\n"
            "Details: {error}"
        ),
        "update_dlg_busy_msg": (
            "Please finish or cancel the active transcription/render task before updating."
        ),
        # Live preview
        "preview_title": "Live Style Preview",
        "tooltip_preview_zoom": "Scroll to zoom, drag to pan, double-click or click this button to reset to 100%",
        # Auto-tag keywords
        "btn_auto_tag_keywords": "✨ Auto-Tag Keywords",
        "tooltip_auto_tag_keywords": (
            "Automatically wrap numbers, dates, proper nouns, and high-impact words in *asterisks* "
            "for Newspaper Cutout style (lines already containing * are skipped)."
        ),
        "status_auto_tag_done": "✨ Tagged {words} keywords across {lines} subtitle lines.",
        "status_auto_tag_none": "No new keywords were tagged (lines already containing * were skipped).",
        # Help dialog
        "btn_help": "? Help",
        "tooltip_help": "Open quick guide for subtitle presets, custom fonts, and settings storage",
        "help_dlg_title": "AutoHardsub Help",
        "help_header_title": "AutoHardsub Quick Guide",
        "help_header_subtitle": "Tips for subtitle presets, editorial keyword tagging, custom fonts, and persistent settings.",
        "help_sec1_title": "1. Subtitle Style Guide (Presets)",
        "help_sec1_body": (
            "<ul style='margin:0; padding-left:18px;'>"
            "<li><b>CapCut Pill (Active Word):</b> Stationary 1–2 line white text with a rounded highlight pill tracking the currently spoken word.</li>"
            "<li><b>Active Word Color (News/Doc):</b> Bold outlined stationary text where only the active word switches to your <i>Highlight Color</i>.</li>"
            "<li><b>Newspaper Cutout (Editorial):</b> Investigative 1–3 word horizontal blocks — crisp light-gray paper boxes with bold black sans-serif text, paired with slightly tilted (±1.6°) crimson boxes with bold white serif text for emphasized words.</li>"
            "<li><b>Classic Presets (YouTube Clean, Reels Pop, Karaoke Wipe, Contrast Box):</b> Full control over font, colors, outline width, and semi-transparent background box.</li>"
            "</ul>"
        ),
        "help_sec2_title": "2. Newspaper Cutout Tips (*Keywords*)",
        "help_sec2_body": (
            "Wrap any word in asterisks like <b>*Baduy*</b> or <b>*fire*</b> in the subtitle editor to force "
            "the tilted red serif cutout box.<br><br>"
            "Click <b>✨ Auto-Tag Keywords</b> above the subtitle table to automatically tag numbers, dates/days, "
            "mid-sentence proper nouns, and dramatic news words. Lines that already contain <b>*</b> are skipped "
            "so your manual tags stay untouched."
        ),
        "help_sec3_title": "3. Adding Custom Fonts",
        "help_sec3_body": (
            "Drop any <b>.ttf</b> or <b>.otf</b> font file into the folder below and restart AutoHardsub:<br>"
            "<code style='color:#7dd3fc;'>{fonts_dir}</code><br><br>"
            "Your custom fonts will automatically appear at the very top of the <b>Font Family</b> dropdown."
        ),
        "help_sec4_title": "4. Auto-Update & Settings Location",
        "help_sec4_body": (
            "Your last-used preferences (UI language, preset, font, colors, vertical margin, preview aspect, and AI model) "
            "are saved safely outside the application folder so GitHub auto-updates never overwrite them:<br>"
            "<code style='color:#7dd3fc;'>{settings_dir}\\user_settings.json</code>"
        ),
        "help_btn_open_fonts": "Open Fonts Folder (assets/fonts)",
    },
}


def normalize_lang(lang_code: str | None) -> str:
    """Normalize a language code to a supported UI language ('id' or 'en')."""
    if not lang_code:
        return DEFAULT_LANGUAGE
    code = lang_code.strip().lower()
    return code if code in TRANSLATIONS else DEFAULT_LANGUAGE


def tr(lang_code: str, key: str, **kwargs: Any) -> str:
    """Translate a key for the given language with optional format placeholders."""
    lang = normalize_lang(lang_code)
    template = TRANSLATIONS[lang].get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template
    return template
