from __future__ import annotations

import json
import time
import unittest
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from core.dashboard_api import DashboardApi, make_nonce, sign_request
from core.database import DEFAULT_GUILD_SETTINGS

SECRET = "test-only-dashboard-key-with-at-least-32-bytes"


class MemoryDatabase:
    def __init__(self) -> None:
        self.settings = DEFAULT_GUILD_SETTINGS.copy()

    def get_guild_settings(self, guild_id: int):
        return self.settings.copy()

    def apply_guild_settings_patch(self, guild_id: int, **updates):
        self.settings.update(updates)
        return self.settings.copy()


class FakeBot:
    def __init__(self) -> None:
        self.guild = SimpleNamespace(id=123)
        self.db = MemoryDatabase()
        self.quran_service = SimpleNamespace(raw_unique_reader_count=242)
        self.audio_player = SimpleNamespace()

    def get_guild(self, guild_id: int):
        return self.guild if guild_id == 123 else None


class DashboardSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.bot = FakeBot()
        self.api = DashboardApi(self.bot, SECRET)
        self.client = TestClient(TestServer(self.api.app))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    def signed_headers(self, path: str, body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        nonce = make_nonce()
        actor = "987654321"
        return {
            "Content-Type": "application/json",
            "X-Rahma-Timestamp": timestamp,
            "X-Rahma-Nonce": nonce,
            "X-Rahma-Actor": actor,
            "X-Rahma-Signature": sign_request(SECRET, "PATCH", path, body, actor, timestamp, nonce),
        }

    def test_safe_settings_keep_times_and_use_string_ids(self) -> None:
        values = {
            **DEFAULT_GUILD_SETTINGS,
            "prayer_channel_id": 101,
            "daily_channel_id": 202,
            "quran_voice_channel_id": 303,
        }
        result = DashboardApi._safe_settings(values)
        self.assertEqual(result["prayer_channel_id"], "101")
        self.assertEqual(result["daily_channel_id"], "202")
        self.assertEqual(result["quran_voice_channel_id"], "303")
        self.assertEqual(result["daily_content_time"], "08:00")
        self.assertEqual(result["friday_reminder_time"], "09:00")

    async def test_daily_reminder_settings_save_without_prayer_location(self) -> None:
        path = "/api/dashboard/guilds/123/settings"
        body = json.dumps({
            "daily_content_enabled": True,
            "daily_content_time": "07:15",
            "friday_reminder": True,
            "friday_reminder_time": "10:20",
        }, separators=(",", ":")).encode()
        response = await self.client.patch(path, data=body, headers=self.signed_headers(path, body))
        self.assertEqual(response.status, 200, await response.text())
        returned = await response.json()
        self.assertEqual(returned["settings"]["daily_content_time"], "07:15")
        self.assertEqual(returned["settings"]["friday_reminder_time"], "10:20")
        self.assertEqual(self.bot.db.settings["city"], "")

    async def test_invalid_local_time_is_rejected(self) -> None:
        path = "/api/dashboard/guilds/123/settings"
        body = json.dumps({"daily_content_time": "25:99"}, separators=(",", ":")).encode()
        response = await self.client.patch(path, data=body, headers=self.signed_headers(path, body))
        self.assertEqual(response.status, 400)
        self.assertEqual(self.bot.db.settings["daily_content_time"], "08:00")


if __name__ == "__main__":
    unittest.main()
