"""Real-time QPainter live visual preview widget for AutoHardsub subtitle styles."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.ass_engine import (
    AssConfig,
    _compute_font_box_metrics,
    _group_newspaper_cutout_words,
    _group_words_into_pill_blocks,
    _NEWSPAPER_TILT_DEG,
    _prepare_newspaper_cutout_words,
    _resolve_newspaper_serif_font,
    estimate_word_timings,
)
from core.presets import PRESETS, SubtitlePreset

DEFAULT_PREVIEW_SAMPLE = "Kampung *Baduy* Luar dilahap *api*"


def _draw_outlined_text(
    painter: QPainter,
    font: QFont,
    baseline_x: float,
    baseline_y: float,
    text: str,
    fill_color: QColor,
    outline_color: QColor | None,
    outline_width_px: float,
    shadow_offset_px: float,
) -> None:
    """Render crisp outlined and shadowed text using QPainterPath."""
    path = QPainterPath()
    path.addText(QPointF(baseline_x, baseline_y), font, text)

    if shadow_offset_px > 0.1:
        painter.save()
        painter.translate(shadow_offset_px, shadow_offset_px)
        painter.fillPath(path, QColor(0, 0, 0, 145))
        painter.restore()

    if outline_color is not None and outline_width_px > 0.1:
        pen = QPen(outline_color, outline_width_px * 2.0)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.strokePath(path, pen)

    painter.fillPath(path, fill_color)


class _StylePreviewCanvas(QWidget):
    """Canvas rendering a pixel-accurate scaled video frame with live styled subtitles."""

    view_changed = Signal(float, bool)

    _MIN_ZOOM: float = 0.5
    _MAX_ZOOM: float = 5.0
    _ZOOM_STEP: float = 1.15

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aspect: str = "16:9"
        self._video_res: tuple[int, int] | None = None
        self._preset: SubtitlePreset = PRESETS[0]
        self._config: AssConfig = AssConfig()
        self._sample_text: str = DEFAULT_PREVIEW_SAMPLE
        self._serif_font_name: str = _resolve_newspaper_serif_font()

        # Interactive viewport zoom & pan state
        self._zoom: float = 1.0
        self._pan: QPointF = QPointF(0.0, 0.0)
        self._dragging: bool = False
        self._last_drag_pos: QPointF = QPointF(0.0, 0.0)

        self.setMouseTracking(True)
        self.setMinimumHeight(156)
        self.setMaximumHeight(186)

    def _is_view_modified(self) -> bool:
        return (
            abs(self._zoom - 1.0) > 1e-3
            or abs(self._pan.x()) > 0.5
            or abs(self._pan.y()) > 0.5
        )

    def _update_hover_cursor(self) -> None:
        if self._dragging:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._is_view_modified():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _emit_view_changed(self) -> None:
        self.view_changed.emit(self._zoom, self._is_view_modified())

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan = QPointF(0.0, 0.0)
        self._dragging = False
        self._update_hover_cursor()
        self._emit_view_changed()
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta_y = event.angleDelta().y()
        if delta_y == 0:
            event.ignore()
            return

        factor = self._ZOOM_STEP if delta_y > 0 else (1.0 / self._ZOOM_STEP)
        old_zoom = self._zoom
        new_zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, old_zoom * factor))
        if abs(new_zoom - old_zoom) < 1e-6:
            event.accept()
            return

        # Keep the point under the mouse cursor stationary while zooming
        cursor_pos = event.position()
        scale_ratio = new_zoom / old_zoom
        self._pan = cursor_pos - ((cursor_pos - self._pan) * scale_ratio)
        self._zoom = new_zoom

        self._update_hover_cursor()
        self._emit_view_changed()
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._dragging = True
            self._last_drag_pos = event.position()
            self._update_hover_cursor()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            current_pos = event.position()
            delta = current_pos - self._last_drag_pos
            self._last_drag_pos = current_pos
            self._pan = self._pan + delta
            self._emit_view_changed()
            self.update()
            event.accept()
            return
        self._update_hover_cursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging and event.button() in (
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
        ):
            self._dragging = False
            self._update_hover_cursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:
        if not self._dragging:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)

    def set_aspect(self, aspect: str) -> None:
        normalized = "9:16" if aspect == "9:16" else "16:9"
        self._aspect = normalized
        self._video_res = None
        self.update()

    def set_video_dimensions(self, width: int, height: int) -> None:
        w = max(16, int(width))
        h = max(16, int(height))
        self._video_res = (w, h)
        self._aspect = "9:16" if h > w else "16:9"
        self.update()

    def set_sample_text(self, text: str | None) -> None:
        cleaned = (text or "").strip() or DEFAULT_PREVIEW_SAMPLE
        if self._sample_text != cleaned:
            self._sample_text = cleaned
            self.update()

    def set_style_state(self, preset: SubtitlePreset, config: AssConfig) -> None:
        self._preset = preset
        self._config = config
        self.update()

    def _compute_frame_rect(self) -> tuple[QRectF, int, int]:
        pad = 6.0
        avail_w = max(20.0, self.width() - (2.0 * pad))
        avail_h = max(20.0, self.height() - (2.0 * pad))

        if self._video_res is not None:
            res_x, res_y = self._video_res
        elif self._aspect == "9:16":
            res_x, res_y = 1080, 1920
        else:
            res_x, res_y = 1920, 1080

        ratio = res_x / float(res_y)
        if (avail_w / avail_h) > ratio:
            frame_h = avail_h
            frame_w = frame_h * ratio
        else:
            frame_w = avail_w
            frame_h = frame_w / ratio

        left = (self.width() - frame_w) / 2.0
        top = (self.height() - frame_h) / 2.0
        return QRectF(left, top, frame_w, frame_h), res_x, res_y

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        outer_rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#090f1c"))
        painter.drawRoundedRect(outer_rect, 8.0, 8.0)

        frame_rect, res_x, res_y = self._compute_frame_rect()
        canvas_rect = QRectF(
            1.0,
            1.0,
            max(1.0, self.width() - 2.0),
            max(1.0, self.height() - 2.0),
        )

        # Clip strictly to the preview canvas frame before applying viewport zoom & pan
        painter.save()
        painter.setClipRect(canvas_rect)
        painter.translate(self._pan)
        painter.scale(self._zoom, self._zoom)

        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(frame_rect, 5.0, 5.0)
        painter.setClipPath(clip_path, Qt.ClipOperation.IntersectClip)

        # Simulated dark video frame gradient
        grad = QLinearGradient(frame_rect.topLeft(), frame_rect.bottomRight())
        grad.setColorAt(0.0, QColor("#1b2a41"))
        grad.setColorAt(0.55, QColor("#121d2f"))
        grad.setColorAt(1.0, QColor("#0d1522"))
        painter.fillRect(frame_rect, grad)

        # Subtle rule-of-thirds guides for visual margin judgment
        guide_pen = QPen(QColor(255, 255, 255, 16), 1.0)
        painter.setPen(guide_pen)
        for frac in (1.0 / 3.0, 2.0 / 3.0):
            gx = frame_rect.left() + frame_rect.width() * frac
            gy = frame_rect.top() + frame_rect.height() * frac
            painter.drawLine(QPointF(gx, frame_rect.top()), QPointF(gx, frame_rect.bottom()))
            painter.drawLine(QPointF(frame_rect.left(), gy), QPointF(frame_rect.right(), gy))

        # Subtle resolution / aspect badge in top-left corner
        badge_font = QFont("Segoe UI")
        badge_font.setPixelSize(9)
        painter.setFont(badge_font)
        painter.setPen(QColor(148, 163, 184, 160))
        badge_text = (
            f"{res_x}×{res_y}"
            if self._video_res is not None
            else self._aspect
        )
        painter.drawText(
            QPointF(frame_rect.left() + 6.0, frame_rect.top() + 13.0),
            badge_text,
        )

        # Render styled subtitle preview in exact PlayRes coordinate space
        self._paint_subtitle(painter, frame_rect, res_x, res_y)
        painter.restore()

        # Crisp video frame border
        painter.setPen(QPen(QColor("#475569"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame_rect, 5.0, 5.0)
        painter.restore()

        # Outer canvas container border drawn cleanly on top
        painter.setPen(QPen(QColor("#334155"), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outer_rect, 8.0, 8.0)
        painter.end()

    def _effective_values(self) -> dict[str, object]:
        preset = self._preset
        cfg = self._config
        return {
            "mode": preset.animation_mode,
            "font_name": cfg.font_name or preset.font_name,
            "font_size": int(
                cfg.font_size if cfg.font_size is not None else preset.default_font_size
            ),
            "margin_v": int(
                cfg.margin_v if cfg.margin_v is not None else preset.default_margin_v
            ),
            "outline_width": float(
                cfg.outline_width if cfg.outline_width is not None else preset.outline
            ),
            "primary_color": QColor(cfg.primary_text_color or preset.primary_text_hex),
            "highlight_color": QColor(cfg.highlight_color or preset.highlight_hex),
            "outline_color": QColor(cfg.outline_color or preset.outline_hex),
            "enable_bg_box": bool(
                cfg.enable_bg_box
                if cfg.enable_bg_box is not None
                else preset.bg_box_enabled
            ),
            "bg_box_color": QColor(cfg.bg_box_color or preset.bg_box_hex),
            "bg_box_opacity": int(
                cfg.bg_box_opacity
                if cfg.bg_box_opacity is not None
                else preset.bg_box_opacity
            ),
            "bold": preset.bold != 0,
            "shadow": preset.shadow if preset.shadow > 0 else 2.0,
        }

    def _paint_subtitle(
        self,
        painter: QPainter,
        frame: QRectF,
        res_x: int,
        res_y: int,
    ) -> None:
        style = self._effective_values()
        mode = str(style["mode"])

        # Mirror core/ass_engine.py coordinate math 1:1 by painting in virtual
        # PlayResX x PlayResY coordinates and scaling smoothly onto the preview canvas.
        # On screen:
        #   - vertical margin = margin_v * (preview_h / 1080.0)
        #   - font pixel size = font_size * min(preview_w, preview_h) / 1080.0
        #   - block_bottom_y  = preview_h - scaled_margin_y (matching libass \an2 / MarginV)
        base_scale = min(float(res_x), float(res_y)) / 1080.0
        font_px = max(12, int(round(float(style["font_size"]) * base_scale)))
        scaled_margin_v = max(0.0, float(style["margin_v"])) * (float(res_y) / 1080.0)

        font = QFont(str(style["font_name"]))
        font.setPixelSize(font_px)
        font.setBold(bool(style["bold"]))
        metrics = QFontMetricsF(font)

        sx = frame.width() / float(res_x)
        sy = frame.height() / float(res_y)

        painter.save()
        painter.translate(frame.left(), frame.top())
        painter.scale(sx, sy)

        try:
            if mode == "newspaper_cutout":
                self._paint_newspaper_cutout(
                    painter, res_x, res_y, font, metrics, font_px, base_scale, scaled_margin_v, style
                )
                return

            # Non-newspaper presets strip manual *emphasis* markers for clean preview
            plain_sample = " ".join(self._sample_text.replace("*", "").split())
            if not plain_sample:
                plain_sample = DEFAULT_PREVIEW_SAMPLE.replace("*", "")

            if mode == "capcut_pill":
                self._paint_capcut_pill(
                    painter,
                    res_x,
                    res_y,
                    font,
                    metrics,
                    font_px,
                    base_scale,
                    scaled_margin_v,
                    plain_sample,
                    style,
                )
            else:
                self._paint_active_word_or_standard(
                    painter,
                    res_x,
                    res_y,
                    font,
                    metrics,
                    font_px,
                    base_scale,
                    scaled_margin_v,
                    plain_sample,
                    style,
                    mode=mode,
                )
        finally:
            painter.restore()

    def _paint_capcut_pill(
        self,
        painter: QPainter,
        res_x: int,
        res_y: int,
        font: QFont,
        metrics: QFontMetricsF,
        font_px: int,
        base_scale: float,
        scaled_margin_v: float,
        sample_text: str,
        style: dict[str, object],
    ) -> None:
        timed_words = estimate_word_timings(0.0, 2.5, sample_text)
        if not timed_words:
            return

        max_line_w = max(64.0, float(res_x) * 0.80)
        blocks = _group_words_into_pill_blocks(timed_words, metrics, max_line_w)
        if not blocks:
            return
        block_lines = blocks[0]

        # Exact constants from core/ass_engine.py::_render_capcut_pill_events
        pad_x = 10.0 * base_scale
        pad_y = 6.0 * base_scale
        corner_radius = 10.0 * base_scale

        ref_rect = metrics.tightBoundingRect("Hg")
        min_visual_h = max(float(font_px) * 0.65, float(metrics.xHeight()) * 1.35)
        glyph_h = max(float(ref_rect.height()), min_visual_h)
        visual_y_offset = (
            (float(metrics.ascent()) - float(metrics.descent())) / 2.0
        ) + float(ref_rect.center().y())

        pill_h = glyph_h + (2.0 * pad_y)
        pill_half_h = pill_h / 2.0
        line_step = max(pill_h + (8.0 * base_scale), float(metrics.height()) * 1.05)
        cx = float(res_x) / 2.0

        min_cy = pill_half_h - visual_y_offset
        max_cy = max(min_cy, float(res_y) - pill_half_h - visual_y_offset)
        bottom_cy = max(
            min_cy,
            min(max_cy, float(res_y) - scaled_margin_v - pill_half_h - visual_y_offset),
        )

        flat_count = sum(len(line) for line in block_lines)
        active_idx = 1 if flat_count >= 2 else 0
        if flat_count >= 4:
            active_idx = flat_count // 2

        positioned: list[tuple[str, float, float, float, bool]] = []
        num_lines = len(block_lines)
        flat_cursor = 0
        for line_idx, line_words in enumerate(block_lines):
            line_cy = max(
                min_cy,
                min(max_cy, bottom_cy - ((num_lines - 1 - line_idx) * line_step)),
            )
            full_text = " ".join(w.text for w in line_words)
            line_w = float(metrics.horizontalAdvance(full_text))
            line_left = cx - (line_w / 2.0)

            for w_idx, word in enumerate(line_words):
                prefix_w = (
                    0.0
                    if w_idx == 0
                    else float(
                        metrics.horizontalAdvance(
                            " ".join(lw.text for lw in line_words[:w_idx]) + " "
                        )
                    )
                )
                upto_w = float(
                    metrics.horizontalAdvance(
                        " ".join(lw.text for lw in line_words[: w_idx + 1])
                    )
                )
                word_w = max(1.0, upto_w - prefix_w)
                word_cx = line_left + prefix_w + (word_w / 2.0)
                positioned.append((word.text, word_cx, line_cy, word_w, flat_cursor == active_idx))
                flat_cursor += 1

        primary_color: QColor = style["primary_color"]  # type: ignore[assignment]
        highlight_color: QColor = style["highlight_color"]  # type: ignore[assignment]

        # Layer 0: Active-word rounded pill
        for _text, word_cx, text_cy, word_w, is_active in positioned:
            if not is_active:
                continue
            pill_cy = text_cy + visual_y_offset
            pill_rect = QRectF(
                word_cx - (word_w / 2.0) - pad_x,
                pill_cy - pill_half_h,
                word_w + (2.0 * pad_x),
                pill_h,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(highlight_color)
            painter.drawRoundedRect(pill_rect, corner_radius, corner_radius)

        # Layer 1: Stationary words
        baseline_delta = (float(metrics.ascent()) - float(metrics.descent())) / 2.0
        shadow_px = 2.0 * base_scale
        for text, word_cx, text_cy, word_w, _is_active in positioned:
            baseline_x = word_cx - (word_w / 2.0)
            baseline_y = text_cy + baseline_delta
            _draw_outlined_text(
                painter,
                font,
                baseline_x,
                baseline_y,
                text,
                primary_color,
                outline_color=None,
                outline_width_px=0.0,
                shadow_offset_px=shadow_px,
            )

    def _paint_newspaper_cutout(
        self,
        painter: QPainter,
        res_x: int,
        res_y: int,
        sans_font: QFont,
        sans_metrics: QFontMetricsF,
        font_px: int,
        base_scale: float,
        scaled_margin_v: float,
        style: dict[str, object],
    ) -> None:
        sans_font.setBold(True)
        serif_font = QFont(self._serif_font_name)
        serif_font.setPixelSize(font_px)
        serif_font.setBold(True)
        serif_metrics = QFontMetricsF(serif_font)

        timed_words = estimate_word_timings(0.0, 2.5, self._sample_text)
        if not timed_words:
            return

        cutout_words, cue_has_manual = _prepare_newspaper_cutout_words(timed_words)
        if not cutout_words:
            return

        # Exact constants from core/ass_engine.py::_render_newspaper_cutout_events
        pad_x = 12.0 * base_scale
        pad_y = 6.0 * base_scale
        box_gap = 12.0 * base_scale
        max_row_w = max(64.0, float(res_x) * 0.88)

        groups = _group_newspaper_cutout_words(
            words=cutout_words,
            cue_has_manual=cue_has_manual,
            sans_metrics=sans_metrics,
            serif_metrics=serif_metrics,
            pad_x=pad_x,
            box_gap=box_gap,
            max_row_width=max_row_w,
        )
        if not groups:
            return

        # Prefer a group containing both normal & emphasized words for clearest preview
        chosen_group = next(
            (g for g in groups if any(w.emphasized for w in g) and any(not w.emphasized for w in g)),
            None,
        )
        if chosen_group is None:
            chosen_group = next(
                (g for g in groups if any(w.emphasized for w in g)),
                groups[0],
            )

        norm_box_h, norm_vis_off = _compute_font_box_metrics(sans_metrics, font_px, pad_y)
        emph_box_h, emph_vis_off = _compute_font_box_metrics(serif_metrics, font_px, pad_y)
        row_box_h = max(norm_box_h, emph_box_h)
        row_half_h = row_box_h / 2.0

        safe_pad = 4.0 * base_scale
        min_cy = row_half_h + safe_pad
        max_cy = max(min_cy, float(res_y) - row_half_h - safe_pad)
        row_cy = max(
            min_cy,
            min(max_cy, float(res_y) - scaled_margin_v - row_half_h),
        )

        measured = []
        for word in chosen_group:
            if word.emphasized:
                w_px = max(1.0, float(serif_metrics.horizontalAdvance(word.text)))
                measured.append((word, w_px + (2.0 * pad_x), emph_box_h, emph_vis_off, w_px))
            else:
                w_px = max(1.0, float(sans_metrics.horizontalAdvance(word.text)))
                measured.append((word, w_px + (2.0 * pad_x), norm_box_h, norm_vis_off, w_px))

        total_w = sum(item[1] for item in measured) + (box_gap * max(0, len(measured) - 1))
        cursor_x = (float(res_x) - total_w) / 2.0

        primary_color: QColor = style["primary_color"]  # type: ignore[assignment]
        highlight_color: QColor = style["highlight_color"]  # type: ignore[assignment]
        paper_color = QColor("#E2E2E2")
        emph_text_color = QColor("#F5F5F5")
        shadow_color = QColor(0, 0, 0, 128)
        shadow_off = 3.0 * base_scale

        emph_counter = 0
        for word, box_w, box_h, vis_off, text_w in measured:
            word_cx = cursor_x + (box_w / 2.0)
            cursor_x += box_w + box_gap

            painter.save()
            painter.translate(word_cx, row_cy)

            if word.emphasized:
                angle = _NEWSPAPER_TILT_DEG if (emph_counter % 2 == 0) else -_NEWSPAPER_TILT_DEG
                emph_counter += 1
                # ASS \frz rotates counter-clockwise; QPainter rotates clockwise.
                painter.rotate(-angle)
                box_rect = QRectF(-box_w / 2.0, -box_h / 2.0, box_w, box_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(shadow_color)
                painter.drawRect(box_rect.translated(shadow_off, shadow_off))
                painter.setBrush(highlight_color)
                painter.drawRect(box_rect)

                baseline_delta = (float(serif_metrics.ascent()) - float(serif_metrics.descent())) / 2.0
                painter.setFont(serif_font)
                painter.setPen(emph_text_color)
                painter.drawText(QPointF(-text_w / 2.0, -vis_off + baseline_delta), word.text)
            else:
                box_rect = QRectF(-box_w / 2.0, -box_h / 2.0, box_w, box_h)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(shadow_color)
                painter.drawRect(box_rect.translated(shadow_off, shadow_off))
                painter.setBrush(paper_color)
                painter.drawRect(box_rect)

                baseline_delta = (float(sans_metrics.ascent()) - float(sans_metrics.descent())) / 2.0
                painter.setFont(sans_font)
                painter.setPen(primary_color)
                painter.drawText(QPointF(-text_w / 2.0, -vis_off + baseline_delta), word.text)

            painter.restore()

    def _paint_active_word_or_standard(
        self,
        painter: QPainter,
        res_x: int,
        res_y: int,
        font: QFont,
        metrics: QFontMetricsF,
        font_px: int,
        base_scale: float,
        scaled_margin_v: float,
        sample_text: str,
        style: dict[str, object],
        mode: str,
    ) -> None:
        timed_words = estimate_word_timings(0.0, 2.5, sample_text)
        if not timed_words:
            return

        max_line_w = max(64.0, float(res_x) * 0.80)
        blocks = _group_words_into_pill_blocks(timed_words, metrics, max_line_w)
        if not blocks:
            return
        lines = blocks[0]

        line_h = float(metrics.height())
        num_lines = len(lines)
        total_h = line_h * num_lines

        # Anchor bottom edge of the 1-2 line block at res_y - scaled_margin_v
        # matching libass \an2 / MarginV and _render_active_word_color_events 1:1.
        min_bottom_y = min(float(res_y), max(total_h, float(font_px) * num_lines))
        block_bottom_y = max(
            min_bottom_y,
            min(float(res_y), float(res_y) - scaled_margin_v),
        )
        top_y = block_bottom_y - total_h

        primary_color: QColor = style["primary_color"]  # type: ignore[assignment]
        highlight_color: QColor = style["highlight_color"]  # type: ignore[assignment]
        outline_color: QColor = style["outline_color"]  # type: ignore[assignment]
        enable_bg_box = bool(style["enable_bg_box"])
        bg_box_color = QColor(style["bg_box_color"])  # type: ignore[arg-type]
        bg_box_opacity = int(style["bg_box_opacity"])
        outline_w_px = max(0.0, float(style["outline_width"])) * base_scale
        shadow_px = 0.0 if enable_bg_box else max(0.0, float(style["shadow"])) * base_scale

        flat_count = sum(len(line) for line in lines)
        active_idx = 1 if flat_count >= 2 else 0
        if flat_count >= 4:
            active_idx = flat_count // 2
        karaoke_split = max(1, flat_count // 2)

        flat_cursor = 0
        for line_idx, line_words in enumerate(lines):
            full_text = " ".join(w.text for w in line_words)
            line_w = float(metrics.horizontalAdvance(full_text))
            line_left = (float(res_x) - line_w) / 2.0
            line_top = top_y + (line_idx * line_h)
            baseline_y = line_top + float(metrics.ascent())

            if enable_bg_box:
                box_pad_x = max(8.0 * base_scale, outline_w_px)
                box_pad_y = max(4.0 * base_scale, outline_w_px * 0.45)
                bg_alpha = int(round(max(0, min(100, bg_box_opacity)) * 255 / 100.0))
                fill_bg = QColor(
                    bg_box_color.red(),
                    bg_box_color.green(),
                    bg_box_color.blue(),
                    bg_alpha,
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill_bg)
                painter.drawRoundedRect(
                    QRectF(
                        line_left - box_pad_x,
                        line_top - box_pad_y,
                        line_w + (2.0 * box_pad_x),
                        line_h + (2.0 * box_pad_y),
                    ),
                    4.0 * base_scale,
                    4.0 * base_scale,
                )

            for w_idx, word in enumerate(line_words):
                prefix_w = (
                    0.0
                    if w_idx == 0
                    else float(
                        metrics.horizontalAdvance(
                            " ".join(lw.text for lw in line_words[:w_idx]) + " "
                        )
                    )
                )
                upto_w = float(
                    metrics.horizontalAdvance(
                        " ".join(lw.text for lw in line_words[: w_idx + 1])
                    )
                )
                word_w = max(1.0, upto_w - prefix_w)
                word_x = line_left + prefix_w

                is_active = flat_cursor == active_idx
                if mode == "active_word_color" and is_active:
                    word_color = highlight_color
                elif mode == "word_pop" and is_active:
                    word_color = highlight_color
                elif mode == "karaoke_wipe" and flat_cursor < karaoke_split:
                    word_color = highlight_color
                else:
                    word_color = primary_color

                if mode == "word_pop" and is_active:
                    painter.save()
                    anchor_x = word_x + (word_w / 2.0)
                    anchor_y = baseline_y - (float(metrics.ascent()) * 0.35)
                    painter.translate(anchor_x, anchor_y)
                    painter.scale(1.18, 1.18)
                    _draw_outlined_text(
                        painter,
                        font,
                        -word_w / 2.0,
                        baseline_y - anchor_y,
                        word.text,
                        word_color,
                        None if enable_bg_box else outline_color,
                        0.0 if enable_bg_box else outline_w_px,
                        shadow_px,
                    )
                    painter.restore()
                else:
                    _draw_outlined_text(
                        painter,
                        font,
                        word_x,
                        baseline_y,
                        word.text,
                        word_color,
                        None if enable_bg_box else outline_color,
                        0.0 if enable_bg_box else outline_w_px,
                        shadow_px,
                    )
                flat_cursor += 1


class StylePreviewWidget(QWidget):
    """Self-contained live preview header (16:9 / 9:16 toggle + zoom reset) + QPainter canvas."""

    aspect_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._aspect = "16:9"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)

        self.title_label = QLabel("Live Style Preview")
        self.title_label.setObjectName("MutedLabel")
        self.title_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #cbd5e1;")

        self.btn_reset_zoom = QPushButton("100%")
        self.btn_reset_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_zoom.setFixedHeight(24)
        self.btn_reset_zoom.setToolTip(
            "Scroll to zoom, drag to pan, double-click or click to reset to 100%"
        )
        self.btn_reset_zoom.clicked.connect(self.reset_view)

        self.btn_16_9 = QPushButton("16:9")
        self.btn_16_9.setCheckable(True)
        self.btn_16_9.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_16_9.setFixedHeight(24)
        self.btn_16_9.clicked.connect(lambda: self.set_aspect("16:9", emit_signal=True))

        self.btn_9_16 = QPushButton("9:16")
        self.btn_9_16.setCheckable(True)
        self.btn_9_16.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_9_16.setFixedHeight(24)
        self.btn_9_16.clicked.connect(lambda: self.set_aspect("9:16", emit_signal=True))

        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        header_row.addWidget(self.btn_reset_zoom)
        header_row.addWidget(self.btn_16_9)
        header_row.addWidget(self.btn_9_16)
        layout.addLayout(header_row)

        self._canvas = _StylePreviewCanvas(self)
        self._canvas.view_changed.connect(self._on_canvas_view_changed)
        layout.addWidget(self._canvas)

        self._apply_toggle_styles()
        self._on_canvas_view_changed(1.0, False)

    @property
    def _zoom(self) -> float:
        return self._canvas._zoom

    @_zoom.setter
    def _zoom(self, value: float) -> None:
        self._canvas._zoom = max(
            _StylePreviewCanvas._MIN_ZOOM,
            min(_StylePreviewCanvas._MAX_ZOOM, float(value)),
        )
        self._canvas._update_hover_cursor()
        self._canvas._emit_view_changed()
        self._canvas.update()

    @property
    def _pan(self) -> QPointF:
        return self._canvas._pan

    @_pan.setter
    def _pan(self, value: QPointF) -> None:
        self._canvas._pan = QPointF(value)
        self._canvas._update_hover_cursor()
        self._canvas._emit_view_changed()
        self._canvas.update()

    def _on_canvas_view_changed(self, zoom: float, is_modified: bool) -> None:
        pct = int(round(zoom * 100.0))
        if is_modified:
            self.btn_reset_zoom.setText(f"{pct}% ↺")
            self.btn_reset_zoom.setStyleSheet(
                "QPushButton { background-color: #1e3a5f; color: #7dd3fc;"
                " border: 1px solid #38bdf8; border-radius: 5px; padding: 2px 8px;"
                " font-size: 11px; font-weight: 700; }"
                "QPushButton:hover { background-color: #2563eb; color: #ffffff; }"
            )
        else:
            self.btn_reset_zoom.setText("100%")
            self.btn_reset_zoom.setStyleSheet(
                "QPushButton { background-color: #0f172a; color: #94a3b8;"
                " border: 1px solid #334155; border-radius: 5px; padding: 2px 8px;"
                " font-size: 11px; font-weight: 600; }"
                "QPushButton:hover { background-color: #1e293b; color: #e2e8f0; }"
            )

    def reset_view(self) -> None:
        """Reset interactive preview zoom to 100% and pan to (0, 0)."""
        self._canvas.reset_view()

    def set_zoom_reset_tooltip(self, tooltip: str) -> None:
        self.btn_reset_zoom.setToolTip(tooltip)

    def _apply_toggle_styles(self) -> None:
        active_qss = (
            "QPushButton { background-color: #2563eb; color: #ffffff;"
            " border: 1px solid #3b82f6; border-radius: 5px; padding: 2px 10px;"
            " font-size: 11px; font-weight: 700; }"
        )
        inactive_qss = (
            "QPushButton { background-color: #0f172a; color: #94a3b8;"
            " border: 1px solid #475569; border-radius: 5px; padding: 2px 10px;"
            " font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background-color: #1e293b; color: #e2e8f0; }"
        )
        is_landscape = self._aspect == "16:9"
        self.btn_16_9.setChecked(is_landscape)
        self.btn_9_16.setChecked(not is_landscape)
        self.btn_16_9.setStyleSheet(active_qss if is_landscape else inactive_qss)
        self.btn_9_16.setStyleSheet(inactive_qss if is_landscape else active_qss)

    def aspect(self) -> str:
        return self._aspect

    def set_aspect(self, aspect: str, emit_signal: bool = False) -> None:
        normalized = "9:16" if aspect == "9:16" else "16:9"
        changed = self._aspect != normalized
        self._aspect = normalized
        self._apply_toggle_styles()
        self._canvas.set_aspect(normalized)
        if emit_signal and changed:
            self.aspect_changed.emit(normalized)

    def set_video_dimensions(self, width: int, height: int) -> None:
        """Match preview canvas aspect ratio to loaded video dimensions while keeping toggle synced."""
        normalized = "9:16" if int(height) > int(width) else "16:9"
        self._aspect = normalized
        self._apply_toggle_styles()
        self._canvas.set_video_dimensions(width, height)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_sample_text(self, text: str | None) -> None:
        self._canvas.set_sample_text(text)

    def set_style_state(self, preset: SubtitlePreset, config: AssConfig) -> None:
        self._canvas.set_style_state(preset, config)
