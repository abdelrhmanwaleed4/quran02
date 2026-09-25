from __future__ import annotations

import asyncio
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from core.config import Settings, load_settings
from core.dashboard_api import make_dashboard_api
from core.database import Database
from core.embeds import make_embed
from core.player import AudioPlayer, Track
from core.quran_data import SURAH_BY_NUMBER
from core.quran_service import QuranService
from core.prayer_service import PrayerService
from core.views import RadioPanelView

EXTENSIONS = ("cogs.quran", "cogs.azkar", "cogs.duas", "cogs.prayer", "cogs.admin")


class RahmaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.settings = settings
        self.db = Database(settings.database_path)
        self.http_session: aiohttp.ClientSession | None = None
        self.quran_service: QuranService
        self.prayer_service: PrayerService
        self.audio_player: AudioPlayer
        self.dashboard_api = None
        self._synced = False
        self._broadcasts_started = False

    async def setup_hook(self) -> None:
        self.db.initialize()
        self.http_session = aiohttp.ClientSession(headers={"User-Agent": "RahmaDiscordBot/1.0"})
        self.quran_service = QuranService(self.http_session, self.settings.mp3quran_api_url)
        self.prayer_service = PrayerService(self.http_session, self.settings.aladhan_api_url)
        self.audio_player = AudioPlayer(self, self.announce_track)
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        self.add_view(RadioPanelView(self))

        if self.settings.sync_guild_id:
            guild = discord.Object(id=self.settings.sync_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info("Synced commands to test guild %s", self.settings.sync_guild_id)
        else:
            await self.tree.sync()
            logging.info("Synced global application commands")
        self._synced = True
        if self.settings.dashboard_shared_secret:
            self.dashboard_api = make_dashboard_api(
                self,
                self.settings.dashboard_shared_secret,
                self.settings.dashboard_api_allow_origins,
            )
            await self.dashboard_api.start(
                self.settings.dashboard_api_host,
                self.settings.dashboard_api_port,
            )
        else:
            logging.info("Dashboard API disabled; set DASHBOARD_SHARED_SECRET to enable it.")

    async def close(self) -> None:
        if self.dashboard_api:
            await self.dashboard_api.close()
        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
        self.db.close()
        await super().close()

    async def announce_track(self, track: Track) -> None:
        channel = self.get_channel(track.text_channel_id)
        guild = getattr(channel, "guild", None)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)) or guild is None:
            return
        settings = self.db.get_guild_settings(guild.id)
        embed, file = make_embed(
            f"📖 {SURAH_BY_NUMBER[track.surah]}",
            f"**القارئ:** {track.reciter.name}\n**الحالة:** ▶️ جاري التشغيل الآن\n**بطلب:** {track.requested_by}",
            theme="quran",
            source="MP3Quran (بث مباشر)",
            settings=settings,
        )
        try:
            await channel.send(embed=embed, file=file)
        except discord.HTTPException as error:
            logging.warning("Could not post playback announcement: %s", error)

    async def on_ready(self) -> None:
        logging.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        if not self._broadcasts_started:
            self._broadcasts_started = True
            for guild_id, settings in self.db.iter_configured_guilds():
                if not settings.get("quran_auto_play"):
                    continue
                guild = self.get_guild(guild_id)
                if guild:
                    await self.start_guild_broadcast(guild, settings)

    async def start_guild_broadcast(self, guild: discord.Guild, settings: dict | None = None) -> tuple[bool, str]:
        """Start the configured full-khatmah radio; silence per-surah announcements."""
        settings = settings or self.db.get_guild_settings(guild.id)
        channel_id = settings.get("quran_voice_channel_id")
        reciter_id = settings.get("default_reciter_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return False, "لم يتم ضبط روم صوتي صالح للإذاعة."
        if not reciter_id:
            return False, "اختر القارئ الافتراضي للإذاعة أولاً."
        edition_id = settings.get("default_edition_id")
        reader = await self.quran_service.find(int(reciter_id), str(edition_id) if edition_id else None)
        if not reader:
            return False, "القارئ الافتراضي لم يعد متاحاً لدى المزود."
        tracks = [Track(reader, number, "إذاعة القرآن", 0) for number in range(1, 115) if number in reader.surahs]
        if len(tracks) < 114:
            return False, "القارئ الافتراضي لا يوفّر ختمة كاملة منشورة."
        await self.audio_player.enqueue(guild, channel, tracks, broadcast=True)
        logging.info("Started continuous Quran broadcast in guild %s with reciter %s", guild.id, reader.id)
        return True, f"بدأت الإذاعة الدائمة: {reader.name}."

    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot:
            return
        voice = member.guild.voice_client
        if not voice or not voice.channel:
            return
        if before.channel != voice.channel and after.channel != voice.channel:
            return
        non_bot_members = [user for user in voice.channel.members if not user.bot]
        if non_bot_members:
            self.audio_player.cancel_scheduled_leave(member.guild.id)
        else:
            self.audio_player.schedule_leave_if_empty(member.guild.id)


async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    original = getattr(error, "original", error)
    if isinstance(original, ValueError):
        message = str(original)
    elif isinstance(error, app_commands.MissingPermissions):
        message = "هذا الأمر مخصص للمسؤولين في السيرفر."
    elif isinstance(error, app_commands.CheckFailure):
        message = "لا تملك صلاحية استخدام هذا الأمر."
    else:
        logging.exception("Unhandled application command error", exc_info=error)
        message = "حدث خطأ غير متوقع. تحقق من الإعدادات والصلاحيات ثم أعد المحاولة."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def main() -> None:
    settings = load_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    bot = RahmaBot(settings)
    bot.tree.on_error = on_app_command_error
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    main()
