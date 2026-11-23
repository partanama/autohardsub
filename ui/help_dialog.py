"""Bilingual (ID/EN) scrollable Help & Quick Guide dialog for AutoHardsub."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.i18n import normalize_lang, tr
from core.paths import get_fonts_dir
from core.user_settings import get_settings_path


class HelpDialog(QDialog):
    """Scrollable bilingual guide covering presets, *keyword* tips, custom fonts, and settings."""

    def __init__(self, lang: str = "id", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lang = normalize_lang(lang)
        self.setWindowTitle(tr(self._lang, "help_dlg_title"))
        self.resize(620, 540)
        self.setMinimumSize(520, 420)
        self._build_ui()

    def _t(self, key: str, **kwargs) -> str:
        return tr(self._lang, key, **kwargs)

    def _build_section_card(self, title: str, body_html: str) -> QFrame:
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #38bdf8; background: transparent;"
        )
        title_lbl.setWordWrap(True)

        body_lbl = QLabel(body_html)
        body_lbl.setTextFormat(Qt.TextFormat.RichText)
        body_lbl.setWordWrap(True)
        body_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_lbl.setStyleSheet(
            "font-size: 12.5px; color: #e2e8f0; line-height: 1.45; background: transparent;"
        )

        card_layout.addWidget(title_lbl)
        card_layout.addWidget(body_lbl)
        return card

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        header_title = QLabel(self._t("help_header_title"))
        header_title.setStyleSheet("font-size: 17px; font-weight: 700; color: #f8fafc;")
        header_sub = QLabel(self._t("help_header_subtitle"))
        header_sub.setObjectName("MutedLabel")
        header_sub.setWordWrap(True)

        root.addWidget(header_title)
        root.addWidget(header_sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(10)

        fonts_dir_str = str(get_fonts_dir())
        settings_dir_str = str(get_settings_path().parent)

        sections = (
            (
                self._t("help_sec1_title"),
                self._t("help_sec1_body"),
            ),
            (
                self._t("help_sec2_title"),
                self._t("help_sec2_body"),
            ),
            (
                self._t("help_sec3_title"),
                self._t("help_sec3_body", fonts_dir=fonts_dir_str),
            ),
            (
                self._t("help_sec4_title"),
                self._t("help_sec4_body", settings_dir=settings_dir_str),
            ),
        )

        for sec_title, sec_body in sections:
            content_layout.addWidget(self._build_section_card(sec_title, sec_body))

        content_layout.addStretch(1)
        scroll.setWidget(container)
        root.addWidget(scroll, stretch=1)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        open_fonts_btn = QPushButton(self._t("help_btn_open_fonts"))
        open_fonts_btn.setObjectName("SecondaryButton")
        open_fonts_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_fonts_btn.clicked.connect(self._open_fonts_folder)

        close_btn = QPushButton(self._t("btn_close"))
        close_btn.setObjectName("PrimaryButton")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)

        footer.addWidget(open_fonts_btn)
        footer.addStretch(1)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _open_fonts_folder(self) -> None:
        fonts_dir = get_fonts_dir()
        try:
            fonts_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(fonts_dir.resolve())))
