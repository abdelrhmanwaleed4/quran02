from __future__ import annotations

import unittest

from PIL import Image

from core.prayer_card import HEIGHT, WIDTH, render_prayer_alert, render_prayer_card
from core.prayer_service import PrayerDay


class PrayerCardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.day = PrayerDay(
            timings={
                "Fajr": "04:37",
                "Sunrise": "06:01",
                "Dhuhr": "12:02",
                "Asr": "15:28",
                "Maghrib": "18:04",
                "Isha": "19:19",
            },
            hijri_date="14-04-1448",
            hijri_month_number=4,
            hijri_month_name="ربيع الآخر",
            hijri_year="1448",
            gregorian_date="25-09-2026",
            method_name="الهيئة المصرية العامة للمساحة",
        )

    def test_renderer_produces_landscape_png_with_exact_source_times(self) -> None:
        stream = render_prayer_card(self.day, "القاهرة", "مصر", highlight_prayer="Asr")
        image = Image.open(stream)
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (WIDTH, HEIGHT))
        self.assertGreater(len(stream.getvalue()), 20_000)

    def test_prayer_alert_is_a_compact_png(self) -> None:
        stream = render_prayer_alert("المغرب", "18:04", "القاهرة", "مصر")
        image = Image.open(stream)
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (1600, 720))
        self.assertGreater(len(stream.getvalue()), 15_000)


if __name__ == "__main__":
    unittest.main()
