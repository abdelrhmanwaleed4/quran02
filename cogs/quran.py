from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from core.embeds import make_embed
from core.player import Track
from core.quran_data import SURAH_BY_NUMBER
from core.quran_service import Reciter
from core.views import RadioPanelView, ReaderBrowser, SurahBrowser


class QuranCog(commands.GroupCog, group_name="quran", group_description="القرآن الكريم والتشغيل الصوتي"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _settings(self, interaction: discord.Interaction) -> dict:
        if not interaction.guild:
            raise ValueError("هذا الأمر متاح داخل السيرفر فقط.")
        return self.bot.db.get_guild_settings(interaction.guild.id)

    async def _reader(self, reciter_id: int, settings: dict, edition_id: str | None = None) -> Reciter | None:
        selected = edition_id or settings.get("default_edition_id")
        return await self.bot.quran_service.find(reciter_id, str(selected) if selected else None)

    @app_commands.command(name="browse", description="اختيار قارئ ثم الرواية أو المصحف ثم سورة")
    @app_commands.describe(search="اسم القارئ أو جزء منه")
    async def browse(self, interaction: discord.Interaction, search: str = "") -> None:
        settings = await self._settings(interaction)
        readers = await self.bot.quran_service.search(search)
        if not readers:
            await interaction.response.send_message("لم أجد قارئاً يطابق البحث.", ephemeral=True)
            return
        edition_list = await self.bot.quran_service.catalogue()
        reader_count = self.bot.quran_service.raw_unique_reader_count
        edition_count = self.bot.quran_service.edition_count
        embed, file = make_embed(
            "📖 قائمة قرّاء رحمة",
            f"**{reader_count} قارئاً** • **{edition_count} مصحفاً وروايةً**\n"
            f"{'نتائج البحث: ' + search if search else 'القائمة مرتبة أبجدياً.'}\n"
            "اختر القارئ ثم المصحف/الرواية لعرض السور المتاحة.",
            theme="quran",
            settings=settings,
        )
        await interaction.response.send_message(
            embed=embed,
            file=file,
            view=ReaderBrowser(
                interaction.user.id,
                readers,
                settings,
                self,
                search_query=search,
                all_editions=edition_list,
            ),
        )

    @app_commands.command(name="play", description="تشغيل سورة برقمها ومعرّف القارئ والمصحف")
    @app_commands.describe(surah="رقم السورة من 1 إلى 114", reciter_id="معرّف القارئ", edition_id="معرّف المصحف (اختياري؛ الافتراضي من الإعدادات)")
    async def play(
        self,
        interaction: discord.Interaction,
        surah: app_commands.Range[int, 1, 114],
        reciter_id: int,
        edition_id: str | None = None,
    ) -> None:
        settings = await self._settings(interaction)
        reader = await self._reader(reciter_id, settings, edition_id)
        if not reader:
            await interaction.response.send_message("لم أجد القارئ أو المصحف. افتح `/quran browse` للاختيار.", ephemeral=True)
            return
        await self._queue(interaction, reader, surah, settings)

    @app_commands.command(name="full", description="إضافة المصحف الكامل للقارئ المختار إلى قائمة التشغيل")
    @app_commands.describe(reciter_id="معرّف القارئ", edition_id="معرّف المصحف (اختياري؛ الافتراضي من الإعدادات)")
    async def full(self, interaction: discord.Interaction, reciter_id: int, edition_id: str | None = None) -> None:
        settings = await self._settings(interaction)
        reader = await self._reader(reciter_id, settings, edition_id)
        if not reader:
            await interaction.response.send_message("لم أجد القارئ أو المصحف المختار.", ephemeral=True)
            return
        voice_channel = self._member_voice_channel(interaction)
        tracks = [
            Track(reader, surah, interaction.user.mention, interaction.channel_id)
            for surah in range(1, 115)
            if surah in reader.surahs
        ]
        if not tracks:
            await interaction.response.send_message("لا توجد سورة متاحة في هذا المصحف.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        await self.bot.audio_player.enqueue(interaction.guild, voice_channel, tracks)
        embed, file = make_embed(
            "📖 تمت إضافة الختمة",
            f"**القارئ:** {reader.name}\n**المصحف:** {reader.moshaf_name}\n"
            f"أضيفت **{len(tracks)}** سورة إلى قائمة التشغيل. سيغادر البوت تلقائياً إذا خلا الروم الصوتي.",
            theme="quran",
            settings=settings,
        )
        await interaction.followup.send(embed=embed, file=file)

    @app_commands.command(name="radio", description="بدء إذاعة ختمة كاملة مستمرة للقارئ والمصحف المختارين")
    @app_commands.describe(reciter_id="معرّف قارئ يوفّر جميع السور الـ114", edition_id="معرّف مصحف يدعم ختمة كاملة")
    async def radio(self, interaction: discord.Interaction, reciter_id: int, edition_id: str | None = None) -> None:
        settings = await self._settings(interaction)
        reader = await self._reader(reciter_id, settings, edition_id)
        if not reader:
            await interaction.response.send_message("لم أجد القارئ أو المصحف المختار.", ephemeral=True)
            return
        if not all(number in reader.surahs for number in range(1, 115)):
            await interaction.response.send_message("هذا المصحف لا يوفّر ختمة كاملة؛ اختر مصحفاً آخر.", ephemeral=True)
            return
        voice_channel = self._member_voice_channel(interaction)
        await interaction.response.defer(thinking=True)
        tracks = [Track(reader, surah, interaction.user.mention, 0) for surah in range(1, 115)]
        await self.bot.audio_player.stop(interaction.guild.id)
        await self.bot.audio_player.enqueue(interaction.guild, voice_channel, tracks, broadcast=True)
        state = self.bot.audio_player.state(interaction.guild.id)
        current = state.now_playing
        description = (
            f"**القارئ:** {reader.name}\n**المصحف:** {reader.moshaf_name}\n"
            f"**الروم:** {voice_channel.mention}\n"
            f"**الحالة:** {'▶️ ' + SURAH_BY_NUMBER[current.surah] if current else 'جارٍ الاتصال'}\n"
            f"**مستوى الصوت:** {int(state.volume * 100)}%\n\n"
            "استخدم الأزرار للتحكم بالصوت والإيقاف المؤقت والتخطي والتكرار أو إيقاف الإذاعة. "
            "لوحة التحكم تعمل فقط لمن هو داخل الروم الصوتي نفسه."
        )
        embed, file = make_embed("📡 إذاعة القرآن — بث مستمر", description, theme="quran", source="MP3Quran (بث مباشر)", settings=settings)
        await interaction.followup.send(embed=embed, file=file, view=RadioPanelView(self.bot, interaction.guild.id))

    @app_commands.command(name="controls", description="نشر لوحة تحكم الإذاعة في هذه القناة")
    async def controls(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        state = self.bot.audio_player.state(interaction.guild.id)
        if not state.broadcast_tracks:
            await interaction.response.send_message("لا توجد إذاعة مستمرة حالياً. استخدم `/quran radio` لبدئها.", ephemeral=True)
            return
        current = state.now_playing
        description = (
            f"**الآن:** {SURAH_BY_NUMBER[current.surah]} — {current.reciter.name}\n"
            f"**المصحف:** {current.reciter.moshaf_name}\n"
            f"**مستوى الصوت:** {int(state.volume * 100)}%\n"
            "ادخل الروم الصوتي الذي فيه البوت للتحكم."
        ) if current else "الإذاعة متصلة. ادخل الروم الصوتي للتحكم."
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        embed, file = make_embed("📡 إذاعة القرآن — لوحة التحكم", description, theme="quran", settings=settings)
        await interaction.response.send_message(embed=embed, file=file, view=RadioPanelView(self.bot, interaction.guild.id))

    @app_commands.command(name="pause", description="إيقاف التلاوة مؤقتاً")
    async def pause(self, interaction: discord.Interaction) -> None:
        await self._control(interaction, "تم الإيقاف المؤقت.", self.bot.audio_player.pause)

    @app_commands.command(name="resume", description="استئناف التلاوة")
    async def resume(self, interaction: discord.Interaction) -> None:
        await self._control(interaction, "تم استئناف التلاوة.", self.bot.audio_player.resume)

    @app_commands.command(name="skip", description="تجاوز السورة الحالية")
    async def skip(self, interaction: discord.Interaction) -> None:
        await self._control(interaction, "تم تجاوز السورة الحالية.", self.bot.audio_player.skip)

    @app_commands.command(name="stop", description="إيقاف التلاوة ومسح القائمة")
    async def stop(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        await self.bot.audio_player.stop(interaction.guild.id)
        settings = await self._settings(interaction)
        embed, file = make_embed("📖 تم الإيقاف", "تم مسح قائمة التشغيل ومغادرة الروم الصوتي.", theme="quran", settings=settings)
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="queue", description="عرض قائمة تشغيل القرآن")
    async def queue(self, interaction: discord.Interaction) -> None:
        settings = await self._settings(interaction)
        lines = self.bot.audio_player.queue_lines(interaction.guild.id if interaction.guild else 0)
        embed, file = make_embed("📖 قائمة التشغيل", "\n".join(lines) if lines else "قائمة التشغيل فارغة.", theme="quran", settings=settings)
        await interaction.response.send_message(embed=embed, file=file)

    async def queue_selected_surah(self, interaction: discord.Interaction, reader: Reciter, surah: int) -> None:
        settings = await self._settings(interaction)
        await self._queue(interaction, reader, surah, settings, edit_response=True)

    async def _queue(self, interaction: discord.Interaction, reader: Reciter, surah: int, settings: dict, edit_response: bool = False) -> None:
        voice_channel = self._member_voice_channel(interaction)
        if surah not in reader.surahs:
            raise ValueError("هذه السورة غير متاحة في مصحف القارئ المختار.")
        track = Track(reader, surah, interaction.user.mention, interaction.channel_id)
        if not edit_response:
            await interaction.response.defer(thinking=True)
        await self.bot.audio_player.enqueue(interaction.guild, voice_channel, [track])
        embed, file = make_embed(
            f"📖 {SURAH_BY_NUMBER[surah]}",
            f"**القارئ:** {reader.name}\n**المصحف:** {reader.moshaf_name}\n**الحالة:** أُضيفت للتشغيل في {voice_channel.mention}.",
            theme="quran", source="MP3Quran (بث مباشر)", settings=settings,
        )
        if edit_response:
            await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=None)
        else:
            await interaction.followup.send(embed=embed, file=file)

    def _member_voice_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | discord.StageChannel:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise ValueError("هذا الأمر متاح داخل السيرفر فقط.")
        voice = interaction.user.voice
        if not voice or not voice.channel or not isinstance(voice.channel, (discord.VoiceChannel, discord.StageChannel)):
            raise ValueError("ادخل روم صوتي أولاً ثم أعد المحاولة.")
        return voice.channel

    async def _control(self, interaction: discord.Interaction, success: str, action: object) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        changed = await action(interaction.guild.id)  # type: ignore[misc]
        if not changed:
            await interaction.response.send_message("لا توجد تلاوة يمكن التحكم بها الآن.", ephemeral=True)
            return
        settings = await self._settings(interaction)
        embed, file = make_embed("📖 مشغل القرآن", success, theme="quran", settings=settings)
        await interaction.response.send_message(embed=embed, file=file)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuranCog(bot))
