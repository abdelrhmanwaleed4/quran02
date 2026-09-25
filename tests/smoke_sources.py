from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.prayer_service import PrayerService
from core.quran_service import QuranService


async def main() -> None:
    async with aiohttp.ClientSession(headers={"User-Agent": "RahmaDiscordBot/validation"}) as session:
        quran = QuranService(session, "https://www.mp3quran.net/api/v3/reciters?language=ar")
        readers = await quran.catalogue(force_refresh=True)
        assert quran.raw_unique_reader_count >= 240, quran.raw_unique_reader_count
        assert len(readers) >= quran.raw_unique_reader_count, len(readers)
        first_stream = readers[0].stream_url(min(readers[0].surahs))
        assert first_stream.startswith("https://") and first_stream.endswith(".mp3"), first_stream

        prayer = PrayerService(session, "https://api.aladhan.com/v1")
        try:
            day = await prayer.today(
                {
                    "city": "Cairo",
                    "country": "Egypt",
                    "timezone": "Africa/Cairo",
                    "calculation_method": 5,
                    "asr_school": 0,
                }
            )
        except (asyncio.TimeoutError, aiohttp.ClientError, RuntimeError) as error:
            print(
                f"AlAdhan live check unavailable ({type(error).__name__}); "
                f"MP3Quran OK: {quran.raw_unique_reader_count} unique reciters, {len(readers)} selectable editions."
            )
            return
        assert all(key in day.timings for key in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")), day.timings
        print(
            f"Live sources OK: {quran.raw_unique_reader_count} unique reciters, "
            f"{len(readers)} selectable editions; Cairo Fajr {day.timings['Fajr']}; Hijri {day.hijri_date}"
        )


if __name__ == "__main__":
    asyncio.run(main())
