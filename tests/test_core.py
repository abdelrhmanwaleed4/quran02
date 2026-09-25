from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.database import Database
from core.prayer_service import PrayerService
from core.quran_data import SURAH_BY_NUMBER
from core.quran_service import Reciter


class DatabaseTests(unittest.TestCase):
    def test_settings_round_trip_and_notification_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Path(directory) / "rahma.sqlite3")
            database.initialize()
            saved = database.update_guild_settings(123, city="Cairo", prayer_channel_id=456)
            self.assertEqual(saved["city"], "Cairo")
            self.assertEqual(database.get_guild_settings(123)["prayer_channel_id"], 456)
            self.assertTrue(database.claim_notification(123, "prayer:Fajr", "2026-09-25"))
            self.assertFalse(database.claim_notification(123, "prayer:Fajr", "2026-09-25"))
            database.close()


class QuranDataTests(unittest.TestCase):
    def test_all_114_surahs_are_present(self) -> None:
        self.assertEqual(len(SURAH_BY_NUMBER), 114)
        self.assertEqual(SURAH_BY_NUMBER[1], "الفاتحة")
        self.assertEqual(SURAH_BY_NUMBER[114], "الناس")

    def test_stream_url_is_zero_padded_and_https(self) -> None:
        reader = Reciter(1, "قارئ", "حفص", "https://example.test/audio/", frozenset({1, 114}))
        self.assertEqual(reader.stream_url(1), "https://example.test/audio/001.mp3")
        self.assertEqual(reader.stream_url(114), "https://example.test/audio/114.mp3")
        with self.assertRaises(ValueError):
            reader.stream_url(2)


class PrayerParsingTests(unittest.TestCase):
    def test_api_time_normalisation_removes_timezone_suffix(self) -> None:
        self.assertEqual(PrayerService._normalise_time("05:21 (EET)"), "05:21")


if __name__ == "__main__":
    unittest.main()
