from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from cogs.prayer import DAILY_CONTENT, PrayerCog
from core.database import DEFAULT_GUILD_SETTINGS


class CaptureChannel:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, **kwargs):
        self.messages.append(kwargs)


class CaptureDatabase:
    def __init__(self) -> None:
        self.claimed = []

    def claim_notification(self, guild_id, key, date):
        self.claimed.append((guild_id, key, date))
        return True


class DailyImageTests(unittest.IsolatedAsyncioTestCase):
    async def test_daily_items_are_one_image_with_complete_source_equivalent(self) -> None:
        channel = CaptureChannel()
        bot = SimpleNamespace(db=CaptureDatabase(), get_channel=lambda channel_id: channel)
        cog = SimpleNamespace(bot=bot)
        settings = {**DEFAULT_GUILD_SETTINGS, "daily_channel_id": 99, "text_equivalent_enabled": True}
        now = datetime(2026, 9, 22, 8, 0)  # Tuesday, avoiding the separate Friday notice.

        with patch("cogs.prayer.discord.TextChannel", CaptureChannel), patch(
            "cogs.prayer.render_content_poster",
            wraps=__import__("core.content_card", fromlist=["render_content_poster"]).render_content_poster,
        ) as render:
            await PrayerCog._send_daily_content(cog, 123, settings, now)

        self.assertEqual(len(channel.messages), 1)
        message = channel.messages[0]
        self.assertEqual(message["file"].filename, "rahma-daily-reminder.png")
        self.assertEqual(render.call_count, 1)
        args, _ = render.call_args
        self.assertEqual(args[0], "محتوى رحمة اليوم")
        self.assertEqual(args[1], [(title, text, source) for title, text, source, _ in DAILY_CONTENT])
        self.assertTrue(message["embed"].description)
        self.assertIn("المصدر:", message["embed"].description)

    async def test_does_not_post_before_configured_local_time(self) -> None:
        channel = CaptureChannel()
        bot = SimpleNamespace(db=CaptureDatabase(), get_channel=lambda channel_id: channel)
        settings = {**DEFAULT_GUILD_SETTINGS, "daily_channel_id": 99, "daily_content_time": "09:00"}
        with patch("cogs.prayer.discord.TextChannel", CaptureChannel):
            await PrayerCog._send_daily_content(SimpleNamespace(bot=bot), 123, settings, datetime(2026, 9, 22, 8, 59))
        self.assertEqual(channel.messages, [])


if __name__ == "__main__":
    unittest.main()
