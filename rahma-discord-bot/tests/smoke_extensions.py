from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import sys

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import EXTENSIONS, RahmaBot
from core.config import Settings
from core.player import AudioPlayer
from core.prayer_service import PrayerService
from core.quran_service import QuranService
from core.views import RadioPanelView


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = Settings(
            discord_token="not-used-in-smoke-test",
            database_path=Path(directory) / "rahma.sqlite3",
            mp3quran_api_url="https://www.mp3quran.net/api/v3/reciters?language=ar",
            aladhan_api_url="https://api.aladhan.com/v1",
            log_level="WARNING",
            owner_id=None,
            sync_guild_id=None,
            dashboard_shared_secret=None,
            dashboard_api_host="127.0.0.1",
            dashboard_api_port=8787,
            dashboard_api_allow_origins="",
        )
        bot = RahmaBot(settings)
        bot.disable_background_tasks = True
        bot.db.initialize()
        bot.http_session = aiohttp.ClientSession()
        bot.quran_service = QuranService(bot.http_session, settings.mp3quran_api_url)
        bot.prayer_service = PrayerService(bot.http_session, settings.aladhan_api_url)
        bot.audio_player = AudioPlayer(bot, lambda _: asyncio.sleep(0))
        for extension in EXTENSIONS:
            await bot.load_extension(extension)
        commands = {command.name for command in bot.tree.get_commands()}
        assert {"quran", "azkar", "dua", "prayer", "setup"}.issubset(commands), commands
        quran_group = next(command for command in bot.tree.get_commands() if command.name == "quran")
        assert {"radio", "controls", "browse", "play"}.issubset({command.name for command in quran_group.commands})
        bot.add_view(RadioPanelView(bot))
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
