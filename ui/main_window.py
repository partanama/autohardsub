"""Main application window for AutoHardsub with bilingual UI and custom subtitle styling."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSlider,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.ass_engine import AssConfig
from core.hw_detect import HardwareProfile, detect_hardware
from core.i18n import SUPPORTED_LANGUAGES, normalize_lang, tr
from core.media_probe import MediaProbeError, VideoInfo, probe_video
from core.paths import get_binary_status, get_fonts_dir, get_models_dir
from core.presets import PRESETS, SubtitlePreset, get_preset
from core.updater import (
    UpdateCheckWorker,
    UpdateInstallWorker,
    load_local_version,
    restart_application,
)
from workers.render_worker import RenderWorker
from workers.transcribe_worker import TranscribeWorker

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".flv"}
_FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}

_AUDIO_LANGUAGE_CODES: tuple[tuple[str, str], ...] = (
    ("lang_auto", "auto"),
    ("lang_id", "id"),
    ("lang_en", "en"),
)

_MODEL_CODES: tuple[tuple[str, str], ...] = (
    ("model_base", "base"),
    ("model_small", "small"),
    ("model_large_v3", "large-v3"),
)

_COMMON_SYSTEM_FONTS: tuple[str, ...] = (
    "Arial",
    "Segoe UI",
    "Impact",
    "Verdana",
    "Tahoma",
    "Trebuchet MS",
    "Calibri",
    "Georgia",
    "Consolas",
)

_CONFIDENCE_MODERATE_THRESHOLD = 0.65
_CONFIDENCE_LOW_THRESHOLD = 0.45
_MODERATE_TINT_HEX = "#4A3518"
_LOW_TINT_HEX = "#4E2222"


def format_timestamp(seconds: float) -> str:
    """Format seconds into readable MM:SS.cc or HH:MM:SS.cc timestamp."""
    total_cs = max(0, int(round(float(seconds) * 100)))
    cs = total_cs % 100
    total_sec = total_cs // 100
    sec = total_sec % 60
    total_min = total_sec // 60
    minute = total_min % 60
    hour = total_min // 60
    if hour > 0:
        return f"{hour:02d}:{minute:02d}:{sec:02d}.{cs:02d}"
    return f"{minute:02d}:{sec:02d}.{cs:02d}"


def parse_timestamp(value: str) -> float:
    """Parse SS(.cc), MM:SS(.cc), or HH:MM:SS(.cc) string into seconds."""
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        raise ValueError("Waktu tidak boleh kosong.")

    parts = cleaned.split(":")
    if len(parts) == 1:
        sec = float(parts[0])
        if sec < 0:
            raise ValueError("Waktu tidak boleh negatif.")
        return sec
    if len(parts) == 2:
        minute = int(parts[0])
        sec = float(parts[1])
        if minute < 0 or sec < 0 or sec >= 60:
            raise ValueError("Format menit/detik tidak valid.")
        return (minute * 60.0) + sec
    if len(parts) == 3:
        hour = int(parts[0])
        minute = int(parts[1])
        sec = float(parts[2])
        if hour < 0 or minute < 0 or minute >= 60 or sec < 0 or sec >= 60:
            raise ValueError("Format jam/menit/detik tidak valid.")
        return (hour * 3600.0) + (minute * 60.0) + sec

    raise ValueError("Gunakan format MM:SS.cc atau HH:MM:SS.cc.")


def _contrast_text_color(hex_rgb: str) -> str:
    """Return dark or light foreground hex color for legible text on a color swatch."""
    color = QColor(hex_rgb)
    if not color.isValid():
        return "#ffffff"
    luminance = (0.299 * color.red()) + (0.587 * color.green()) + (0.114 * color.blue())
    return "#0f172a" if luminance > 150 else "#f8fafc"


def _discover_available_fonts() -> list[str]:
    """Load bundled fonts from assets/fonts/ and merge with common system fonts."""
    discovered: list[str] = []
    seen_lower: set[str] = set()

    fonts_dir = get_fonts_dir()
    if fonts_dir.is_dir():
        try:
            for entry in sorted(fonts_dir.iterdir(), key=lambda p: p.name.lower()):
                if entry.is_file() and entry.suffix.lower() in _FONT_EXTENSIONS:
                    font_id = QFontDatabase.addApplicationFont(str(entry))
                    if font_id >= 0:
                        for family in QFontDatabase.applicationFontFamilies(font_id):
                            clean = family.strip()
                            if clean and clean.lower() not in seen_lower:
                                discovered.append(clean)
                                seen_lower.add(clean.lower())
        except OSError:
            pass

    for family in _COMMON_SYSTEM_FONTS:
        if family.lower() not in seen_lower:
            discovered.append(family)
            seen_lower.add(family.lower())

    return discovered


class VideoDropZone(QFrame):
    """Drag-and-drop card displaying the selected video and quick browse trigger."""

    def __init__(self, on_file_dropped, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_file_dropped = on_file_dropped
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in _VIDEO_EXTENSIONS:
                    self.setProperty("dragActive", True)
                    self.style().unpolish(self)
                    self.style().polish(self)
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("dragActive", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            if url.isLocalFile():
                file_path = Path(url.toLocalFile())
                if file_path.is_file() and file_path.suffix.lower() in _VIDEO_EXTENSIONS:
                    self._on_file_dropped(str(file_path))
                    event.acceptProposedAction()
                    return
        event.ignore()


class MainWindow(QMainWindow):
    """Primary AutoHardsub desktop interface."""

    def __init__(self) -> None:
        super().__init__()
        self._lang: str = "en"
        self._status_i18n_key: str | None = "status_ready"
        self._status_i18n_kwargs: dict[str, object] = {}

        self.resize(1360, 780)
        self.setMinimumSize(1180, 700)
        self.setAcceptDrops(True)

        self._video_info: VideoInfo | None = None
        self._version_info: dict[str, str] = load_local_version()
        self._hardware_profile: HardwareProfile = detect_hardware()
        self._transcribe_worker: TranscribeWorker | None = None
        self._render_worker: RenderWorker | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_install_worker: UpdateInstallWorker | None = None
        self._update_progress_dialog: QProgressDialog | None = None
        self._is_busy = False
        self._updating_table = False

        # Live subtitle color state (RGB hex "#RRGGBB")
        self._primary_text_color: str = "#FFFFFF"
        self._highlight_color: str = "#FFFF00"
        self._outline_color: str = "#000000"
        self._bg_box_color: str = "#000000"

        self._build_ui()
        self._apply_hardware_badge()
        self._check_missing_binaries()
        self._on_preset_changed(0)
        self.apply_language(self._lang)
        self._update_action_states()

        # Silent post-launch update check (1.5s delay)
        QTimer.singleShot(1500, self._start_silent_update_check)

    def _t(self, key: str, **kwargs) -> str:
        return tr(self._lang, key, **kwargs)

    def _set_status_key(self, key: str, **kwargs) -> None:
        self._status_i18n_key = key
        self._status_i18n_kwargs = kwargs
        self.status_label.setText(self._t(key, **kwargs))

    def _set_raw_status(self, text: str) -> None:
        self._status_i18n_key = None
        self._status_i18n_kwargs = {}
        self.status_label.setText(text)

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(10)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)

        self.app_title_label = QLabel()
        self.app_title_label.setObjectName("AppTitle")

        codename = self._version_info.get("codename", "Jemboed Kecelup Santen")
        version = self._version_info.get("version", "1.0.0")
        self.build_version_label = QLabel(
            f'Build Version : "{codename}" (v{version})'
        )
        self.build_version_label.setObjectName("BuildVersionLabel")
        self.build_version_label.setStyleSheet(
            "font-size: 11px; font-style: italic; color: #94A3B8; margin-left: 10px;"
        )

        title_row.addWidget(self.app_title_label, alignment=Qt.AlignmentFlag.AlignBaseline)
        title_row.addWidget(
            self.build_version_label, alignment=Qt.AlignmentFlag.AlignBaseline
        )
        title_row.addStretch(1)

        self.app_subtitle_label = QLabel()
        self.app_subtitle_label.setObjectName("AppSubtitle")
        title_box.addLayout(title_row)
        title_box.addWidget(self.app_subtitle_label)

        header_layout.addLayout(title_box, stretch=1)

        self.hw_badge_label = QLabel()
        self.hw_badge_label.setObjectName("HardwareBadge")
        header_layout.addWidget(
            self.hw_badge_label,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.check_update_btn = QPushButton()
        self.check_update_btn.setObjectName("MiniButton")
        self.check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_update_btn.clicked.connect(self._on_check_update_clicked)
        header_layout.addWidget(
            self.check_update_btn,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        self.ui_lang_combo = QComboBox()
        self.ui_lang_combo.setObjectName("LangSwitcher")
        for label, code in SUPPORTED_LANGUAGES:
            self.ui_lang_combo.addItem(label, code)
        self.ui_lang_combo.currentIndexChanged.connect(self._on_ui_language_changed)
        header_layout.addWidget(
            self.ui_lang_combo,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

        root_layout.addLayout(header_layout)

        # Warning banner when external binaries are missing
        self.warning_banner = QLabel()
        self.warning_banner.setObjectName("WarningBanner")
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setVisible(False)
        root_layout.addWidget(self.warning_banner)

        # Main 2-Column Studio Split Layout below header
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # Left Column (stretch=62): Step 1 (Input & Transcribe) + Step 2 (Subtitle Table Editor)
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Step 1: Video Input & Transcription Controls
        step1_card = QFrame()
        step1_card.setObjectName("Card")
        step1_layout = QVBoxLayout(step1_card)
        step1_layout.setContentsMargins(14, 12, 14, 12)
        step1_layout.setSpacing(10)

        self.step1_title_label = QLabel()
        self.step1_title_label.setObjectName("SectionTitle")
        step1_layout.addWidget(self.step1_title_label)

        self.drop_zone = VideoDropZone(self._load_video)
        self.drop_zone.setMinimumHeight(74)
        drop_layout = QHBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(16, 14, 16, 14)
        drop_layout.setSpacing(12)

        video_text_col = QVBoxLayout()
        video_text_col.setSpacing(4)
        self.video_name_label = QLabel()
        self.video_name_label.setObjectName("VideoNameLabel")
        self.video_meta_label = QLabel()
        self.video_meta_label.setObjectName("MutedLabel")
        self.video_meta_label.setWordWrap(True)
        video_text_col.addWidget(self.video_name_label)
        video_text_col.addWidget(self.video_meta_label)

        self.browse_video_btn = QPushButton()
        self.browse_video_btn.setObjectName("SecondaryButton")
        self.browse_video_btn.clicked.connect(self._on_browse_video)

        drop_layout.addLayout(video_text_col, stretch=1)
        drop_layout.addWidget(
            self.browse_video_btn, alignment=Qt.AlignmentFlag.AlignVCenter
        )
        step1_layout.addWidget(self.drop_zone)

        controls_row = QHBoxLayout()
        controls_row.setSpacing(10)

        self.audio_lang_label = QLabel()
        self.lang_combo = QComboBox()
        for key, code in _AUDIO_LANGUAGE_CODES:
            self.lang_combo.addItem(self._t(key), code)

        self.model_label = QLabel()
        self.model_combo = QComboBox()
        for key, code in _MODEL_CODES:
            self.model_combo.addItem(self._t(key), code)

        self.transcribe_btn = QPushButton()
        self.transcribe_btn.setObjectName("ActionButton")
        self.transcribe_btn.clicked.connect(self._on_start_transcribe)

        controls_row.addWidget(self.audio_lang_label)
        controls_row.addWidget(self.lang_combo, stretch=1)
        controls_row.addSpacing(6)
        controls_row.addWidget(self.model_label)
        controls_row.addWidget(self.model_combo, stretch=1)
        controls_row.addSpacing(8)
        controls_row.addWidget(self.transcribe_btn)
        step1_layout.addLayout(controls_row)

        left_col.addWidget(step1_card)

        # Step 2: Interactive Subtitle Editor Table
        step2_card = QFrame()
        step2_card.setObjectName("Card")
        step2_layout = QVBoxLayout(step2_card)
        step2_layout.setContentsMargins(14, 12, 14, 12)
        step2_layout.setSpacing(8)

        table_header = QHBoxLayout()
        self.step2_title_label = QLabel()
        self.step2_title_label.setObjectName("SectionTitle")
        self.cue_count_label = QLabel()
        self.cue_count_label.setObjectName("MutedLabel")

        self.add_row_btn = QPushButton()
        self.add_row_btn.setObjectName("MiniButton")
        self.add_row_btn.clicked.connect(self._on_add_row)

        self.remove_row_btn = QPushButton()
        self.remove_row_btn.setObjectName("MiniButton")
        self.remove_row_btn.clicked.connect(self._on_remove_row)

        table_header.addWidget(self.step2_title_label)
        table_header.addSpacing(8)
        table_header.addWidget(self.cue_count_label)
        table_header.addStretch(1)
        table_header.addWidget(self.add_row_btn)
        table_header.addWidget(self.remove_row_btn)
        step2_layout.addLayout(table_header)

        self.confidence_legend_label = QLabel()
        self.confidence_legend_label.setObjectName("MutedLabel")
        self.confidence_legend_label.setWordWrap(True)
        step2_layout.addWidget(self.confidence_legend_label)

        self.cue_table = QTableWidget(0, 3)
        self.cue_table.setAlternatingRowColors(True)
        self.cue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.cue_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.cue_table.verticalHeader().setDefaultSectionSize(30)
        self.cue_table.verticalHeader().setVisible(False)
        self.cue_table.itemSelectionChanged.connect(self._update_action_states)
        self.cue_table.itemChanged.connect(self._on_table_item_changed)

        header = self.cue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.cue_table.setColumnWidth(0, 110)
        self.cue_table.setColumnWidth(1, 110)

        step2_layout.addWidget(self.cue_table, stretch=1)
        left_col.addWidget(step2_card, stretch=1)

        content_layout.addLayout(left_col, stretch=62)

        # Right Column (stretch=38, minimumWidth=430): Step 3 (Subtitle Styling & Export)
        step3_card = QFrame()
        step3_card.setObjectName("Card")
        step3_card.setMinimumWidth(430)
        step3_layout = QVBoxLayout(step3_card)
        step3_layout.setContentsMargins(16, 12, 16, 12)
        step3_layout.setSpacing(10)

        self.step3_title_label = QLabel()
        self.step3_title_label.setObjectName("SectionTitle")
        step3_layout.addWidget(self.step3_title_label)

        # 1. Preset Section
        preset_section = QVBoxLayout()
        preset_section.setSpacing(4)
        self.preset_label = QLabel()
        self.preset_combo = QComboBox()
        for preset in PRESETS:
            self.preset_combo.addItem(preset.name, preset.id)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)

        self.preset_desc_label = QLabel()
        self.preset_desc_label.setObjectName("MutedLabel")
        self.preset_desc_label.setWordWrap(True)

        preset_section.addWidget(self.preset_label)
        preset_section.addWidget(self.preset_combo)
        preset_section.addWidget(self.preset_desc_label)
        step3_layout.addLayout(preset_section)

        # 2. Typography Section
        typo_section = QVBoxLayout()
        typo_section.setSpacing(8)

        font_family_group = QVBoxLayout()
        font_family_group.setSpacing(4)
        self.font_family_label = QLabel()
        self.font_family_combo = QComboBox()
        for font_name in _discover_available_fonts():
            self.font_family_combo.addItem(font_name, font_name)
        font_family_group.addWidget(self.font_family_label)
        font_family_group.addWidget(self.font_family_combo)
        typo_section.addLayout(font_family_group)

        size_outline_row = QHBoxLayout()
        size_outline_row.setSpacing(10)

        font_size_col = QVBoxLayout()
        font_size_col.setSpacing(4)
        self.font_size_label = QLabel()
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(16, 150)
        self.font_size_spin.setSuffix(" px")
        font_size_col.addWidget(self.font_size_label)
        font_size_col.addWidget(self.font_size_spin)

        outline_width_col = QVBoxLayout()
        outline_width_col.setSpacing(4)
        self.outline_width_label = QLabel()
        self.outline_width_spin = QDoubleSpinBox()
        self.outline_width_spin.setRange(0.0, 20.0)
        self.outline_width_spin.setSingleStep(0.5)
        self.outline_width_spin.setDecimals(1)
        self.outline_width_spin.setSuffix(" px")
        outline_width_col.addWidget(self.outline_width_label)
        outline_width_col.addWidget(self.outline_width_spin)

        size_outline_row.addLayout(font_size_col, stretch=1)
        size_outline_row.addLayout(outline_width_col, stretch=1)
        typo_section.addLayout(size_outline_row)

        step3_layout.addLayout(typo_section)

        # 3. Color Palette Grid (2x2 Grid) + Background Box Controls
        color_section = QVBoxLayout()
        color_section.setSpacing(8)

        color_grid = QGridLayout()
        color_grid.setHorizontalSpacing(10)
        color_grid.setVerticalSpacing(8)
        color_grid.setColumnStretch(0, 1)
        color_grid.setColumnStretch(1, 1)

        self.primary_color_label = QLabel()
        self.primary_color_btn = QPushButton()
        self.primary_color_btn.setObjectName("ColorSwatchButton")
        self.primary_color_btn.setFixedHeight(32)
        self.primary_color_btn.clicked.connect(lambda: self._pick_color("primary"))

        primary_cell = QVBoxLayout()
        primary_cell.setSpacing(4)
        primary_cell.addWidget(self.primary_color_label)
        primary_cell.addWidget(self.primary_color_btn)

        self.highlight_color_label = QLabel()
        self.highlight_color_btn = QPushButton()
        self.highlight_color_btn.setObjectName("ColorSwatchButton")
        self.highlight_color_btn.setFixedHeight(32)
        self.highlight_color_btn.clicked.connect(lambda: self._pick_color("highlight"))

        highlight_cell = QVBoxLayout()
        highlight_cell.setSpacing(4)
        highlight_cell.addWidget(self.highlight_color_label)
        highlight_cell.addWidget(self.highlight_color_btn)

        self.outline_color_label = QLabel()
        self.outline_color_btn = QPushButton()
        self.outline_color_btn.setObjectName("ColorSwatchButton")
        self.outline_color_btn.setFixedHeight(32)
        self.outline_color_btn.clicked.connect(lambda: self._pick_color("outline"))

        outline_cell = QVBoxLayout()
        outline_cell.setSpacing(4)
        outline_cell.addWidget(self.outline_color_label)
        outline_cell.addWidget(self.outline_color_btn)

        self.bg_box_color_label = QLabel()
        self.bg_box_color_btn = QPushButton()
        self.bg_box_color_btn.setObjectName("ColorSwatchButton")
        self.bg_box_color_btn.setFixedHeight(32)
        self.bg_box_color_btn.clicked.connect(lambda: self._pick_color("bg_box"))

        bg_color_cell = QVBoxLayout()
        bg_color_cell.setSpacing(4)
        bg_color_cell.addWidget(self.bg_box_color_label)
        bg_color_cell.addWidget(self.bg_box_color_btn)

        color_grid.addLayout(primary_cell, 0, 0)
        color_grid.addLayout(highlight_cell, 0, 1)
        color_grid.addLayout(outline_cell, 1, 0)
        color_grid.addLayout(bg_color_cell, 1, 1)
        color_section.addLayout(color_grid)

        self.bg_box_checkbox = QCheckBox()
        self.bg_box_checkbox.toggled.connect(self._on_bg_box_toggled)
        color_section.addWidget(self.bg_box_checkbox)

        bg_opacity_row = QHBoxLayout()
        bg_opacity_row.setSpacing(8)
        self.bg_opacity_label = QLabel()
        self.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_slider.setValue(50)
        self.bg_opacity_value_label = QLabel("50%")
        self.bg_opacity_value_label.setMinimumWidth(44)
        self.bg_opacity_value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.bg_opacity_slider.valueChanged.connect(
            lambda val: self.bg_opacity_value_label.setText(f"{val}%")
        )
        bg_opacity_row.addWidget(self.bg_opacity_label)
        bg_opacity_row.addWidget(self.bg_opacity_slider, stretch=1)
        bg_opacity_row.addWidget(self.bg_opacity_value_label)
        color_section.addLayout(bg_opacity_row)

        step3_layout.addLayout(color_section)

        # 4. Position Section
        margin_row = QHBoxLayout()
        margin_row.setSpacing(8)
        self.margin_label = QLabel()
        self.margin_v_slider = QSlider(Qt.Orientation.Horizontal)
        self.margin_v_slider.setRange(10, 500)
        self.margin_v_value_label = QLabel("60 px")
        self.margin_v_value_label.setMinimumWidth(48)
        self.margin_v_value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.margin_v_slider.valueChanged.connect(
            lambda val: self.margin_v_value_label.setText(f"{val} px")
        )
        margin_row.addWidget(self.margin_label)
        margin_row.addWidget(self.margin_v_slider, stretch=1)
        margin_row.addWidget(self.margin_v_value_label)
        step3_layout.addLayout(margin_row)

        # Push export footer cleanly to the bottom of the right column
        step3_layout.addStretch(1)

        # 5. Bottom Sticky Export Footer
        export_footer = QVBoxLayout()
        export_footer.setSpacing(8)

        output_group = QVBoxLayout()
        output_group.setSpacing(4)
        self.output_label = QLabel()
        output_row = QHBoxLayout()
        output_row.setSpacing(8)
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        self.output_path_edit.setFixedHeight(32)
        self.browse_output_btn = QPushButton()
        self.browse_output_btn.setObjectName("SecondaryButton")
        self.browse_output_btn.setMinimumWidth(76)
        self.browse_output_btn.setFixedHeight(32)
        self.browse_output_btn.setStyleSheet(
            "QPushButton#SecondaryButton { padding: 4px 10px; }"
        )
        self.browse_output_btn.clicked.connect(self._on_browse_output)
        output_row.addWidget(self.output_path_edit, stretch=1)
        output_row.addWidget(self.browse_output_btn)
        output_group.addWidget(self.output_label)
        output_group.addLayout(output_row)
        export_footer.addLayout(output_group)

        cta_row = QHBoxLayout()
        cta_row.setSpacing(8)
        self.export_btn = QPushButton()
        self.export_btn.setObjectName("PrimaryButton")
        self.export_btn.setFixedHeight(42)
        self.export_btn.clicked.connect(self._on_start_export)

        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("DangerButton")
        self.cancel_btn.setFixedHeight(42)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._on_cancel_worker)

        cta_row.addWidget(self.export_btn, stretch=1)
        cta_row.addWidget(self.cancel_btn)
        export_footer.addLayout(cta_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setTextVisible(True)
        export_footer.addWidget(self.progress_bar)

        self.status_label = QLabel()
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setWordWrap(True)
        export_footer.addWidget(self.status_label)

        step3_layout.addLayout(export_footer)

        content_layout.addWidget(step3_card, stretch=38)
        root_layout.addLayout(content_layout, stretch=1)

    def _on_ui_language_changed(self, _index: int) -> None:
        lang_code = str(self.ui_lang_combo.currentData() or "en")
        self.apply_language(lang_code)

    def apply_language(self, lang_code: str) -> None:
        """Dynamically switch all visible UI texts to the chosen language ('id' or 'en')."""
        self._lang = normalize_lang(lang_code)

        # Keep language combo synced without triggering recursion
        idx = self.ui_lang_combo.findData(self._lang)
        if idx >= 0 and self.ui_lang_combo.currentIndex() != idx:
            self.ui_lang_combo.blockSignals(True)
            self.ui_lang_combo.setCurrentIndex(idx)
            self.ui_lang_combo.blockSignals(False)

        self.setWindowTitle(self._t("window_title"))
        self.app_title_label.setText(self._t("app_title"))
        self.app_subtitle_label.setText(self._t("app_subtitle"))
        self.ui_lang_combo.setToolTip(self._t("ui_lang_tooltip"))
        self._refresh_update_button_label()
        self.check_update_btn.setToolTip(self._t("tooltip_check_update"))

        self._apply_hardware_badge()
        self._check_missing_binaries()

        # Step 1
        self.step1_title_label.setText(self._t("step1_title"))
        self.browse_video_btn.setText(self._t("btn_browse_video"))
        self._refresh_video_labels()

        self.audio_lang_label.setText(self._t("label_audio_lang"))
        for i, (key, _code) in enumerate(_AUDIO_LANGUAGE_CODES):
            self.lang_combo.setItemText(i, self._t(key))

        self.model_label.setText(self._t("label_ai_model"))
        for i, (key, _code) in enumerate(_MODEL_CODES):
            self.model_combo.setItemText(i, self._t(key))
        self.model_combo.setToolTip(self._t("tooltip_model", models_dir=get_models_dir()))
        self.transcribe_btn.setText(self._t("btn_transcribe"))

        # Step 2
        self.step2_title_label.setText(self._t("step2_title"))
        self._update_cue_count()
        self.add_row_btn.setText(self._t("btn_add_row"))
        self.remove_row_btn.setText(self._t("btn_remove_row"))
        self.confidence_legend_label.setText(self._t("confidence_legend"))
        self.cue_table.setHorizontalHeaderLabels(
            [self._t("col_start"), self._t("col_end"), self._t("col_text")]
        )
        self._refresh_table_tooltips()

        # Step 3
        self.step3_title_label.setText(self._t("step3_title"))
        self.preset_label.setText(self._t("label_preset"))
        for i, preset in enumerate(PRESETS):
            self.preset_combo.setItemText(i, self._t(f"preset_{preset.id}_name"))
        current_preset = self._current_preset()
        self.preset_desc_label.setText(self._t(f"preset_{current_preset.id}_desc"))

        self.font_family_label.setText(self._t("label_font_family"))
        self.font_size_label.setText(self._t("label_font_size"))
        self.outline_width_label.setText(self._t("label_outline_width"))
        self.margin_label.setText(self._t("label_margin_v"))

        self.primary_color_label.setText(self._t("label_primary_color"))
        self.highlight_color_label.setText(self._t("label_highlight_color"))
        self.outline_color_label.setText(self._t("label_outline_color"))
        self.bg_box_color_label.setText(self._t("label_bg_box_color"))
        self.bg_box_checkbox.setText(self._t("chk_enable_bg_box"))
        self.bg_opacity_label.setText(self._t("label_bg_box_opacity"))

        self.primary_color_btn.setToolTip(self._t("tooltip_primary_color"))
        self.highlight_color_btn.setToolTip(self._t("tooltip_highlight_color"))
        self.outline_color_btn.setToolTip(self._t("tooltip_outline_color"))
        self.bg_box_color_btn.setToolTip(self._t("tooltip_bg_box_color"))
        self.bg_box_checkbox.setToolTip(self._t("tooltip_bg_box_toggle"))
        self.bg_opacity_slider.setToolTip(self._t("tooltip_bg_box_opacity"))

        self.output_label.setText(self._t("label_output_file"))
        self.output_path_edit.setPlaceholderText(self._t("placeholder_output"))
        self.browse_output_btn.setText(self._t("btn_browse_output"))
        self.cancel_btn.setText(self._t("btn_cancel"))
        self.export_btn.setText(self._t("btn_export"))

        if self._status_i18n_key:
            self.status_label.setText(
                self._t(self._status_i18n_key, **self._status_i18n_kwargs)
            )

    def _refresh_video_labels(self) -> None:
        if self._video_info is None:
            self.video_name_label.setText(self._t("drop_prompt"))
            self.video_meta_label.setText(self._t("drop_hint"))
            return

        info = self._video_info
        self.video_name_label.setText(Path(info.path).name)
        duration_text = format_timestamp(info.duration_seconds).rsplit(".", 1)[0]
        if info.height > info.width:
            orientation = self._t("orientation_vertical")
        elif info.height == info.width:
            orientation = self._t("orientation_square")
        else:
            orientation = self._t("orientation_horizontal")
        self.video_meta_label.setText(
            self._t(
                "video_meta_format",
                width=info.width,
                height=info.height,
                orientation=orientation,
                duration=duration_text,
            )
        )

    def _apply_hardware_badge(self) -> None:
        profile = self._hardware_profile
        encoder_key_map = {
            "h264_nvenc": "hw_render_nvenc",
            "h264_qsv": "hw_render_qsv",
            "h264_mf": "hw_render_mf",
            "libx264": "hw_render_cpu",
        }

        if not profile.use_gpu and not profile.vulkan_available:
            badge_text = self._t("hw_badge_cpu_only")
            gpu_prop = "false"
        else:
            transcribe_key = (
                "hw_transcribe_vulkan"
                if profile.vulkan_available
                else "hw_transcribe_cpu"
            )
            render_key = encoder_key_map.get(profile.encoder_name, "hw_render_cpu")
            badge_text = self._t(
                "hw_badge_format",
                transcribe=self._t(transcribe_key),
                render=self._t(render_key),
            )
            gpu_prop = "true" if profile.use_gpu else "partial"

        self.hw_badge_label.setText(badge_text)
        self.hw_badge_label.setProperty("gpuActive", gpu_prop)
        if profile.detail:
            self.hw_badge_label.setToolTip(profile.detail)
        self.hw_badge_label.style().unpolish(self.hw_badge_label)
        self.hw_badge_label.style().polish(self.hw_badge_label)

    def _check_missing_binaries(self) -> None:
        status = get_binary_status()
        missing: list[str] = []
        if status.get("whisper_cli") is None and status.get("opencaption") is None:
            missing.append("whisper-cli.exe")
        if status.get("ffmpeg") is None:
            missing.append("ffmpeg.exe")
        if status.get("ffprobe") is None:
            missing.append("ffprobe.exe")
        if missing:
            missing_list = ", ".join(missing)
            self.warning_banner.setText(
                self._t("warning_missing_bins", missing=missing_list)
            )
            self.warning_banner.setVisible(True)
        else:
            self.warning_banner.setVisible(False)

    def _update_swatch_button(self, button: QPushButton, hex_rgb: str) -> None:
        normalized = hex_rgb.upper()
        fg = _contrast_text_color(normalized)
        button.setText(normalized)
        button.setStyleSheet(
            f"QPushButton#ColorSwatchButton {{"
            f" background-color: {normalized};"
            f" color: {fg};"
            f" border: 1px solid #64748b;"
            f"}}"
            f"QPushButton#ColorSwatchButton:hover:!disabled {{"
            f" border: 2px solid #38bdf8;"
            f"}}"
            f"QPushButton#ColorSwatchButton:disabled {{"
            f" background-color: #334155;"
            f" color: #64748b;"
            f" border: 1px solid #334155;"
            f"}}"
        )

    def _sync_color_swatches(self) -> None:
        self._update_swatch_button(self.primary_color_btn, self._primary_text_color)
        self._update_swatch_button(self.highlight_color_btn, self._highlight_color)
        self._update_swatch_button(self.outline_color_btn, self._outline_color)
        self._update_swatch_button(self.bg_box_color_btn, self._bg_box_color)

    def _on_bg_box_toggled(self, checked: bool) -> None:
        controls_enabled = (not self._is_busy) and checked
        self.bg_box_color_btn.setEnabled(controls_enabled)
        self.bg_opacity_slider.setEnabled(controls_enabled)
        self.outline_color_btn.setEnabled((not self._is_busy) and (not checked))

    def _pick_color(self, target: str) -> None:
        color_map = {
            "primary": (self._primary_text_color, "label_primary_color"),
            "highlight": (self._highlight_color, "label_highlight_color"),
            "outline": (self._outline_color, "label_outline_color"),
            "bg_box": (self._bg_box_color, "label_bg_box_color"),
        }
        current_hex, label_key = color_map[target]
        title = self._t("color_dialog_title", target=self._t(label_key).rstrip(":"))
        chosen = QColorDialog.getColor(QColor(current_hex), self, title)
        if not chosen.isValid():
            return

        hex_val = chosen.name().upper()
        if target == "primary":
            self._primary_text_color = hex_val
        elif target == "highlight":
            self._highlight_color = hex_val
        elif target == "outline":
            self._outline_color = hex_val
        elif target == "bg_box":
            self._bg_box_color = hex_val
        self._sync_color_swatches()

    def _build_ass_config(self) -> AssConfig:
        """Assemble current custom UI styling overrides into an AssConfig instance."""
        return AssConfig(
            font_name=str(self.font_family_combo.currentData() or self.font_family_combo.currentText()),
            font_size=self.font_size_spin.value(),
            margin_v=self.margin_v_slider.value(),
            outline_width=round(self.outline_width_spin.value(), 1),
            primary_text_color=self._primary_text_color,
            highlight_color=self._highlight_color,
            outline_color=self._outline_color,
            enable_bg_box=self.bg_box_checkbox.isChecked(),
            bg_box_color=self._bg_box_color,
            bg_box_opacity=self.bg_opacity_slider.value(),
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._is_busy:
            event.ignore()
            return
        mime = event.mimeData()
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in _VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if self._is_busy:
            event.ignore()
            return
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_file() and path.suffix.lower() in _VIDEO_EXTENSIONS:
                    self._load_video(str(path))
                    event.acceptProposedAction()
                    return
        event.ignore()

    def _on_browse_video(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._t("dlg_select_video_title"),
            "",
            self._t("dlg_video_filter"),
        )
        if selected:
            self._load_video(selected)

    def _load_video(self, path_str: str) -> None:
        try:
            info = probe_video(path_str)
        except MediaProbeError as exc:
            QMessageBox.warning(self, self._t("dlg_video_error_title"), str(exc))
            return

        self._video_info = info
        src = Path(info.path)
        self._refresh_video_labels()

        default_output = src.with_name(f"{src.stem}_hardsub.mp4")
        self.output_path_edit.setText(str(default_output))

        max_margin = max(200, info.height // 2)
        self.margin_v_slider.setRange(10, max_margin)
        current_preset = self._current_preset()
        recommended_margin = (
            current_preset.default_margin_v
            if info.is_vertical
            else min(current_preset.default_margin_v, max(40, info.height // 8))
        )
        self.margin_v_slider.setValue(min(max_margin, recommended_margin))

        self._set_status_key("status_video_loaded")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._update_action_states()

    def _on_browse_output(self) -> None:
        initial = self.output_path_edit.text().strip()
        selected, _ = QFileDialog.getSaveFileName(
            self,
            self._t("dlg_save_video_title"),
            initial or "output_hardsub.mp4",
            self._t("dlg_mp4_filter"),
        )
        if selected:
            if not selected.lower().endswith(".mp4"):
                selected = f"{selected}.mp4"
            self.output_path_edit.setText(selected)

    def _current_preset(self) -> SubtitlePreset:
        preset_id = self.preset_combo.currentData() or PRESETS[0].id
        return get_preset(preset_id)

    def _on_preset_changed(self, _index: int) -> None:
        preset = self._current_preset()
        self.preset_desc_label.setText(self._t(f"preset_{preset.id}_desc"))

        # Sync font family, size, outline, margin
        font_idx = self.font_family_combo.findText(
            preset.font_name, Qt.MatchFlag.MatchFixedString
        )
        if font_idx >= 0:
            self.font_family_combo.setCurrentIndex(font_idx)

        self.font_size_spin.setValue(preset.default_font_size)
        self.outline_width_spin.setValue(preset.outline)

        target_margin = preset.default_margin_v
        if self._video_info is not None and not self._video_info.is_vertical:
            target_margin = min(target_margin, max(40, self._video_info.height // 8))
        self.margin_v_slider.setValue(
            min(self.margin_v_slider.maximum(), max(self.margin_v_slider.minimum(), target_margin))
        )

        # Sync color swatches, background box checkbox, and opacity slider
        self._primary_text_color = preset.primary_text_hex.upper()
        self._highlight_color = preset.highlight_hex.upper()
        self._outline_color = preset.outline_hex.upper()
        self._bg_box_color = preset.bg_box_hex.upper()
        self._sync_color_swatches()

        self.bg_box_checkbox.setChecked(preset.bg_box_enabled)
        self.bg_opacity_slider.setValue(preset.bg_box_opacity)
        self._on_bg_box_toggled(preset.bg_box_enabled)

    def _apply_row_confidence_style(
        self,
        row: int,
        words: list[dict],
        min_confidence: float,
        reviewed: bool = False,
    ) -> None:
        low_words = [
            w
            for w in words
            if float(w.get("confidence", 1.0)) < _CONFIDENCE_MODERATE_THRESHOLD
        ]
        effective_min = min(
            (float(w.get("confidence", 1.0)) for w in words),
            default=min_confidence,
        )
        effective_min = min(effective_min, float(min_confidence))

        text_item = self.cue_table.item(row, 2)
        if not reviewed and (
            effective_min < _CONFIDENCE_MODERATE_THRESHOLD or low_words
        ):
            tint_hex = (
                _LOW_TINT_HEX
                if effective_min < _CONFIDENCE_LOW_THRESHOLD
                else _MODERATE_TINT_HEX
            )
            brush = QBrush(QColor(tint_hex))
            for col in range(3):
                cell = self.cue_table.item(row, col)
                if cell is not None:
                    cell.setBackground(brush)

            if text_item is not None:
                if low_words:
                    parts = [
                        f"'{w.get('word', '')}' ({int(round(float(w.get('confidence', 0.0)) * 100))}%)"
                        for w in low_words
                    ]
                    text_item.setToolTip(
                        self._t("tooltip_typo_words", words=", ".join(parts))
                    )
                else:
                    pct = int(round(effective_min * 100))
                    text_item.setToolTip(self._t("tooltip_typo_conf", pct=pct))
        else:
            for col in range(3):
                cell = self.cue_table.item(row, col)
                if cell is not None:
                    cell.setData(Qt.ItemDataRole.BackgroundRole, None)
            if text_item is not None:
                text_item.setToolTip("")

    def _refresh_table_tooltips(self) -> None:
        self._updating_table = True
        try:
            for row in range(self.cue_table.rowCount()):
                text_item = self.cue_table.item(row, 2)
                if text_item is None:
                    continue
                raw_meta = text_item.data(Qt.ItemDataRole.UserRole)
                meta = raw_meta if isinstance(raw_meta, dict) else {}
                words = meta.get("words") if isinstance(meta.get("words"), list) else []
                min_conf = float(meta.get("min_confidence", 1.0))
                reviewed = bool(meta.get("reviewed", False))
                self._apply_row_confidence_style(row, words, min_conf, reviewed=reviewed)
        finally:
            self._updating_table = False

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_table or item.column() != 2:
            return
        row = item.row()
        raw_meta = item.data(Qt.ItemDataRole.UserRole)
        meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        meta["reviewed"] = True
        words = meta.get("words") if isinstance(meta.get("words"), list) else []
        min_conf = float(meta.get("min_confidence", 1.0))

        self._updating_table = True
        try:
            item.setData(Qt.ItemDataRole.UserRole, meta)
            self._apply_row_confidence_style(row, words, min_conf, reviewed=True)
        finally:
            self._updating_table = False

    def _populate_cues_table(self, cues: list[dict]) -> None:
        self._updating_table = True
        try:
            self.cue_table.setRowCount(0)
            for cue in cues:
                words = cue.get("words")
                self._append_cue_row(
                    float(cue["start"]),
                    float(cue["end"]),
                    str(cue["text"]),
                    words=words if isinstance(words, list) else [],
                    min_confidence=float(cue.get("min_confidence", 1.0)),
                )
        finally:
            self._updating_table = False
        self._update_cue_count()
        self._update_action_states()

    def _append_cue_row(
        self,
        start: float,
        end: float,
        text: str,
        row_idx: int | None = None,
        words: list[dict] | None = None,
        min_confidence: float = 1.0,
    ) -> int:
        if row_idx is None:
            row_idx = self.cue_table.rowCount()
        self.cue_table.insertRow(row_idx)

        start_item = QTableWidgetItem(format_timestamp(start))
        end_item = QTableWidgetItem(format_timestamp(end))
        text_item = QTableWidgetItem(text)

        start_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        end_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        words_list = list(words) if words else []
        text_item.setData(
            Qt.ItemDataRole.UserRole,
            {
                "words": words_list,
                "min_confidence": float(min_confidence),
                "reviewed": False,
            },
        )

        self.cue_table.setItem(row_idx, 0, start_item)
        self.cue_table.setItem(row_idx, 1, end_item)
        self.cue_table.setItem(row_idx, 2, text_item)
        self._apply_row_confidence_style(
            row_idx, words_list, float(min_confidence), reviewed=False
        )
        return row_idx

    def _update_cue_count(self) -> None:
        self.cue_count_label.setText(self._t("cue_count", count=self.cue_table.rowCount()))

    def _on_add_row(self) -> None:
        selected_rows = sorted({idx.row() for idx in self.cue_table.selectedIndexes()})
        insert_at = (selected_rows[-1] + 1) if selected_rows else self.cue_table.rowCount()

        prev_end = 0.0
        if insert_at > 0:
            prev_item = self.cue_table.item(insert_at - 1, 1)
            if prev_item is not None:
                try:
                    prev_end = parse_timestamp(prev_item.text())
                except ValueError:
                    prev_end = 0.0

        new_start = prev_end
        new_end = new_start + 2.0
        if self._video_info is not None and self._video_info.duration_seconds > new_start + 0.2:
            new_end = min(new_end, self._video_info.duration_seconds)

        self._updating_table = True
        try:
            new_row = self._append_cue_row(new_start, new_end, "", row_idx=insert_at)
        finally:
            self._updating_table = False
        self._update_cue_count()
        self._update_action_states()
        self.cue_table.setCurrentCell(new_row, 2)
        self.cue_table.editItem(self.cue_table.item(new_row, 2))

    def _on_remove_row(self) -> None:
        selected_rows = sorted(
            {idx.row() for idx in self.cue_table.selectedIndexes()},
            reverse=True,
        )
        for row in selected_rows:
            self.cue_table.removeRow(row)
        self._update_cue_count()
        self._update_action_states()

    def _collect_cues_from_table(self) -> list[dict]:
        cues: list[dict] = []
        for row in range(self.cue_table.rowCount()):
            start_item = self.cue_table.item(row, 0)
            end_item = self.cue_table.item(row, 1)
            text_item = self.cue_table.item(row, 2)

            text = (text_item.text() if text_item else "").strip()
            if not text:
                continue

            try:
                start_sec = parse_timestamp(start_item.text() if start_item else "")
                end_sec = parse_timestamp(end_item.text() if end_item else "")
            except ValueError as exc:
                raise ValueError(
                    self._t("err_row_prefix", row=row + 1, error=str(exc))
                ) from exc

            if end_sec <= start_sec:
                raise ValueError(self._t("err_row_end_before_start", row=row + 1))

            raw_meta = text_item.data(Qt.ItemDataRole.UserRole) if text_item else None
            meta = raw_meta if isinstance(raw_meta, dict) else {}
            words_meta = meta.get("words") if isinstance(meta.get("words"), list) else []
            min_conf = float(meta.get("min_confidence", 1.0))

            cues.append(
                {
                    "start": start_sec,
                    "end": end_sec,
                    "text": text,
                    "min_confidence": min_conf,
                    "words": words_meta,
                }
            )

        if not cues:
            raise ValueError(self._t("err_empty_cues"))
        return cues

    def _set_busy(self, busy: bool, indeterminate: bool = False) -> None:
        self._is_busy = busy
        self.drop_zone.setEnabled(not busy)
        self.browse_video_btn.setEnabled(not busy)
        self.lang_combo.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.cue_table.setEnabled(not busy)
        self.add_row_btn.setEnabled(not busy)
        self.preset_combo.setEnabled(not busy)
        self.font_family_combo.setEnabled(not busy)
        self.font_size_spin.setEnabled(not busy)
        self.outline_width_spin.setEnabled(not busy)
        self.margin_v_slider.setEnabled(not busy)
        self.primary_color_btn.setEnabled(not busy)
        self.highlight_color_btn.setEnabled(not busy)
        self.bg_box_checkbox.setEnabled(not busy)
        self._on_bg_box_toggled(self.bg_box_checkbox.isChecked())
        self.output_path_edit.setEnabled(not busy)
        self.browse_output_btn.setEnabled(not busy)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(busy)

        if busy and indeterminate:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)

        self._update_action_states()

    def _update_action_states(self) -> None:
        has_video = self._video_info is not None
        has_cues = self.cue_table.rowCount() > 0
        has_selection = bool(self.cue_table.selectedIndexes())
        updating = (
            self._update_check_worker is not None
            and self._update_check_worker.isRunning()
        ) or (
            self._update_install_worker is not None
            and self._update_install_worker.isRunning()
        )

        self.transcribe_btn.setEnabled((not self._is_busy) and has_video)
        self.export_btn.setEnabled((not self._is_busy) and has_video and has_cues)
        self.remove_row_btn.setEnabled((not self._is_busy) and has_selection)
        self.check_update_btn.setEnabled((not self._is_busy) and (not updating))

    def _on_start_transcribe(self) -> None:
        if self._video_info is None or self._is_busy:
            return

        language = str(self.lang_combo.currentData() or "auto")
        model_name = str(self.model_combo.currentData() or "base")

        self._set_busy(True, indeterminate=True)
        self._set_status_key("status_transcribing", model=model_name)

        worker = TranscribeWorker(
            video_path=self._video_info.path,
            language=language,
            model_name=model_name,
            device=self._hardware_profile.opencaption_device,
            parent=self,
        )
        worker.status_changed.connect(self._set_raw_status)
        worker.finished_success.connect(self._on_transcribe_finished)
        worker.error_occurred.connect(self._on_transcribe_error)
        worker.finished.connect(worker.deleteLater)
        self._transcribe_worker = worker
        worker.start()

    def _on_transcribe_finished(self, cues: list) -> None:
        self._transcribe_worker = None
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self._populate_cues_table(cues)

        if cues:
            flagged = sum(
                1
                for cue in cues
                if float(cue.get("min_confidence", 1.0)) < _CONFIDENCE_MODERATE_THRESHOLD
            )
            if flagged > 0:
                self._set_status_key(
                    "status_transcribe_done_flagged", count=len(cues), flagged=flagged
                )
            else:
                self._set_status_key("status_transcribe_done", count=len(cues))
        else:
            self._set_status_key("status_transcribe_empty")

    def _on_transcribe_error(self, message: str) -> None:
        self._transcribe_worker = None
        self._set_busy(False)
        self.progress_bar.setValue(0)
        self._set_status_key("status_transcribe_failed")
        QMessageBox.warning(self, self._t("dlg_transcribe_error_title"), message)

    def _on_start_export(self) -> None:
        if self._video_info is None or self._is_busy:
            return

        try:
            cues = self._collect_cues_from_table()
        except ValueError as exc:
            QMessageBox.warning(self, self._t("dlg_check_subtitle_title"), str(exc))
            return

        output_path = self.output_path_edit.text().strip()
        if not output_path:
            src = Path(self._video_info.path)
            output_path = str(src.with_name(f"{src.stem}_hardsub.mp4"))
            self.output_path_edit.setText(output_path)

        if Path(output_path).resolve() == Path(self._video_info.path).resolve():
            QMessageBox.warning(
                self,
                self._t("dlg_invalid_output_title"),
                self._t("dlg_invalid_output_msg"),
            )
            return

        preset = self._current_preset()
        ass_config = self._build_ass_config()

        self._set_busy(True, indeterminate=False)
        self.progress_bar.setValue(0)
        self._set_status_key("status_export_starting")

        worker = RenderWorker(
            video_info=self._video_info,
            cues=cues,
            preset=preset,
            output_path=output_path,
            use_gpu=self._hardware_profile.use_gpu,
            encoder_name=self._hardware_profile.encoder_name,
            font_size=ass_config.font_size,
            margin_v=ass_config.margin_v,
            ass_config=ass_config,
            parent=self,
        )
        worker.progress_changed.connect(self.progress_bar.setValue)
        worker.status_changed.connect(self._set_raw_status)
        worker.finished_success.connect(self._on_render_finished)
        worker.error_occurred.connect(self._on_render_error)
        worker.finished.connect(worker.deleteLater)
        self._render_worker = worker
        worker.start()

    def _on_render_finished(self, output_path: str) -> None:
        self._render_worker = None
        self._set_busy(False)
        self.progress_bar.setValue(100)
        norm_output = os.path.normpath(str(output_path))
        self._set_status_key("status_export_done", filename=Path(norm_output).name)

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(self._t("dlg_export_success_title"))
        dialog.setText(self._t("dlg_export_success_text"))
        dialog.setInformativeText(self._t("dlg_export_success_info", path=norm_output))
        open_folder_btn = dialog.addButton(
            self._t("btn_open_folder"), QMessageBox.ButtonRole.AcceptRole
        )
        dialog.addButton(self._t("btn_close"), QMessageBox.ButtonRole.RejectRole)
        dialog.exec()

        if dialog.clickedButton() is open_folder_btn:
            self._open_output_folder(norm_output)

    def _on_render_error(self, message: str) -> None:
        self._render_worker = None
        self._set_busy(False)
        self.progress_bar.setValue(0)
        self._set_status_key("status_export_failed")
        QMessageBox.warning(self, self._t("dlg_export_error_title"), message)

    def _on_cancel_worker(self) -> None:
        if self._transcribe_worker is not None:
            self._set_status_key("status_cancel_transcribe")
            self.cancel_btn.setEnabled(False)
            self._transcribe_worker.cancel()
        elif self._render_worker is not None:
            self._set_status_key("status_cancel_render")
            self.cancel_btn.setEnabled(False)
            self._render_worker.cancel()

    def _open_output_folder(self, output_path: str) -> None:
        norm_path = os.path.normpath(str(output_path))
        target = Path(norm_path)
        if sys.platform == "win32" and target.exists():
            subprocess.Popen(["explorer", "/select,", norm_path])
            return
        parent_dir = target.parent.resolve() if target.parent.exists() else Path.home().resolve()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent_dir)))

    def _refresh_update_button_label(self) -> None:
        checking = (
            self._update_check_worker is not None
            and self._update_check_worker.isRunning()
            and not self._update_check_worker.is_silent
        )
        key = "btn_checking_update" if checking else "btn_check_update"
        self.check_update_btn.setText(self._t(key))

    def _start_silent_update_check(self) -> None:
        self._start_update_check(silent=True)

    def _on_check_update_clicked(self) -> None:
        self._start_update_check(silent=False)

    def _start_update_check(self, *, silent: bool) -> None:
        if (
            self._update_check_worker is not None
            and self._update_check_worker.isRunning()
        ):
            return
        if (
            self._update_install_worker is not None
            and self._update_install_worker.isRunning()
        ):
            return

        worker = UpdateCheckWorker(silent=silent, timeout=5.0, parent=self)
        worker.update_available.connect(self._on_update_available)
        worker.up_to_date.connect(self._on_update_up_to_date)
        worker.check_failed.connect(self._on_update_check_failed)
        worker.finished.connect(self._on_update_check_finished)
        worker.finished.connect(worker.deleteLater)
        self._update_check_worker = worker
        self._refresh_update_button_label()
        self._update_action_states()
        worker.start()

    def _on_update_check_finished(self) -> None:
        self._update_check_worker = None
        self._refresh_update_button_label()
        self._update_action_states()

    def _on_update_available(self, remote_info: dict) -> None:
        new_version = str(remote_info.get("version", ""))
        codename = str(remote_info.get("codename", ""))
        local_version = str(
            remote_info.get("local_version", self._version_info.get("version", "1.0.0"))
        )
        changelog = str(remote_info.get("changelog", "")).strip() or self._t(
            "update_no_changelog"
        )

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setWindowTitle(self._t("update_dlg_available_title"))
        dialog.setText(
            self._t(
                "update_dlg_available_text",
                version=new_version,
                codename=codename,
            )
        )
        dialog.setInformativeText(
            self._t(
                "update_dlg_available_info",
                local_version=local_version,
                changelog=changelog,
            )
        )
        update_now_btn = dialog.addButton(
            self._t("btn_update_now"), QMessageBox.ButtonRole.AcceptRole
        )
        dialog.addButton(self._t("btn_update_later"), QMessageBox.ButtonRole.RejectRole)
        dialog.exec()

        if dialog.clickedButton() is update_now_btn:
            if self._is_busy:
                QMessageBox.information(
                    self,
                    self._t("update_dlg_available_title"),
                    self._t("update_dlg_busy_msg"),
                )
                return
            self._start_update_install(remote_info)

    def _on_update_up_to_date(self, remote_info: dict) -> None:
        if remote_info.get("silent"):
            return
        local_version = self._version_info.get("version", "1.0.0")
        codename = self._version_info.get("codename", "")
        QMessageBox.information(
            self,
            self._t("update_dlg_uptodate_title"),
            self._t(
                "update_dlg_uptodate_msg",
                version=local_version,
                codename=codename,
            ),
        )

    def _on_update_check_failed(self, error_msg: str) -> None:
        worker = self._update_check_worker
        if worker is not None and worker.is_silent:
            return
        QMessageBox.warning(
            self,
            self._t("update_dlg_check_error_title"),
            self._t("update_dlg_check_error_msg", error=error_msg),
        )

    def _start_update_install(self, remote_info: dict) -> None:
        if (
            self._update_install_worker is not None
            and self._update_install_worker.isRunning()
        ):
            return

        progress_dlg = QProgressDialog(
            self._t("update_status_backup"),
            None,
            0,
            100,
            self,
        )
        progress_dlg.setWindowTitle(self._t("update_progress_title"))
        progress_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.setMinimumWidth(400)
        progress_dlg.setAutoClose(False)
        progress_dlg.setAutoReset(False)
        progress_dlg.setValue(0)
        progress_dlg.show()
        self._update_progress_dialog = progress_dlg

        worker = UpdateInstallWorker(remote_info, lang=self._lang, parent=self)
        worker.progress_changed.connect(progress_dlg.setValue)
        worker.status_changed.connect(progress_dlg.setLabelText)
        worker.install_finished.connect(self._on_update_install_finished)
        worker.install_failed.connect(self._on_update_install_failed)
        worker.finished.connect(worker.deleteLater)
        self._update_install_worker = worker
        self._update_action_states()
        worker.start()

    def _close_update_progress_dialog(self) -> None:
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.close()
            self._update_progress_dialog.deleteLater()
            self._update_progress_dialog = None

    def _on_update_install_finished(self, remote_info: dict) -> None:
        self._update_install_worker = None
        self._close_update_progress_dialog()
        self._update_action_states()

        new_version = str(remote_info.get("version", ""))
        codename = str(remote_info.get("codename", ""))
        QMessageBox.information(
            self,
            self._t("update_dlg_success_title"),
            self._t(
                "update_dlg_success_msg",
                version=new_version,
                codename=codename,
            ),
        )
        try:
            restart_application()
        finally:
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def _on_update_install_failed(self, error_msg: str) -> None:
        self._update_install_worker = None
        self._close_update_progress_dialog()
        self._update_action_states()
        QMessageBox.warning(
            self,
            self._t("update_dlg_failed_title"),
            self._t("update_dlg_failed_msg", error=error_msg),
        )

    def closeEvent(self, event) -> None:
        if (
            self._update_install_worker is not None
            and self._update_install_worker.isRunning()
        ):
            event.ignore()
            return
        if (
            self._update_check_worker is not None
            and self._update_check_worker.isRunning()
        ):
            self._update_check_worker.wait(1000)

        active_worker = self._transcribe_worker or self._render_worker
        if active_worker is not None and active_worker.isRunning():
            reply = QMessageBox.question(
                self,
                self._t("dlg_busy_close_title"),
                self._t("dlg_busy_close_msg"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            active_worker.cancel()
            active_worker.wait(3000)
        super().closeEvent(event)
