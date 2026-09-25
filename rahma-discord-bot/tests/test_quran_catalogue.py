from __future__ import annotations

from urllib.parse import parse_qs, urlparse
import unittest

from core.quran_service import QuranService


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    async def json(self, **_kwargs):
        return self.payload


class FakeSession:
    def get(self, url, **_kwargs):
        language = parse_qs(urlparse(url).query)["language"][0]
        if language == "ar":
            payload = {
                "reciters": [
                    {"id": 9, "name": "عبد الباسط", "moshaf": [
                        {"name": "حفص عن عاصم", "server": "https://audio.example/hafs", "surah_list": "1,2,114"},
                        {"name": "ورشة عن نافع", "server": "https://audio.example/warsh", "surah_list": "1,2,114"},
                    ]},
                ],
            }
        else:
            payload = {
                "reciters": [
                    {"id": 9, "name": "Abdulbasit Abdulsamad", "moshaf": [
                        {"name": "Hafs", "server": "https://audio.example/hafs", "surah_list": "1,2,114"},
                    ]},
                    {"id": 10, "name": "English Reader", "moshaf": [
                        {"name": "Hafs", "server": "https://audio.example/other", "surah_list": "1,114"},
                    ]},
                ],
            }
        return FakeResponse(payload)


class QuranCatalogueTests(unittest.IsolatedAsyncioTestCase):
    async def test_merges_languages_without_duplicate_readers_and_keeps_all_editions(self):
        service = QuranService(FakeSession(), "https://api.example/reciters?language=ar")
        catalogue = await service.catalogue(force_refresh=True)
        self.assertEqual(service.raw_unique_reader_count, 2)
        self.assertEqual(len(catalogue), 3)
        reader_nine = await service.editions_for(9)
        self.assertEqual(len(reader_nine), 2)
        self.assertTrue(all(item.name == "عبد الباسط" for item in reader_nine))
        self.assertEqual(len({item.edition_id for item in reader_nine}), 2)
        default_reader = await service.find(9)
        self.assertIsNotNone(default_reader)
        selected = await service.find(9, reader_nine[1].edition_id)
        self.assertEqual(selected.edition_id, reader_nine[1].edition_id)

    async def test_search_is_one_row_per_reciter(self):
        service = QuranService(FakeSession(), "https://api.example/reciters?language=ar")
        matches = await service.search("عبد الباسط")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, 9)
        self.assertEqual(service.edition_count, 3)


if __name__ == "__main__":
    unittest.main()
