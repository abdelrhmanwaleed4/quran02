from __future__ import annotations

from pathlib import Path
from typing import Any

import discord


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
THEME_ASSETS = {
    "quran": "quran-banner.png",
    "azkar": "azkar-banner.png",
    "dua": "azkar-banner.png",
    "prayer": "prayer-banner.png",
    "ramadan": "ramadan-banner.png",
    "reminder": "reminder-banner.png",
}
THEME_COLOURS = {
    "quran": 0x126E5A,
    "azkar": 0x1E5C74,
    "dua": 0x1E5C74,
    "prayer": 0x1D4F91,
    "ramadan": 0x264653,
    "reminder": 0x665191,
}


def make_embed(
    title: str,
    description: str = "",
    *,
    theme: str = "reminder",
    source: str | None = None,
    settings: dict[str, Any] | None = None,
) -> tuple[discord.Embed, discord.File | None]:
    """Create the uniform Rahma embed and attach its topic-specific local banner."""
    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour(THEME_COLOURS.get(theme, THEME_COLOURS["reminder"])),
    )
    embed.set_footer(text=(f"المصدر: {source}" if source else "رحمة • القرآن والأذكار والدعاء"))

    override = ((settings or {}).get("banner_urls") or {}).get(theme)
    if override:
        embed.set_image(url=override)
        return embed, None

    asset_name = THEME_ASSETS.get(theme, THEME_ASSETS["reminder"])
    asset = ASSET_DIR / asset_name
    if asset.exists():
        embed.set_image(url=f"attachment://{asset_name}")
        return embed, discord.File(asset, filename=asset_name)
    return embed, None


def add_prayer_fields(embed: discord.Embed, timings: dict[str, str]) -> discord.Embed:
    labels = {
        "Fajr": "الفجر",
        "Sunrise": "الشروق",
        "Dhuhr": "الظهر",
        "Asr": "العصر",
        "Maghrib": "المغرب",
        "Isha": "العشاء",
    }
    for key in ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"):
        embed.add_field(name=labels[key], value=f"`{timings[key]}`", inline=True)
    return embed
