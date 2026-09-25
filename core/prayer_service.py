from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp


PRAYER_KEYS = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha")
ARABIC_PRAYER_NAMES = {
    "Fajr": "الفجر",
    "Sunrise": "الشروق",
    "Dhuhr": "الظهر",
    "Asr": "العصر",
    "Maghrib": "المغرب",
    "Isha": "العشاء",
}
METHOD_NAMES = {
    1: "جامعة العلوم الإسلامية، كراتشي",
    2: "الجمعية الإسلامية لأمريكا الشمالية",
    3: "رابطة العالم الإسلامي",
    4: "أم القرى، مكة المكرمة",
    5: "الهيئة المصرية العامة للمساحة",
    8: "الهيئة العامة للمساحة، الخليج",
    13: "رئاسة الشؤون الدينية، تركيا",
}


@dataclass(frozen=True, slots=True)
class PrayerDay:
    timings: dict[str, str]
    hijri_date: str
    hijri_month_number: int
    hijri_month_name: str
    hijri_year: str
    gregorian_date: str
    method_name: str

    def next_prayer(self, now: datetime) -> tuple[str, str] | None:
        for prayer in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"):
            hour, minute = map(int, self.timings[prayer].split(":"))
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate > now:
                return prayer, self.timings[prayer]
        return None


class PrayerService:
    def __init__(self, session: aiohttp.ClientSession, api_base: str) -> None:
        self.session = session
        self.api_base = api_base
        self._cache: dict[tuple[str, str, str, int, int], tuple[datetime, PrayerDay]] = {}

    async def today(self, settings: dict[str, Any], now: datetime | None = None) -> PrayerDay:
        city = str(settings.get("city", "")).strip()
        country = str(settings.get("country", "")).strip()
        zone_name = str(settings.get("timezone", "UTC")).strip()
        if not city or not country:
            raise ValueError("لم يضبط المسؤول المدينة والدولة بعد. استخدم /setup prayer أولاً.")
        zone = ZoneInfo(zone_name)
        local_now = now.astimezone(zone) if now else datetime.now(zone)
        method = int(settings.get("calculation_method", 5))
        school = int(settings.get("asr_school", 0))
        cache_key = (city.casefold(), country.casefold(), local_now.date().isoformat(), method, school)
        cached = self._cache.get(cache_key)
        if cached and cached[0] > datetime.now():
            return cached[1]

        params = {
            "city": city,
            "country": country,
            "method": method,
            "school": school,
            "iso8601": "false",
        }
        timeout = aiohttp.ClientTimeout(total=20)
        date_path = local_now.strftime("%d-%m-%Y")
        async with self.session.get(f"{self.api_base}/timingsByCity/{date_path}", params=params, timeout=timeout) as response:
            response.raise_for_status()
            payload: dict[str, Any] = await response.json(content_type=None)
        if int(payload.get("code", 0)) != 200:
            raise RuntimeError("تعذر الحصول على مواقيت الصلاة من المزود.")

        data = payload["data"]
        raw_timings = data["timings"]
        timings = {key: self._normalise_time(str(raw_timings[key])) for key in PRAYER_KEYS}
        hijri = data["date"]["hijri"]
        metadata = data.get("meta", {})
        result = PrayerDay(
            timings=timings,
            hijri_date=str(hijri.get("date", "")),
            hijri_month_number=int(hijri.get("month", {}).get("number", 0)),
            hijri_month_name=str(hijri.get("month", {}).get("ar", "")),
            hijri_year=str(hijri.get("year", "")),
            gregorian_date=str(data["date"].get("gregorian", {}).get("date", "")),
            method_name=METHOD_NAMES.get(
                method,
                str(metadata.get("method", {}).get("name", method)),
            ),
        )
        self._cache[cache_key] = (datetime.now() + timedelta(minutes=25), result)
        return result

    @staticmethod
    def _normalise_time(value: str) -> str:
        return value.split(" ", 1)[0].strip()
