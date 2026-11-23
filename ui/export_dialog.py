"""Centered modal animated export progress dialog for AutoHardsub."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.i18n import tr


def _resolve_encoder_badge(encoder_name: str) -> tuple[str, bool]:
    """Return a concise encoder badge label (NVENC/QSV/AMF/MF/CPU) and GPU flag."""
    enc = (encoder_name or "").strip().lower()
    if "nvenc" in enc:
        return "GPU • NVENC", True
    if "qsv" in enc:
        return "GPU • QSV", True
    if "amf" in enc:
        return "GPU • AMF", True
    if "mf" in enc:
        return "GPU • MF", True
    return "CPU • libx264", False


class ExportProgressDialog(QDialog):
    """Modal centered dialog with smooth animated progress bar and GPU encoder status."""

    cancel_requested = Signal()

    def __init__(
        self,
        encoder_name: str,
        output_filename: str,
        lang: str = "en",
        parent: QWidget | None = None,
        output_path: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._lang = lang
        self._encoder_name = encoder_name
        self._output_path = os.path.normpath(output_path) if output_path else ""
        self._output_filename = output_filename or (
            Path(self._output_path).name if self._output_path else ""
        )
        self._is_finished = False
        self._is_cancelling = False
        self._is_indeterminate = True
        self._shimmer_phase = 0.0

        self.setWindowTitle(tr(self._lang, "export_dlg_title"))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        self.setFixedWidth(500)

        self._build_ui()

        # Smooth value transition animation
        self._progress_anim = QPropertyAnimation(self._progress_bar, b"value", self)
        self._progress_anim.setDuration(220)
        self._progress_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Animated shimmer gradient timer for sleek live progress chunk
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(45)
        self._shimmer_timer.timeout.connect(self._advance_shimmer)

        self.set_indeterminate(True)
        self._shimmer_timer.start()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: #0f172a;
                border: 1px solid #334155;
            }
            QFrame#ExportCard {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 10px;
            }
            """
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("ExportCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Header: Title + Encoder Pill Badge
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        self._title_label = QLabel(tr(self._lang, "export_dlg_heading"))
        self._title_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f8fafc; background: transparent;"
        )

        badge_text, is_gpu = _resolve_encoder_badge(self._encoder_name)
        self._encoder_badge = QLabel(badge_text)
        if is_gpu:
            self._encoder_badge.setStyleSheet(
                "background-color: #064e3b; color: #6ee7b7; border: 1px solid #10b981;"
                " border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 700;"
            )
        else:
            self._encoder_badge.setStyleSheet(
                "background-color: #334155; color: #fbbf24; border: 1px solid #475569;"
                " border-radius: 10px; padding: 3px 10px; font-size: 11px; font-weight: 700;"
            )

        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._encoder_badge)
        layout.addLayout(header_row)

        # Stage status + Percentage readout
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self._stage_label = QLabel(tr(self._lang, "status_export_starting"))
        self._stage_label.setWordWrap(True)
        self._stage_label.setStyleSheet(
            "font-size: 12px; color: #cbd5e1; background: transparent;"
        )

        self._percent_label = QLabel("0%")
        self._percent_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._percent_label.setMinimumWidth(52)
        self._percent_label.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #38bdf8; background: transparent;"
        )

        status_row.addWidget(self._stage_label, stretch=1)
        status_row.addWidget(self._percent_label)
        layout.addLayout(status_row)

        # Animated Progress Bar
        self._progress_bar = QProgressBar(card)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setTextVisible(False)
        self._apply_shimmer_qss(0.0)
        layout.addWidget(self._progress_bar)

        # Footer: Output filename + Cancel button (while exporting)
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)

        self._file_label = QLabel(self._output_filename)
        self._file_label.setStyleSheet(
            "font-size: 11px; color: #94a3b8; background: transparent;"
        )
        self._file_label.setToolTip(self._output_path or self._output_filename)

        self._cancel_btn = QPushButton(tr(self._lang, "btn_cancel"))
        self._cancel_btn.setObjectName("DangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setFixedHeight(34)
        self._cancel_btn.setMinimumWidth(96)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)

        footer_row.addWidget(self._file_label, stretch=1)
        footer_row.addWidget(self._cancel_btn)
        layout.addLayout(footer_row)

        # Completion action row (hidden until export succeeds)
        self._completion_actions = QWidget(card)
        self._completion_actions.setStyleSheet("background: transparent;")
        actions_row = QHBoxLayout(self._completion_actions)
        actions_row.setContentsMargins(0, 4, 0, 0)
        actions_row.setSpacing(8)

        self._open_file_btn = QPushButton(tr(self._lang, "btn_open_file"))
        self._open_file_btn.setObjectName("PrimaryButton")
        self._open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_file_btn.setFixedHeight(36)
        self._open_file_btn.setStyleSheet(
            "QPushButton {"
            " background-color: #10b981; color: #052e16;"
            " border: 1px solid #34d399; border-radius: 7px;"
            " padding: 0 14px; font-size: 12px; font-weight: 700;"
            "}"
            "QPushButton:hover { background-color: #34d399; }"
            "QPushButton:pressed { background-color: #059669; color: #ecfdf5; }"
        )
        self._open_file_btn.clicked.connect(self._on_open_file_clicked)

        self._open_folder_btn = QPushButton(tr(self._lang, "btn_open_folder_short"))
        self._open_folder_btn.setObjectName("SecondaryButton")
        self._open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_folder_btn.setFixedHeight(36)
        self._open_folder_btn.setStyleSheet(
            "QPushButton {"
            " background-color: #1e293b; color: #e2e8f0;"
            " border: 1px solid #475569; border-radius: 7px;"
            " padding: 0 12px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #334155; border-color: #64748b; }"
        )
        self._open_folder_btn.clicked.connect(self._on_open_folder_clicked)

        self._close_btn = QPushButton(tr(self._lang, "btn_close"))
        self._close_btn.setObjectName("SecondaryButton")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setFixedHeight(36)
        self._close_btn.setMinimumWidth(82)
        self._close_btn.setStyleSheet(
            "QPushButton {"
            " background-color: #0f172a; color: #cbd5e1;"
            " border: 1px solid #334155; border-radius: 7px;"
            " padding: 0 12px; font-size: 12px; font-weight: 600;"
            "}"
            "QPushButton:hover { background-color: #1e293b; color: #f8fafc; }"
        )
        self._close_btn.clicked.connect(self.accept)

        actions_row.addWidget(self._open_file_btn, stretch=2)
        actions_row.addWidget(self._open_folder_btn, stretch=2)
        actions_row.addWidget(self._close_btn, stretch=1)

        self._completion_actions.setVisible(False)
        layout.addWidget(self._completion_actions)

        outer.addWidget(card)

    def _apply_shimmer_qss(self, phase: float, *, completed: bool = False) -> None:
        if completed:
            chunk_bg = (
                "qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                " stop:0 #059669, stop:0.5 #10b981, stop:1 #34d399)"
            )
        else:
            # Smooth moving highlight band across the progress chunk
            s0 = max(0.0, min(0.96, phase - 0.18))
            s1 = max(s0 + 0.01, min(0.98, phase))
            s2 = max(s1 + 0.01, min(1.0, phase + 0.18))
            chunk_bg = (
                f"qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                f" stop:0 #1d4ed8,"
                f" stop:{s0:.3f} #2563eb,"
                f" stop:{s1:.3f} #38bdf8,"
                f" stop:{s2:.3f} #2563eb,"
                f" stop:1 #1d4ed8)"
            )

        self._progress_bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
            }}
            QProgressBar::chunk {{
                background: {chunk_bg};
                border-radius: 7px;
            }}
            """
        )

    def _advance_shimmer(self) -> None:
        self._shimmer_phase += 0.035
        if self._shimmer_phase > 1.18:
            self._shimmer_phase = -0.18
        self._apply_shimmer_qss(max(0.0, min(1.0, self._shimmer_phase)))

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            self.move(parent.frameGeometry().center() - self.rect().center())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._center_on_parent()

    def set_indeterminate(self, active: bool) -> None:
        """Toggle indeterminate pulse mode for pre-processing stages."""
        self._is_indeterminate = bool(active)
        if self._is_indeterminate:
            self._progress_anim.stop()
            self._progress_bar.setRange(0, 0)
            self._percent_label.setText("...")
        else:
            if self._progress_bar.maximum() == 0:
                self._progress_bar.setRange(0, 100)
                self._progress_bar.setValue(0)
            self._percent_label.setText(f"{self._progress_bar.value()}%")

    def set_progress(self, value: int) -> None:
        """Smoothly animate the progress bar to the target percentage (0–100)."""
        clamped = max(0, min(100, int(value)))
        if self._is_indeterminate:
            if clamped == 0:
                return
            self.set_indeterminate(False)

        self._percent_label.setText(f"{clamped}%")

        current_val = self._progress_bar.value()
        if clamped == current_val:
            return

        self._progress_anim.stop()
        self._progress_anim.setStartValue(current_val)
        self._progress_anim.setEndValue(clamped)
        self._progress_anim.start()

    def set_status_text(self, text: str) -> None:
        """Update the active stage/status description."""
        if text:
            self._stage_label.setText(text)

    def mark_completed(self, output_path: str | None = None) -> None:
        """Transition into the completed state with Open File, Open Folder, and Close actions."""
        self._is_finished = True
        self._shimmer_timer.stop()

        if output_path:
            self._output_path = os.path.normpath(str(output_path))
            self._output_filename = Path(self._output_path).name
            self._file_label.setText(self._output_filename)
            self._file_label.setToolTip(self._output_path)

        if self._is_indeterminate:
            self.set_indeterminate(False)

        self._progress_anim.stop()
        self._progress_anim.setStartValue(self._progress_bar.value())
        self._progress_anim.setEndValue(100)
        self._progress_anim.start()

        self._title_label.setText(tr(self._lang, "export_dlg_done_heading"))
        self._title_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #34d399; background: transparent;"
        )
        self._percent_label.setText("100%")
        self._percent_label.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #34d399; background: transparent;"
        )
        self._stage_label.setText(tr(self._lang, "export_dlg_done"))
        self._apply_shimmer_qss(1.0, completed=True)

        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setVisible(False)
        self._completion_actions.setVisible(True)
        self._open_file_btn.setDefault(True)
        self._open_file_btn.setFocus()
        self._center_on_parent()

    def _on_open_file_clicked(self) -> None:
        target = self._output_path
        if target:
            norm_path = os.path.normpath(target)
            launched = False
            if sys.platform == "win32" and hasattr(os, "startfile"):
                try:
                    os.startfile(norm_path)
                    launched = True
                except OSError:
                    launched = False
            if not launched:
                QDesktopServices.openUrl(QUrl.fromLocalFile(norm_path))
        self.accept()

    def _on_open_folder_clicked(self) -> None:
        target = self._output_path
        if not target:
            return
        norm_path = os.path.normpath(target)
        path_obj = Path(norm_path)
        if sys.platform == "win32" and path_obj.exists():
            subprocess.Popen(["explorer", "/select,", norm_path])
            return
        parent_dir = (
            path_obj.parent.resolve()
            if path_obj.parent.exists()
            else Path.home().resolve()
        )
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(parent_dir)))

    def mark_failed(self) -> None:
        """Stop animations and close immediately on error or cancellation."""
        self._is_finished = True
        self._shimmer_timer.stop()
        self._progress_anim.stop()
        self.reject()

    def _on_cancel_clicked(self) -> None:
        if self._is_finished or self._is_cancelling:
            return
        self._is_cancelling = True
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText(tr(self._lang, "export_dlg_cancelling"))
        self._stage_label.setText(tr(self._lang, "status_cancel_render"))
        self.cancel_requested.emit()

    def reject(self) -> None:
        if self._is_finished:
            super().reject()
        else:
            self._on_cancel_clicked()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_finished:
            self._shimmer_timer.stop()
            self._progress_anim.stop()
            event.accept()
        else:
            self._on_cancel_clicked()
            event.ignore()
