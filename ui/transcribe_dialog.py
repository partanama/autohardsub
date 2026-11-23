"""Centered modal animated transcription progress dialog for AutoHardsub."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
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


def _format_elapsed(total_seconds: int) -> str:
    """Format elapsed seconds as MM:SS (or HH:MM:SS if >= 1 hour)."""
    secs = max(0, int(total_seconds))
    hours, rem = divmod(secs, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _format_model_badge(model_name: str) -> str:
    """Return a clean human-readable Whisper model pill label."""
    cleaned = (model_name or "base").strip()
    if cleaned.lower().endswith(".bin"):
        cleaned = cleaned[:-4]
    if cleaned.lower().startswith("ggml-"):
        cleaned = cleaned[5:]
    return f"Whisper • {cleaned}" if cleaned else "Whisper • base"


class TranscribeProgressDialog(QDialog):
    """Modal centered dialog with animated progress bar, stage status, and elapsed timer."""

    cancel_requested = Signal()

    def __init__(
        self,
        model_name: str,
        vulkan_available: bool = False,
        lang: str = "en",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._lang = lang
        self._model_name = model_name or "base"
        self._vulkan_available = bool(vulkan_available)
        self._is_finished = False
        self._is_cancelling = False
        self._is_indeterminate = True
        self._shimmer_phase = 0.0
        self._elapsed_seconds = 0
        self._target_progress = 0

        self.setWindowTitle(tr(self._lang, "transcribe_dlg_title"))
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

        # Animated shimmer gradient timer for sleek live progress bar
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(45)
        self._shimmer_timer.timeout.connect(self._advance_shimmer)

        # Live elapsed time counter (updates every second)
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self.set_indeterminate(True)
        self._shimmer_timer.start()
        self._elapsed_timer.start()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background-color: #0f172a;
                border: 1px solid #334155;
            }
            QFrame#TranscribeCard {
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
        card.setObjectName("TranscribeCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Header: Title + Model Badge + Backend Badge
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self._title_label = QLabel(tr(self._lang, "transcribe_dlg_heading"))
        self._title_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #f8fafc; background: transparent;"
        )

        self._model_badge = QLabel(_format_model_badge(self._model_name))
        self._model_badge.setStyleSheet(
            "background-color: #1e3a5f; color: #7dd3fc; border: 1px solid #0284c7;"
            " border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
        )

        backend_text = tr(
            self._lang,
            "transcribe_badge_vulkan" if self._vulkan_available else "transcribe_badge_cpu",
        )
        self._backend_badge = QLabel(backend_text)
        if self._vulkan_available:
            self._backend_badge.setStyleSheet(
                "background-color: #064e3b; color: #6ee7b7; border: 1px solid #10b981;"
                " border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
            )
        else:
            self._backend_badge.setStyleSheet(
                "background-color: #334155; color: #fbbf24; border: 1px solid #475569;"
                " border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 700;"
            )

        header_row.addWidget(self._title_label)
        header_row.addStretch(1)
        header_row.addWidget(self._model_badge)
        header_row.addWidget(self._backend_badge)
        layout.addLayout(header_row)

        # Stage status + Percentage readout
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self._stage_label = QLabel(tr(self._lang, "transcribe_stage_init"))
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

        # Footer: Live elapsed timer + Cancel button
        footer_row = QHBoxLayout()
        footer_row.setSpacing(10)

        self._elapsed_label = QLabel(
            tr(self._lang, "transcribe_dlg_elapsed", elapsed=_format_elapsed(0))
        )
        self._elapsed_label.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #94a3b8; background: transparent;"
        )

        self._cancel_btn = QPushButton(tr(self._lang, "btn_cancel"))
        self._cancel_btn.setObjectName("DangerButton")
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setFixedHeight(34)
        self._cancel_btn.setMinimumWidth(96)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)

        footer_row.addWidget(self._elapsed_label, stretch=1)
        footer_row.addWidget(self._cancel_btn)
        layout.addLayout(footer_row)

        outer.addWidget(card)

    def _apply_shimmer_qss(self, phase: float, *, completed: bool = False) -> None:
        if completed:
            chunk_bg = (
                "qlineargradient(x1:0, y1:0, x2:1, y2:0,"
                " stop:0 #059669, stop:0.5 #10b981, stop:1 #34d399)"
            )
        else:
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

    def _tick_elapsed(self) -> None:
        self._elapsed_seconds += 1
        self._elapsed_label.setText(
            tr(
                self._lang,
                "transcribe_dlg_elapsed",
                elapsed=_format_elapsed(self._elapsed_seconds),
            )
        )

    def _center_on_parent(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            self.move(parent.frameGeometry().center() - self.rect().center())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._center_on_parent()

    def set_indeterminate(self, active: bool) -> None:
        """Toggle indeterminate shimmer mode during initialization."""
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
        if self._is_finished:
            return
        clamped = max(0, min(100, int(value)))
        if clamped < self._target_progress:
            return
        self._target_progress = clamped

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
        if text and not self._is_cancelling:
            self._stage_label.setText(text)

    def update_progress(self, percent: int, stage_text: str) -> None:
        """Update both percentage progress and stage text in one slot."""
        if self._is_finished or self._is_cancelling:
            return
        if stage_text:
            self._stage_label.setText(stage_text)
        self.set_progress(percent)

    def mark_completed(self) -> None:
        """Animate smoothly to 100% and auto-close after ~250ms."""
        if self._is_finished:
            return
        self._is_finished = True
        self._shimmer_timer.stop()
        self._elapsed_timer.stop()

        if self._is_indeterminate:
            self.set_indeterminate(False)

        self._progress_anim.stop()
        self._progress_anim.setDuration(180)
        self._progress_anim.setStartValue(self._progress_bar.value())
        self._progress_anim.setEndValue(100)
        self._progress_anim.start()

        self._title_label.setText(tr(self._lang, "transcribe_dlg_done_heading"))
        self._title_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #34d399; background: transparent;"
        )
        self._percent_label.setText("100%")
        self._percent_label.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #34d399; background: transparent;"
        )
        self._stage_label.setText(tr(self._lang, "transcribe_dlg_done"))
        self._apply_shimmer_qss(1.0, completed=True)
        self._cancel_btn.setEnabled(False)

        QTimer.singleShot(250, self._finish_auto_close)

    def _finish_auto_close(self) -> None:
        if self.isVisible():
            self.accept()

    def mark_failed(self) -> None:
        """Stop all timers/animations and close immediately on error or cancellation."""
        self._is_finished = True
        self._shimmer_timer.stop()
        self._elapsed_timer.stop()
        self._progress_anim.stop()
        self.reject()

    def _on_cancel_clicked(self) -> None:
        if self._is_finished or self._is_cancelling:
            return
        self._is_cancelling = True
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText(tr(self._lang, "transcribe_dlg_cancelling"))
        self._stage_label.setText(tr(self._lang, "status_cancel_transcribe"))
        self.cancel_requested.emit()

    def reject(self) -> None:
        if self._is_finished:
            super().reject()
        else:
            self._on_cancel_clicked()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_finished:
            self._shimmer_timer.stop()
            self._elapsed_timer.stop()
            self._progress_anim.stop()
            event.accept()
        else:
            self._on_cancel_clicked()
            event.ignore()
