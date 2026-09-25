from __future__ import annotations

import unittest

from core.quran_service import Reciter
from core.views import ReaderBrowser, ReaderSelect


class ReaderBrowserTests(unittest.TestCase):
    def test_all_readers_are_paginated_without_truncation(self) -> None:
        readers = [
            Reciter(index, f"قارئ {index}", "حفص", "https://example.test/audio", frozenset({1, 114}))
            for index in range(1, 243)
        ]
        browser = ReaderBrowser(10, readers, {}, cog=object())

        self.assertEqual(browser.page_count, 10)
        self.assertEqual(len(browser.readers), 242)
        first_select = browser.children[0]
        self.assertIsInstance(first_select, ReaderSelect)
        self.assertEqual(len(first_select.options), 25)

        browser.page = browser.page_count - 1
        browser._rebuild()
        last_select = browser.children[0]
        self.assertEqual(len(last_select.options), 17)
        self.assertEqual(last_select.options[-1].value, "242")


if __name__ == "__main__":
    unittest.main()
