from __future__ import annotations

import unittest

from PIL import Image

from core.content_card import WIDTH, render_content_poster


class ContentCardTests(unittest.TestCase):
    def test_card_grows_to_fit_full_long_text_and_reference(self) -> None:
        text = "اللهم " + ("اغفر لي وارحمني واهدني وعافني وارزقني. " * 20)
        source = "صحيح مسلم، كتاب الذكر والدعاء، رقم 2697"
        stream = render_content_poster("دعاء طويل للاختبار", [("دعاء مأثور", text, source)])
        image = Image.open(stream)
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.width, WIDTH)
        self.assertGreater(image.height, 760)
        self.assertGreater(len(stream.getvalue()), 15_000)


if __name__ == "__main__":
    unittest.main()
