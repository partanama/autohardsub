"""Application entry point and dark-slate theme setup for AutoHardsub."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

DARK_SLATE_QSS = """
QWidget {
    background-color: #0f172a;
    color: #e2e8f0;
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}

QFrame#Card {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
}

QFrame#DropZone {
    background-color: #0f172a;
    border: 2px dashed #475569;
    border-radius: 8px;
}

QFrame#DropZone[dragActive="true"] {
    background-color: #172554;
    border: 2px dashed #38bdf8;
}

QLabel#AppTitle {
    font-size: 20px;
    font-weight: 700;
    color: #f8fafc;
}

QLabel#AppSubtitle {
    font-size: 12px;
    color: #94a3b8;
}

QLabel#SectionTitle {
    font-size: 14px;
    font-weight: 600;
    color: #f1f5f9;
}

QLabel#VideoNameLabel {
    font-size: 13px;
    font-weight: 600;
    color: #f8fafc;
}

QLabel#MutedLabel {
    font-size: 12px;
    color: #94a3b8;
}

QLabel#StatusLabel {
    font-size: 12px;
    font-weight: 500;
    color: #cbd5e1;
}

QLabel#HardwareBadge {
    padding: 6px 12px;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 600;
    background-color: #334155;
    color: #fbbf24;
    border: 1px solid #475569;
}

QLabel#HardwareBadge[gpuActive="true"] {
    background-color: #064e3b;
    color: #6ee7b7;
    border: 1px solid #10b981;
}

QLabel#HardwareBadge[gpuActive="partial"] {
    background-color: #0c4a6e;
    color: #7dd3fc;
    border: 1px solid #0284c7;
}

QLabel#WarningBanner {
    background-color: #451a03;
    color: #fde68a;
    border: 1px solid #d97706;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 5px 9px;
    min-height: 20px;
}

QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {
    border: 1px solid #38bdf8;
}

QComboBox#LangSwitcher {
    min-width: 58px;
    max-width: 72px;
    font-weight: 600;
    padding: 4px 8px;
}

QComboBox QAbstractItemView {
    background-color: #1e293b;
    color: #f8fafc;
    selection-background-color: #2563eb;
    border: 1px solid #475569;
}

QCheckBox {
    spacing: 8px;
    color: #e2e8f0;
    font-weight: 500;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #64748b;
    background-color: #0f172a;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border: 1px solid #3b82f6;
}

QCheckBox:disabled {
    color: #64748b;
}

QPushButton {
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 600;
}

QPushButton:disabled {
    background-color: #334155;
    color: #64748b;
    border: 1px solid #334155;
}

QPushButton#PrimaryButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    padding: 10px 20px;
    font-size: 14px;
}

QPushButton#PrimaryButton:hover:!disabled {
    background-color: #1d4ed8;
}

QPushButton#ActionButton {
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #0ea5e9;
}

QPushButton#ActionButton:hover:!disabled {
    background-color: #0369a1;
}

QPushButton#SecondaryButton {
    background-color: #334155;
    color: #f1f5f9;
    border: 1px solid #475569;
}

QPushButton#SecondaryButton:hover:!disabled {
    background-color: #475569;
}

QPushButton#MiniButton {
    background-color: #334155;
    color: #e2e8f0;
    border: 1px solid #475569;
    padding: 5px 10px;
    font-size: 12px;
}

QPushButton#MiniButton:hover:!disabled {
    background-color: #475569;
}

QPushButton#DangerButton {
    background-color: #b91c1c;
    color: #ffffff;
    border: 1px solid #dc2626;
    padding: 10px 14px;
}

QPushButton#DangerButton:hover:!disabled {
    background-color: #991b1b;
}

QPushButton#ColorSwatchButton {
    border-radius: 6px;
    padding: 4px 10px;
    min-height: 24px;
    min-width: 78px;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 12px;
    font-weight: 700;
}

QTableWidget {
    background-color: #0f172a;
    alternate-background-color: #162033;
    color: #f8fafc;
    gridline-color: #334155;
    border: 1px solid #334155;
    border-radius: 6px;
    selection-background-color: #1d4ed8;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #1e293b;
    color: #cbd5e1;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #334155;
    border-right: 1px solid #334155;
    font-weight: 600;
}

QProgressBar {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #f8fafc;
    min-height: 18px;
    font-weight: 600;
}

QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 5px;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #0f172a;
    border: 1px solid #475569;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #38bdf8;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
"""


def main() -> int:
    """Create the Qt application, apply dark-slate theme, and launch MainWindow."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    app.setApplicationName("AutoHardsub")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_SLATE_QSS)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
