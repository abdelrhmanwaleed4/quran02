from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.prayer_service import PrayerDay


WIDTH, HEIGHT = 1600, 1000
NAVY = (8, 16, 31)
NAVY_LIGHT = (17, 32, 54)
BURGUNDY = (75, 18, 42)
GOLD = (221, 184, 102)
GOLD_LIGHT = (246, 221, 160)
WHITE = (248, 246, 239)
MUTED = (182, 191, 204)
CARD = (16, 28, 45)
CARD_NEXT = (48, 25, 44)
GREEN = (77, 178, 123)
FONT_REGULAR = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"
FONT_MIXED = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
ARABIC_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
PRAYERS = (
    ("Fajr", "الفجر"),
    ("Sunrise", "الشروق"),
    ("Dhuhr", "الظهر"),
    ("Asr", "العصر"),
    ("Maghrib", "المغرب"),
    ("Isha", "العشاء"),
)


def localize_digits(text: str) -> str:
    return str(text).translate(ARABIC_DIGITS)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    if not Path(path).exists():
        # Noto fonts are present on the validated host; this fallback aids minimal Linux installs.
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size=size)


def _mixed_font(size: int) -> ImageFont.FreeTypeFont:
    if Path(FONT_MIXED).exists():
        return ImageFont.truetype(FONT_MIXED, size=size)
    return _font(size)


def _centered_arabic(draw: ImageDraw.ImageDraw, center_x: int, top: int, text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    bounds = draw.textbbox((0, 0), text, font=font, direction="rtl")
    width = bounds[2] - bounds[0]
    draw.text((center_x - width / 2, top), text, font=font, fill=fill, direction="rtl")


def _right_arabic(draw: ImageDraw.ImageDraw, right_x: int, top: int, text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    draw.text((right_x, top), text, font=font, fill=fill, anchor="ra", direction="rtl")


def render_prayer_card(
    prayer_day: PrayerDay,
    city: str,
    country: str,
    *,
    highlight_prayer: str | None = None,
    generated_at: datetime | None = None,
) -> BytesIO:
    """Render exact API-provided timings into a crisp branded Arabic PNG card."""
    image = Image.new("RGB", (WIDTH, HEIGHT), NAVY)
    draw = ImageDraw.Draw(image)
    # Soft, low-cost color fields give the background Rahma's navy/burgundy identity.
    draw.ellipse((WIDTH - 770, -430, WIDTH + 430, 680), fill=(31, 16, 39))
    draw.ellipse((WIDTH - 520, 500, WIDTH + 360, HEIGHT + 410), fill=(24, 15, 37))
    draw.polygon(((0, HEIGHT - 120), (500, HEIGHT), (0, HEIGHT)), fill=(11, 22, 39))
    margin = 72
    # Restrained signature frame and stepped arch motifs echo Rahma's profile identity.
    draw.rounded_rectangle((24, 24, WIDTH - 24, HEIGHT - 24), radius=36, outline=(91, 77, 54), width=2)
    draw.line((margin, 48, margin, 220), fill=GOLD, width=4)
    draw.line((WIDTH - margin, 48, WIDTH - margin, 220), fill=GOLD, width=4)
    draw.line((margin, 48, WIDTH - margin, 48), fill=(112, 84, 50), width=2)

    # Small crescent insignia.
    cx, cy, radius = WIDTH - 132, 128, 36
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=GOLD_LIGHT)
    draw.ellipse((cx - radius + 17, cy - radius - 9, cx + radius + 17, cy + radius - 9), fill=NAVY_LIGHT)
    draw.ellipse((cx + 47, cy - 41, cx + 55, cy - 33), fill=GOLD)

    _right_arabic(draw, WIDTH - 205, 75, "مواقيت الصلاة اليوم", _font(58, bold=True), WHITE)
    _right_arabic(draw, WIDTH - 205, 151, f"{city}، {country}", _mixed_font(31), GOLD_LIGHT)
    date_line = (
        f"الميلادي {localize_digits(prayer_day.gregorian_date)}، "
        f"الهجري {localize_digits(prayer_day.hijri_date)} هـ"
    )
    _right_arabic(draw, WIDTH - 205, 207, date_line, _font(24), MUTED)

    # Six broad cards: the five daily prayers and sunrise, matching the provided layout.
    grid_left = margin
    grid_right = WIDTH - margin
    gap_x, gap_y = 28, 26
    card_width = (grid_right - grid_left - 2 * gap_x) // 3
    card_height = 245
    grid_top = 310
    x_positions = [grid_left + i * (card_width + gap_x) for i in range(3)]
    y_positions = [grid_top, grid_top + card_height + gap_y]
    positions = {
        "Fajr": (x_positions[0], y_positions[0]),
        "Sunrise": (x_positions[1], y_positions[0]),
        "Dhuhr": (x_positions[2], y_positions[0]),
        "Asr": (x_positions[0], y_positions[1]),
        "Maghrib": (x_positions[1], y_positions[1]),
        "Isha": (x_positions[2], y_positions[1]),
    }

    for key, label in PRAYERS:
        x, y = positions[key]
        x2, y2 = x + card_width, y + card_height
        is_highlight = key == highlight_prayer
        fill = CARD_NEXT if is_highlight else CARD
        outline = GOLD if is_highlight else (69, 81, 98)
        draw.rounded_rectangle((x, y, x2, y2), radius=28, fill=fill, outline=outline, width=3 if is_highlight else 2)
        draw.line((x + 34, y + 14, x2 - 34, y + 14), fill=GOLD if is_highlight else (58, 76, 97), width=3)
        if is_highlight:
            draw.ellipse((x2 - 42, y + 31, x2 - 24, y + 49), fill=GREEN)
        _centered_arabic(draw, x + card_width // 2, y + 47, label, _font(38, bold=True), GOLD_LIGHT if is_highlight else WHITE)
        hour, minute = prayer_day.timings[key].split(":", 1)
        time_text = f"{localize_digits(hour)}:{localize_digits(minute)}"
        _centered_arabic(draw, x + card_width // 2, y + 115, time_text, _font(58, bold=True), WHITE)
        _centered_arabic(draw, x + card_width // 2, y + 190, "الصلاة القادمة" if is_highlight else "بحسب التوقيت المحلي", _font(20), MUTED)

    footer_y = HEIGHT - 92
    draw.line((margin, footer_y - 20, WIDTH - margin, footer_y - 20), fill=(66, 73, 88), width=2)
    _right_arabic(draw, WIDTH - margin, footer_y, f"طريقة الحساب: {prayer_day.method_name}", _font(20), MUTED)
    generated = generated_at or datetime.now().astimezone()
    _centered_arabic(draw, WIDTH // 2, footer_y + 1, f"رحمة - تحديث {localize_digits(generated.strftime('%H:%M'))}", _font(20), GOLD_LIGHT)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def render_prayer_alert(
    prayer_name: str,
    prayer_time: str,
    city: str,
    country: str,
) -> BytesIO:
    """Create a subdued, notification-style image for the prayer that just began."""
    alert_width, alert_height = 1600, 720
    source_path = ASSET_DIR / "prayer-banner.png"
    if source_path.exists():
        background = Image.open(source_path).convert("RGB")
        background = ImageOps.fit(background, (alert_width, alert_height), method=Image.Resampling.LANCZOS)
        background = Image.blend(background, Image.new("RGB", background.size, (6, 10, 17)), 0.78)
    else:
        background = Image.new("RGB", (alert_width, alert_height), NAVY)

    draw = ImageDraw.Draw(background)
    draw.rounded_rectangle((24, 24, alert_width - 24, alert_height - 24), radius=34, outline=(92, 77, 58), width=2)
    panel = (92, 206, alert_width - 92, alert_height - 150)
    draw.rounded_rectangle(panel, radius=40, fill=(8, 13, 21), outline=(156, 140, 110), width=2)
    draw.line((panel[0] + 56, panel[1] + 4, panel[2] - 56, panel[1] + 4), fill=GOLD, width=3)

    # Small crescent motif consistent with Rahma's bot icon.
    cx, cy, radius = alert_width - 158, 114, 32
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=GOLD_LIGHT)
    draw.ellipse((cx - radius + 15, cy - radius - 8, cx + radius + 15, cy + radius - 8), fill=(8, 13, 21))

    _centered_arabic(
        draw,
        alert_width // 2,
        270,
        f"حان الآن وقت صلاة {prayer_name}",
        _font(55, bold=True),
        WHITE,
    )
    _centered_arabic(
        draw,
        alert_width // 2,
        366,
        f"حسب توقيت {city}، {country}",
        _mixed_font(30),
        MUTED,
    )
    _centered_arabic(
        draw,
        alert_width // 2,
        425,
        f"الساعة {localize_digits(prayer_time)}",
        _font(30, bold=True),
        GOLD_LIGHT,
    )
    _centered_arabic(draw, alert_width // 2, 620, "رحمة - تذكير الصلاة", _font(21), MUTED)

    output = BytesIO()
    background.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
