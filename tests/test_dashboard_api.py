from __future__ import annotations

from types import SimpleNamespace
import time
import unittest

from aiohttp.test_utils import TestClient, TestServer

from core.dashboard_api import DashboardApi, make_nonce, sign_request


SECRET = "test-only-shared-secret-that-is-at-least-32-bytes-long"


class FakeQuranService:
    raw_unique_reader_count = 242

    async def catalogue(self):
        return []


class FakeBot:
    def __init__(self) -> None:
        self.guilds = [SimpleNamespace(id=123, name="Test Server", icon=None, member_count=3, owner_id=456)]
        self.quran_service = FakeQuranService()

    def is_ready(self) -> bool:
        return True

    def get_guild(self, guild_id: int):
        return next((guild for guild in self.guilds if guild.id == guild_id), None)


class DashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.api = DashboardApi(FakeBot(), SECRET)
        self.client = TestClient(TestServer(self.api.app))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()

    def headers(self, path: str, *, body: bytes = b"", method: str = "GET", nonce: str | None = None) -> dict[str, str]:
        timestamp = str(int(time.time()))
        request_nonce = nonce or make_nonce()
        actor = "12345"
        return {
            "X-Rahma-Timestamp": timestamp,
            "X-Rahma-Nonce": request_nonce,
            "X-Rahma-Actor": actor,
            "X-Rahma-Signature": sign_request(SECRET, method, path, body, actor, timestamp, request_nonce),
        }

    async def test_rejects_unsigned_requests(self) -> None:
        response = await self.client.get("/api/dashboard/health")
        self.assertEqual(response.status, 401)

    async def test_signed_health_and_guild_list(self) -> None:
        health_path = "/api/dashboard/health"
        response = await self.client.get(health_path, headers=self.headers(health_path))
        self.assertEqual(response.status, 200)
        health = await response.json()
        self.assertTrue(health["ok"])
        self.assertEqual(health["bot_name"], "رحمة")
        self.assertEqual(health["reciter_count"], 242)

        guild_path = "/api/dashboard/guilds"
        response = await self.client.get(guild_path, headers=self.headers(guild_path))
        self.assertEqual(response.status, 200)
        guilds = await response.json()
        self.assertEqual(guilds["guilds"][0]["name"], "Test Server")

    async def test_rejects_a_replayed_nonce(self) -> None:
        path = "/api/dashboard/health"
        headers = self.headers(path, nonce="replay_nonce_abcdefghijklmnop")
        first = await self.client.get(path, headers=headers)
        second = await self.client.get(path, headers=headers)
        self.assertEqual(first.status, 200)
        self.assertEqual(second.status, 401)

    async def test_signature_is_bound_to_raw_path(self) -> None:
        original = "/api/dashboard/health"
        headers = self.headers(original)
        response = await self.client.get("/api/dashboard/health?other=1", headers=headers)
        self.assertEqual(response.status, 401)

    async def test_signature_is_bound_to_body(self) -> None:
        path = "/api/dashboard/guilds/123/preview"
        headers = self.headers(path, body=b'{"kind":"daily"}', method="POST")
        response = await self.client.post(path, data=b'{"kind":"friday"}', headers=headers)
        self.assertEqual(response.status, 401)


if __name__ == "__main__":
    unittest.main()
