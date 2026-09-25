from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.prayer_card import render_prayer_alert, render_prayer_card
from core.prayer_service import PrayerService


async def main() -> None:
    async with aiohttp.ClientSession(headers={"User-Agent": "RahmaDiscordBot/preview"}) as session:
        service = PrayerService(session, "https://api.aladhan.com/v1")
        settings = {
            "city": "Cairo",
            "country": "Egypt",
            "timezone": "Africa/Cairo",
            "calculation_method": 5,
            "asr_school": 0,
        }
        day = await service.today(settings)
        output = Path(__file__).resolve().parents[1] / "prayer-times-preview-cairo.png"
        output.write_bytes(
            render_prayer_card(day, "القاهرة", "مصر").getvalue()
        )
        alert_output = Path(__file__).resolve().parents[1] / "prayer-alert-preview-cairo.png"
        alert_output.write_bytes(
            render_prayer_alert("المغرب", day.timings["Maghrib"], "القاهرة", "مصر").getvalue()
        )
        print(f"Saved sample card for {settings['city']}, {settings['country']}: {output}")
        print(f"Saved prayer-alert sample: {alert_output}")
        print(f"Gregorian {day.gregorian_date} | Hijri {day.hijri_date} | {day.timings}")


if __name__ == "__main__":
    asyncio.run(main())
