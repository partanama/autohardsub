from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication


def hex_to_ass_bgr(hex_color: str) -> str:
    """Konversi '#6D00F6' menjadi format warna ASS '&HF6006D&'."""
    h = hex_color.strip().lstrip("#")
    if len(h) != 6:
        return "&HF6006D&"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{b.upper()}{g.upper()}{r.upper()}&"


def build_rounded_rect_ass(x: float, y: float, w: float, h: float, radius: float) -> str:
    """
    Menghasilkan perintah drawing vektor ASS ({\\p1} ... {\\p0}) berbentuk
    persegi panjang sudut membulat menggunakan kurva Bezier kubik (k = 0.5523).
    """
    r = min(radius, w / 2.0, h / 2.0)
    k = 0.55228475
    c = r * k

    x0, y0 = x, y
    x1, y1 = x + w, y + h

    # Format koordinat ASS drawing memakai bilangan bulat (sub-pixel tidak didukung \p1)
    def p(vx: float, vy: float) -> str:
        return f"{round(vx)} {round(vy)}"

    commands = [
        f"m {p(x0 + r, y0)}",
        f"l {p(x1 - r, y0)}",
        f"b {p(x1 - r + c, y0)} {p(x1, y0 + r - c)} {p(x1, y0 + r)}",
        f"l {p(x1, y1 - r)}",
        f"b {p(x1, y1 - r + c)} {p(x1 - r + c, y1)} {p(x1 - r, y1)}",
        f"l {p(x0 + r, y1)}",
        f"b {p(x0 + r - c, y1)} {p(x0, y1 - r + c)} {p(x0, y1 - r)}",
        f"l {p(x0, y0 + r)}",
        f"b {p(x0, y0 + r - c)} {p(x0 + r - c, y0)} {p(x0 + r, y0)}",
    ]
    return "{\\p1}" + " ".join(commands) + "{\\p0}"


def format_ass_time(seconds: float) -> str:
    """Konversi detik (float) ke format waktu ASS 'H:MM:SS.cs'."""
    total_cs = max(0, round(seconds * 100))
    cs = total_cs % 100
    total_sec = total_cs // 100
    sec = total_sec % 60
    total_min = total_sec // 60
    mins = total_min % 60
    hrs = total_min // 60
    return f"{hrs}:{mins:02d}:{sec:02d}.{cs:02d}"


def generate_capcut_pill_dialogues(
    words: list[dict],
    play_res_x: int,
    play_res_y: int,
    font_family: str = "Montserrat",
    font_size_1080p: int = 58,
    pill_hex_color: str = "#6D00F6",
    text_hex_color: str = "#FFFFFF",
    bottom_margin_ratio: float = 0.14,
) -> list[str]:
    """
    Menghasilkan daftar baris 'Dialogue:' 2-layer (Layer 0: Pill Ungu, Layer 1: Teks Statis)
    untuk 1 blok kalimat (maksimal 2 baris) yang presisi di 16:9 maupun 9:16.

    Parameter `words`: list of {"text": str, "start": float, "end": float}
    """
    if not words:
        return []

    # Pastikan QApplication sudah aktif sebelum memanggil QFontMetricsF
    if QApplication.instance() is None:
        _ = QApplication([])

    # Skala proporsional berbasis sisi terpendek agar ukuran teks & padding
    # seimbang baik di 1920x1080 (16:9) maupun 1080x1920 (9:16)
    base_scale = min(play_res_x, play_res_y) / 1080.0
    pixel_size = max(16, round(font_size_1080p * base_scale))

    font = QFont(font_family)
    font.setBold(True)
    # WAJIB setPixelSize agar bebas dari pengaruh Windows DPI Scaling (125%/150%)
    font.setPixelSize(pixel_size)
    metrics = QFontMetricsF(font)

    space_w = metrics.horizontalAdvance(" ")
    line_height = metrics.height()
    line_spacing = line_height * 1.22

    # Batas lebar maksimal per baris: 82% dari lebar video (aman untuk 9:16 maupun 16:9)
    max_line_width = play_res_x * 0.82

    # 1. Susun kata ke dalam maksimal 2 baris
    lines: list[list[dict]] = [[]]
    current_w = 0.0

    for w_item in words:
        w_text = w_item["text"]
        w_width = metrics.horizontalAdvance(w_text)
        added_w = w_width if not lines[-1] else (space_w + w_width)

        if lines[-1] and (current_w + added_w > max_line_width) and len(lines) < 2:
            lines.append([])
            current_w = 0.0
            added_w = w_width

        lines[-1].append({**w_item, "width": w_width})
        current_w += added_w

    # 2. Hitung posisi Y blok di bagian bawah tengah layar
    num_lines = len(lines)
    total_block_h = line_height + (num_lines - 1) * line_spacing
    block_bottom_y = play_res_y * (1.0 - bottom_margin_ratio)
    block_top_y = block_bottom_y - total_block_h

    # Padding & radius kotak pill (ikut skala resolusi)
    pad_x = 18.0 * base_scale
    pad_y = 7.0 * base_scale
    corner_radius = 12.0 * base_scale

    ass_pill_color = hex_to_ass_bgr(pill_hex_color)
    ass_text_color = hex_to_ass_bgr(text_hex_color)

    dialogues: list[str] = []
    block_start = format_ass_time(words[0]["start"])
    block_end = format_ass_time(words[-1]["end"])

    # 3. Emit Layer 0 (Kotak Pill bergerak per kata) & Layer 1 (Teks statis per baris)
    for line_idx, line_words in enumerate(lines):
        line_text = " ".join(w["text"] for w in line_words)
        line_total_w = sum(w["width"] for w in line_words) + space_w * (len(line_words) - 1)

        line_top_y = block_top_y + line_idx * line_spacing
        line_center_y = line_top_y + (line_height / 2.0)
        cursor_x = (play_res_x - line_total_w) / 2.0

        # Layer 1: Teks putih statis selama durasi penuh blok (anti-geser)
        text_tag = (
            f"{{\\an5\\pos({round(play_res_x / 2)},{round(line_center_y)})"
            f"\\fn{font_family}\\fs{pixel_size}\\b1"
            f"\\1c{ass_text_color}\\bord0\\shad2\\3c&H000000&}}"
        )
        dialogues.append(f"Dialogue: 1,{block_start},{block_end},Default,,0,0,0,,{text_tag}{line_text}")

        # Layer 0: Kotak pill rounded di belakang kata yang sedang aktif
        for w in line_words:
            w_start = format_ass_time(w["start"])
            w_end = format_ass_time(w["end"])

            pill_x = cursor_x - pad_x
            pill_y = line_top_y - pad_y
            pill_w = w["width"] + (pad_x * 2.0)
            pill_h = line_height + (pad_y * 2.0)

            vec_draw = build_rounded_rect_ass(pill_x, pill_y, pill_w, pill_h, corner_radius)
            pill_tag = f"{{\\an7\\pos(0,0)\\1c{ass_pill_color}\\bord0\\shad0}}{vec_draw}"
            dialogues.append(f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{pill_tag}")

            cursor_x += w["width"] + space_w

    return dialogues