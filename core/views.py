from __future__ import annotations

from typing import Any

import discord

from core.embeds import make_embed
from core.content_card import image_card_embed, render_content_poster
from core.quran_data import SURAH_NAMES
from core.quran_service import Reciter


def _owner_only(interaction: discord.Interaction, owner_id: int) -> bool:
    return interaction.user.id == owner_id


class AzkarView(discord.ui.View):
    def __init__(self, owner_id: int, label: str, items: list[dict[str, Any]], settings: dict[str, Any]) -> None:
        super().__init__(timeout=900)
        self.owner_id = owner_id
        self.label = label
        self.items = items
        self.index = 0
        self.settings = settings

    def render(self) -> tuple[discord.Embed, discord.File | None]:
        item = self.items[self.index]
        source = f"{item['source']} • يُكرر {item['count']} مرات"
        image = render_content_poster(
            f"{self.label} - الذكر {self.index + 1}/{len(self.items)}",
            [(None, item["text"], source)],
        )
        return image_card_embed(
            f"🤲 {self.label}",
            image,
            "rahma-azkar.png",
            colour=0x1E5C74,
            description=f"{item['text']}\n{source}" if self.settings.get("text_equivalent_enabled") else None,
        )

    @discord.ui.button(label="تم", style=discord.ButtonStyle.success, emoji="✅")
    async def done(self, interaction: discord.Interaction, button: discord.ui.Button["AzkarView"]) -> None:
        if not _owner_only(interaction, self.owner_id):
            await interaction.response.send_message("هذه البطاقة تخص من بدأ الذكر.", ephemeral=True)
            return
        self.index += 1
        if self.index >= len(self.items):
            completion = "أحسنت. تم إكمال الأذكار. تقبل الله منك."
            image = render_content_poster(self.label, [(None, completion, None)])
            embed, file = image_card_embed(
                f"🤲 {self.label}", image, "rahma-azkar-complete.png", colour=0x1E5C74,
                description=completion if self.settings.get("text_equivalent_enabled") else None,
            )
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)
            return
        embed, file = self.render()
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

    @discord.ui.button(label="إنهاء", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button["AzkarView"]) -> None:
        if not _owner_only(interaction, self.owner_id):
            await interaction.response.send_message("هذه البطاقة تخص من بدأ الذكر.", ephemeral=True)
            return
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


class ReaderSelect(discord.ui.Select):
    def __init__(
        self,
        owner_id: int,
        readers: list[Reciter],
        settings: dict[str, Any],
        edition_map: dict[int, list[Reciter]],
        cog: Any,
        page: int,
        page_count: int,
    ) -> None:
        self.owner_id = owner_id
        self.readers = {reader.id: reader for reader in readers}
        self.settings = settings
        self.edition_map = edition_map
        self.cog = cog
        options = [
            discord.SelectOption(
                label=reader.name[:100],
                description=f"{len(reader.surahs)} سورة • {len(edition_map.get(reader.id, [])) or 1} مصحف • ID {reader.id}"[:100],
                value=str(reader.id),
            )
            for reader in readers[:25]
        ]
        super().__init__(placeholder=f"قارئ 🎙️ ({page + 1}/{page_count})", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _owner_only(interaction, self.owner_id):
            await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
            return
        reader_id = int(self.values[0])
        editions = self.edition_map.get(reader_id, [self.readers[reader_id]])
        if len(editions) == 1:
            view = SurahBrowser(self.owner_id, editions[0], self.settings).bind(self.cog)
        else:
            view = EditionBrowser(self.owner_id, editions, self.settings, self.cog)
        embed, file = view.render()
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=view)


class ReaderBrowser(discord.ui.View):
    PAGE_SIZE = 25

    def __init__(
        self,
        owner_id: int,
        readers: list[Reciter],
        settings: dict[str, Any],
        cog: Any,
        search_query: str = "",
        all_editions: list[Reciter] | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.readers = readers
        self.settings = settings
        self.cog = cog
        self.search_query = search_query
        self.page = 0
        self.page_count = max(1, (len(readers) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.edition_map: dict[int, list[Reciter]] = {}
        for edition in all_editions or readers:
            self.edition_map.setdefault(edition.id, []).append(edition)
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        start = self.page * self.PAGE_SIZE
        visible = self.readers[start : start + self.PAGE_SIZE]
        self.add_item(ReaderSelect(self.owner_id, visible, self.settings, self.edition_map, self.cog, self.page, self.page_count))
        previous = discord.ui.Button(label="السابق", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
        next_button = discord.ui.Button(label="التالي", style=discord.ButtonStyle.secondary, disabled=self.page + 1 >= self.page_count)

        async def turn(delta: int, interaction: discord.Interaction) -> None:
            if not _owner_only(interaction, self.owner_id):
                await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
                return
            self.page = max(0, min(self.page + delta, self.page_count - 1))
            self._rebuild()
            embed, file = self.render()
            await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

        async def go_previous(interaction: discord.Interaction) -> None:
            await turn(-1, interaction)

        async def go_next(interaction: discord.Interaction) -> None:
            await turn(1, interaction)

        previous.callback = go_previous
        next_button.callback = go_next
        self.add_item(previous)
        self.add_item(next_button)

    def render(self) -> tuple[discord.Embed, discord.File | None]:
        search_line = f"نتائج البحث عن: {self.search_query}" if self.search_query else "القائمة مرتبة أبجدياً."
        edition_count = len({edition.edition_id for editions in self.edition_map.values() for edition in editions})
        return make_embed(
            "📖 قائمة القرّاء - رحمة",
            f"عدد القرّاء: **{len(self.readers)}**\nالمصاحف المتاحة: **{edition_count}**\nالصفحة **{self.page + 1}/{self.page_count}**\n{search_line}",
            theme="quran",
            settings=self.settings,
        )


class EditionSelect(discord.ui.Select):
    def __init__(self, browser: "EditionBrowser") -> None:
        self.browser = browser
        start = browser.page * browser.PAGE_SIZE
        visible = browser.editions[start : start + browser.PAGE_SIZE]
        options = [
            discord.SelectOption(
                label=edition.moshaf_name[:100],
                description=f"{len(edition.surahs)}/114 سورة" + (" • ختمة كاملة" if len(edition.surahs) == 114 else ""),
                value=edition.edition_id,
            )
            for edition in visible
        ]
        super().__init__(placeholder=f"اختر الرواية أو المصحف ({browser.page + 1}/{browser.page_count})", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _owner_only(interaction, self.browser.owner_id):
            await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
            return
        edition_id = self.values[0]
        edition = next(item for item in self.browser.editions if item.edition_id == edition_id)
        view = SurahBrowser(self.browser.owner_id, edition, self.browser.settings).bind(self.browser.cog)
        embed, file = view.render()
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=view)


class EditionBrowser(discord.ui.View):
    PAGE_SIZE = 25

    def __init__(self, owner_id: int, editions: list[Reciter], settings: dict[str, Any], cog: Any) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.editions = editions
        self.settings = settings
        self.cog = cog
        self.page = 0
        self.page_count = max(1, (len(editions) + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        self.add_item(EditionSelect(self))
        previous = discord.ui.Button(label="السابق", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
        next_button = discord.ui.Button(label="التالي", style=discord.ButtonStyle.secondary, disabled=self.page + 1 >= self.page_count)

        async def turn(delta: int, interaction: discord.Interaction) -> None:
            if not _owner_only(interaction, self.owner_id):
                await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
                return
            self.page = max(0, min(self.page + delta, self.page_count - 1))
            self._rebuild()
            embed, file = self.render()
            await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

        previous.callback = lambda interaction: turn(-1, interaction)
        next_button.callback = lambda interaction: turn(1, interaction)
        self.add_item(previous)
        self.add_item(next_button)

    def render(self) -> tuple[discord.Embed, discord.File | None]:
        reader = self.editions[0]
        return make_embed(
            f"🎙️ {reader.name} — اختر المصحف",
            f"يتوفر لهذا القارئ **{len(self.editions)}** مصحف/رواية. اختر أحدها لعرض السور المتاحة.",
            theme="quran",
            settings=self.settings,
        )


class SurahSelect(discord.ui.Select):
    def __init__(self, browser: "SurahBrowser") -> None:
        self.browser = browser
        start = browser.page * 25
        options = [
            discord.SelectOption(label=f"{number}. {name}", value=str(number))
            for number, name in list(SURAH_NAMES)[start : start + 25]
            if number in browser.reader.surahs
        ]
        if not options:
            options = [discord.SelectOption(label="لا توجد سور متاحة في هذه الصفحة", value="0")]
        super().__init__(placeholder="اختر السورة 📖", options=options, disabled=options[0].value == "0")

    async def callback(self, interaction: discord.Interaction) -> None:
        if not _owner_only(interaction, self.browser.owner_id):
            await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
            return
        surah = int(self.values[0])
        try:
            await self.browser.cog.queue_selected_surah(interaction, self.browser.reader, surah)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
        except Exception:
            await interaction.response.send_message("تعذر بدء التشغيل. تحقق من صلاحيات الصوت وFFmpeg.", ephemeral=True)
            raise


class SurahBrowser(discord.ui.View):
    PAGE_COUNT = 5

    def __init__(self, owner_id: int, reader: Reciter, settings: dict[str, Any]) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.reader = reader
        self.settings = settings
        self.page = 0
        self.cog: Any = None
        self._rebuild()

    def bind(self, cog: Any) -> "SurahBrowser":
        self.cog = cog
        return self

    def _rebuild(self) -> None:
        self.clear_items()
        self.add_item(SurahSelect(self))
        previous = discord.ui.Button(label="السابق", style=discord.ButtonStyle.secondary, disabled=self.page == 0)
        next_button = discord.ui.Button(label="التالي", style=discord.ButtonStyle.secondary, disabled=self.page >= self.PAGE_COUNT - 1)

        async def go_previous(interaction: discord.Interaction) -> None:
            if not _owner_only(interaction, self.owner_id):
                await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
                return
            self.page = max(0, self.page - 1)
            self._rebuild()
            embed, file = self.render()
            await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

        async def go_next(interaction: discord.Interaction) -> None:
            if not _owner_only(interaction, self.owner_id):
                await interaction.response.send_message("هذه القائمة تخص من فتحها.", ephemeral=True)
                return
            self.page = min(self.PAGE_COUNT - 1, self.page + 1)
            self._rebuild()
            embed, file = self.render()
            await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

        previous.callback = go_previous
        next_button.callback = go_next
        self.add_item(previous)
        self.add_item(next_button)

    def render(self) -> tuple[discord.Embed, discord.File | None]:
        available_count = len(self.reader.surahs)
        embed, file = make_embed(
            "📖 اختر السورة",
            f"**القارئ:** {self.reader.name}\n**المصحف / الرواية:** {self.reader.moshaf_name}\n"
            f"**المتاح:** {available_count} سورة\nالصفحة **{self.page + 1}/{self.PAGE_COUNT}**",
            theme="quran",
            settings=self.settings,
        )
        return embed, file


class RadioPanelView(discord.ui.View):
    """Voice-room-only interactive controls for the Quran broadcast."""

    def __init__(self, bot: Any, guild_id: int | None = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id

    async def _allowed(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if (
            not guild
            or (self.guild_id is not None and guild.id != self.guild_id)
            or not isinstance(interaction.user, discord.Member)
        ):
            await interaction.response.send_message("لوحة التحكم غير متاحة هنا.", ephemeral=True)
            return False
        voice = guild.voice_client
        if not voice or not interaction.user.voice or interaction.user.voice.channel != voice.channel:
            await interaction.response.send_message("ادخل نفس الروم الصوتي الذي يعمل فيه البوت للتحكم.", ephemeral=True)
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction, message: str | None = None) -> None:
        guild_id = interaction.guild.id if interaction.guild else self.guild_id
        if guild_id is None:
            return
        state = self.bot.audio_player.state(guild_id)
        current = state.now_playing
        description = message or (
            f"**الآن:** {SURAH_BY_NUMBER[current.surah]} — {current.reciter.name}"
            if current
            else "الإذاعة متصلة وجاهزة."
        )
        if state.broadcast_tracks:
            description += "\n**وضع الإذاعة:** ختمة كاملة " + ("تُعاد تلقائياً." if state.repeat_broadcast else "مع إيقاف التكرار بعد إكمال القائمة.")
        description += f"\n**مستوى الصوت:** {int(state.volume * 100)}%" + (" • مكتوم" if state.muted else "")
        embed, file = make_embed("📡 إذاعة القرآن — لوحة التحكم", description, theme="quran")
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)

    @discord.ui.button(label="خفض الصوت", emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="noor:radio:volume_down")
    async def volume_down(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        state = self.bot.audio_player.state(self.guild_id)
        self.bot.audio_player.set_volume(interaction.guild.id, state.volume - 0.1)
        await self._refresh(interaction)

    @discord.ui.button(label="رفع الصوت", emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="noor:radio:volume_up")
    async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        state = self.bot.audio_player.state(self.guild_id)
        self.bot.audio_player.set_volume(interaction.guild.id, state.volume + 0.1)
        await self._refresh(interaction)

    @discord.ui.button(label="كتم / تشغيل", emoji="🔇", style=discord.ButtonStyle.secondary, custom_id="noor:radio:mute")
    async def mute(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        muted = self.bot.audio_player.toggle_mute(interaction.guild.id)
        await self._refresh(interaction, "تم كتم الصوت." if muted else "تم إلغاء الكتم.")

    @discord.ui.button(label="إيقاف مؤقت / متابعة", emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="noor:radio:pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        if await self.bot.audio_player.pause(interaction.guild.id):
            await self._refresh(interaction, "تم إيقاف التلاوة مؤقتاً.")
        elif await self.bot.audio_player.resume(interaction.guild.id):
            await self._refresh(interaction, "تم استئناف التلاوة.")
        else:
            await interaction.response.send_message("لا توجد تلاوة تعمل حالياً.", ephemeral=True)

    @discord.ui.button(label="تخطي السورة", emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="noor:radio:skip")
    async def skip_track(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        if await self.bot.audio_player.skip(interaction.guild.id):
            await self._refresh(interaction, "تم تخطي السورة؛ ستبدأ التالية.")
        else:
            await interaction.response.send_message("لا توجد سورة لتخطيها.", ephemeral=True)

    @discord.ui.button(label="تكرار الختمة", emoji="🔁", style=discord.ButtonStyle.secondary, custom_id="noor:radio:repeat")
    async def repeat(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        repeat = self.bot.audio_player.toggle_repeat(interaction.guild.id)
        await self._refresh(interaction, "تكرار الختمة " + ("مفعّل." if repeat else "متوقف بعد إكمال القائمة."))

    @discord.ui.button(label="إيقاف الإذاعة", emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="noor:radio:stop")
    async def stop_radio(self, interaction: discord.Interaction, button: discord.ui.Button["RadioPanelView"]) -> None:
        if not await self._allowed(interaction):
            return
        await self.bot.audio_player.stop(interaction.guild.id)
        for child in self.children:
            child.disabled = True
        embed, file = make_embed("📡 تم إيقاف إذاعة القرآن", "انتهى البث وغادر البوت الروم الصوتي.", theme="quran")
        await interaction.response.edit_message(embed=embed, attachments=[file] if file else [], view=self)
