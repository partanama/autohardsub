"""Built-in ASS subtitle visual presets for content creators."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitlePreset:
    """Configuration defining an ASS subtitle visual style and animation mode."""

    id: str
    name: str
    description: str
    animation_mode: str  # "static", "word_pop", "karaoke_wipe", "box", "capcut_pill", "active_word_color"
    font_name: str
    primary_colour: str
    secondary_colour: str
    outline_colour: str
    back_colour: str
    highlight_colour: str
    bold: int
    border_style: int
    outline: float
    shadow: float
    alignment: int
    default_font_size: int
    default_margin_v: int
    margin_l: int = 40
    margin_r: int = 40
    # UI-friendly RGB hex defaults for color swatches & background box sync
    primary_text_hex: str = "#FFFFFF"
    highlight_hex: str = "#FFFF00"
    outline_hex: str = "#000000"
    bg_box_hex: str = "#000000"
    bg_box_enabled: bool = False
    bg_box_opacity: int = 50  # 0 (transparent) .. 100 (solid)


PRESETS: tuple[SubtitlePreset, ...] = (
    SubtitlePreset(
        id="youtube_clean",
        name="YouTube Clean",
        description="Teks putih bersih dengan garis tepi hitam dan bayangan halus.",
        animation_mode="static",
        font_name="Arial",
        primary_colour="&H00FFFFFF",
        secondary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H80000000",
        highlight_colour="&H00FFFFFF",
        bold=-1,
        border_style=1,
        outline=3.0,
        shadow=2.0,
        alignment=2,
        default_font_size=54,
        default_margin_v=60,
        primary_text_hex="#FFFFFF",
        highlight_hex="#FFFF00",
        outline_hex="#000000",
        bg_box_hex="#000000",
        bg_box_enabled=False,
        bg_box_opacity=50,
    ),
    SubtitlePreset(
        id="reels_pop",
        name="Reels / Shorts Pop Kuning",
        description="Sorotan kuning per kata dengan efek membal (bounce) untuk video vertikal.",
        animation_mode="word_pop",
        font_name="Arial",
        primary_colour="&H00FFFFFF",
        secondary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H80000000",
        highlight_colour="&H0000FFFF",
        bold=-1,
        border_style=1,
        outline=4.5,
        shadow=1.5,
        alignment=2,
        default_font_size=64,
        default_margin_v=180,
        primary_text_hex="#FFFFFF",
        highlight_hex="#FFFF00",
        outline_hex="#000000",
        bg_box_hex="#000000",
        bg_box_enabled=False,
        bg_box_opacity=50,
    ),
    SubtitlePreset(
        id="karaoke_wipe",
        name="Karaoke Wipe",
        description="Transisi warna halus kiri-ke-kanan dari putih ke kuning per kata.",
        animation_mode="karaoke_wipe",
        font_name="Arial",
        primary_colour="&H0000FFFF",
        secondary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H80000000",
        highlight_colour="&H0000FFFF",
        bold=-1,
        border_style=1,
        outline=3.5,
        shadow=2.0,
        alignment=2,
        default_font_size=58,
        default_margin_v=90,
        primary_text_hex="#FFFFFF",
        highlight_hex="#FFFF00",
        outline_hex="#000000",
        bg_box_hex="#000000",
        bg_box_enabled=False,
        bg_box_opacity=50,
    ),
    SubtitlePreset(
        id="box_kontras",
        name="Box Kontras (TikTok Style)",
        description="Latar kotak hitam semi-transparan dengan teks putih kontras tinggi.",
        animation_mode="box",
        font_name="Arial",
        primary_colour="&H00FFFFFF",
        secondary_colour="&H00FFFFFF",
        # libass BorderStyle=3 uses OutlineColour as the opaque box fill color.
        outline_colour="&H80000000",
        back_colour="&H80000000",
        highlight_colour="&H00FFFFFF",
        bold=-1,
        border_style=3,
        outline=10.0,
        shadow=0.0,
        alignment=2,
        default_font_size=54,
        default_margin_v=140,
        primary_text_hex="#FFFFFF",
        highlight_hex="#FFFF00",
        outline_hex="#000000",
        bg_box_hex="#000000",
        bg_box_enabled=True,
        bg_box_opacity=50,
    ),
    SubtitlePreset(
        id="capcut_pill",
        name="CapCut Pill (Active Word)",
        description="Kotak kapsul berwarna mengikuti kata aktif secara halus dengan teks putih tetap diam (gaya CapCut).",
        animation_mode="capcut_pill",
        font_name="Montserrat",
        primary_colour="&H00FFFFFF",
        secondary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H80000000",
        highlight_colour="&H00F6006D",
        bold=-1,
        border_style=1,
        outline=0.0,
        shadow=2.0,
        alignment=2,
        default_font_size=58,
        default_margin_v=140,
        primary_text_hex="#FFFFFF",
        highlight_hex="#6D00F6",
        outline_hex="#000000",
        bg_box_hex="#000000",
        bg_box_enabled=False,
        bg_box_opacity=50,
    ),
    SubtitlePreset(
        id="active_word_color",
        name="Active Word Color (News/Doc)",
        description="Semua kata tetap diam dengan outline hitam tegas, sementara kata yang sedang diucapkan berubah warna highlight (gaya Berita/Dokumenter).",
        animation_mode="active_word_color",
        font_name="Montserrat",
        primary_colour="&H00FFFFFF",
        secondary_colour="&H00FFFFFF",
        outline_colour="&H00000000",
        back_colour="&H80000000",
        highlight_colour="&H001A8CFF",
        bold=-1,
        border_style=1,
        outline=3.5,
        shadow=1.5,
        alignment=2,
        default_font_size=58,
        default_margin_v=140,
        primary_text_hex="#FFFFFF",
        highlight_hex="#FF8C1A",
        outline_hex="#000000",
        bg_box_hex="#000000",
        bg_box_enabled=False,
        bg_box_opacity=50,
    ),
)

PRESET_MAP: dict[str, SubtitlePreset] = {preset.id: preset for preset in PRESETS}


def get_preset(preset_id: str) -> SubtitlePreset:
    """Return a SubtitlePreset by its id."""
    if preset_id not in PRESET_MAP:
        raise KeyError(f"Preset subtitle tidak dikenal: {preset_id}")
    return PRESET_MAP[preset_id]
