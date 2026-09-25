from __future__ import annotations

import asyncio
import unittest

from core.player import AudioPlayer


class DummyBot:
    def __init__(self) -> None:
        self.loop = asyncio.get_running_loop()

    def get_guild(self, guild_id: int):
        return None


async def announce(_track) -> None:
    return None


class RadioControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_volume_is_bounded_and_mute_preserves_selected_level(self) -> None:
        player = AudioPlayer(DummyBot(), announce)
        guild_id = 55
        self.assertEqual(player.state(guild_id).volume, 0.5)
        self.assertEqual(player.set_volume(guild_id, 0.6), 0.6)
        self.assertTrue(player.toggle_mute(guild_id))
        self.assertEqual(player.state(guild_id).volume, 0.6)
        self.assertFalse(player.toggle_mute(guild_id))
        self.assertEqual(player.set_volume(guild_id, 1.5), 1.0)
        self.assertEqual(player.set_volume(guild_id, -0.4), 0.0)

    async def test_repeat_broadcast_can_be_switched_off(self) -> None:
        player = AudioPlayer(DummyBot(), announce)
        guild_id = 77
        self.assertTrue(player.state(guild_id).repeat_broadcast)
        self.assertFalse(player.toggle_repeat(guild_id))
        self.assertTrue(player.toggle_repeat(guild_id))


if __name__ == "__main__":
    unittest.main()
