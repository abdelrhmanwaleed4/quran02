from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Sequence

import discord
from PIL import Image, ImageDraw, ImageFont


WIDTH = 1600
NAVY = (8, 16, 31)
PANEL = (14, 24, 39)
PANEL_ALT = (26, 23, 39)
GOLD = (221, 184, 102)
GOLD_LIGHT = (246, 221, 160)
WHITE = (248, 246, 239)
MUTED = (183, 191, 201)
REGULAR_FONT = "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"
BOLD_FONT = "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf"

Section = tuple[str | None, str, str | None]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT if bold else REGULAR_FONT
    if not Path(path).exists():
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    return ImageFont.truetype(path, size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap exact content by measured width without dropping words or citations."""
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and draw.textlength(candidate, font=font, direction="rtl") > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def _draw_centered_lines(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    top: int,
    lines: Sequence[str],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    line_height: int,
) -> None:
    for line in lines:
        bounds = draw.textbbox((0, 0), line, font=font, direction="rtl")
        width = bounds[2] - bounds[0]
        draw.text((center_x - width / 2, top), line, font=font, fill=fill, direction="rtl")
        top += line_height


def render_content_poster(title: str, sections: Sequence[Section]) -> BytesIO:
    """Render exact Arabic content and its references into a Rahma-branded poster."""
    safe_sections = list(sections) or [(None, "", None)]
    title_font = _font(54, bold=True)
    heading_font = _font(35, bold=True)
    body_font = _font(36)
    source_font = _font(23)
    probe = Image.new("RGB", (WIDTH, 100), NAVY)
    probe_draw = ImageDraw.Draw(probe)
    text_width = WIDTH - 300
    title_lines = _wrap(probe_draw, title, title_font, text_width)
    prepared: list[tuple[list[str], list[str], list[str]]] = []
    measured_height = 245 + len(title_lines) * 70 + 95

    for heading, body, source in safe_sections:
        heading_lines = _wrap(probe_draw, heading, heading_font, text_width) if heading else []
        body_lines = _wrap(probe_draw, body, body_font, text_width)
        source_lines = _wrap(probe_draw, source, source_font, text_width) if source else []
        section_height = 86 + len(heading_lines) * 52 + len(body_lines) * 57 + len(source_lines) * 37
        measured_height += section_height + 28
        prepared.append((heading_lines, body_lines, source_lines))

    height = max(760, measured_height)
    image = Image.new("RGB", (WIDTH, height), NAVY)
    draw = ImageDraw.Draw(image)
    draw.ellipse((WIDTH - 670, -420, WIDTH + 290, 550), fill=(28, 17, 38))
    draw.ellipse((-420, height - 410, 560, height + 500), fill=(15, 24, 42))
    draw.rounded_rectangle((22, 22, WIDTH - 22, height - 22), radius=38, outline=(103, 84, 53), width=2)
    draw.line((90, 58, WIDTH - 90, 58), fill=GOLD, width=3)

    # Simple crescent mark, deliberately text-free so it remains clean at phone size.
    cx, cy, radius = WIDTH - 135, 139, 32
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=GOLD_LIGHT)
    draw.ellipse((cx - radius + 15, cy - radius - 8, cx + radius + 15, cy + radius - 8), fill=NAVY)

    y = 105
    _draw_centered_lines(draw, WIDTH // 2, y, title_lines, title_font, WHITE, 70)
    y += len(title_lines) * 70 + 46

    for index, ((heading_lines, body_lines, source_lines), (heading, _, _)) in enumerate(zip(prepared, safe_sections)):
        section_height = 86 + len(heading_lines) * 52 + len(body_lines) * 57 + len(source_lines) * 37
        box = (100, y, WIDTH - 100, y + section_height)
        draw.rounded_rectangle(box, radius=28, fill=PANEL if index % 2 == 0 else PANEL_ALT, outline=(63, 74, 91), width=2)
        draw.line((box[0] + 42, box[1] + 12, box[2] - 42, box[1] + 12), fill=GOLD if heading else (72, 87, 102), width=3)
        inner_top = y + 30
        if heading_lines:
            _draw_centered_lines(draw, WIDTH // 2, inner_top, heading_lines, heading_font, GOLD_LIGHT, 52)
            inner_top += len(heading_lines) * 52 + 12
        _draw_centered_lines(draw, WIDTH // 2, inner_top, body_lines, body_font, WHITE, 57)
        inner_top += len(body_lines) * 57 + 6
        if source_lines:
            _draw_centered_lines(draw, WIDTH // 2, inner_top, source_lines, source_font, MUTED, 37)
        y += section_height + 28

    draw.line((100, height - 96, WIDTH - 100, height - 96), fill=(63, 74, 91), width=2)
    footer = "رحمة - القرآن والأذكار والدعاء"
    footer_font = _font(23)
    footer_width = draw.textlength(footer, font=footer_font, direction="rtl")
    draw.text(((WIDTH - footer_width) / 2, height - 74), footer, font=footer_font, fill=GOLD_LIGHT, direction="rtl")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def image_card_embed(
    title: str,
    image: BytesIO,
    filename: str,
    *,
    colour: int = 0x126E5A,
    footer: str = "رحمة",
    description: str | None = None,
) -> tuple[discord.Embed, discord.File]:
    embed = discord.Embed(title=title, description=description, colour=discord.Colour(colour))
    embed.set_image(url=f"attachment://{filename}")
    embed.set_footer(text=footer)
    image.seek(0)
    return embed, discord.File(image, filename=filename)
