from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from core.embeds import make_embed
from core.content_card import image_card_embed
from core.prayer_card import render_prayer_card
from core.prayer_service import METHOD_NAMES

METHOD_CHOICES = [app_commands.Choice(name=name, value=method) for method, name in METHOD_NAMES.items()]
THEME_CHOICES = [
    app_commands.Choice(name="القرآن", value="quran"),
    app_commands.Choice(name="الأذكار والدعاء", value="azkar"),
    app_commands.Choice(name="الصلاة", value="prayer"),
    app_commands.Choice(name="رمضان والتاريخ", value="ramadan"),
    app_commands.Choice(name="التذكيرات", value="reminder"),
]


def administrator_only():
    return app_commands.checks.has_permissions(administrator=True)


class PrayerSetupWizard(discord.ui.Modal, title="إعداد مواقيت الصلاة — رحمة"):
    city = discord.ui.TextInput(label="المدينة", max_length=80, placeholder="القاهرة")
    country = discord.ui.TextInput(label="الدولة", max_length=80, placeholder="مصر")
    timezone = discord.ui.TextInput(label="المنطقة الزمنية (IANA)", max_length=64, placeholder="Africa/Cairo")
    timetable_time = discord.ui.TextInput(label="وقت نشر جدول اليوم (HH:MM)", max_length=5, placeholder="06:00")

    def __init__(self, bot: commands.Bot, guild_id: int, defaults: dict) -> None:
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.city.default = str(defaults.get("city") or "")
        self.country.default = str(defaults.get("country") or "")
        self.timezone.default = str(defaults.get("timezone") or "Africa/Cairo")
        self.timetable_time.default = str(defaults.get("prayer_timetable_time") or "06:00")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        city = str(self.city.value).strip()
        country = str(self.country.value).strip()
        zone_name = str(self.timezone.value).strip()
        timetable_time = str(self.timetable_time.value).strip()
        if not _TIME_RE.fullmatch(timetable_time):
            await interaction.response.send_message("الوقت يجب أن يكون بصيغة 24 ساعة HH:MM، مثل 06:30.", ephemeral=True)
            return
        try:
            zone = ZoneInfo(zone_name)
        except Exception:
            await interaction.response.send_message("المنطقة الزمنية غير صحيحة. مثال: Africa/Cairo أو Asia/Riyadh.", ephemeral=True)
            return
        settings = self.bot.db.get_guild_settings(self.guild_id)
        proposal = {**settings, "city": city, "country": country, "timezone": zone_name, "prayer_timetable_time": timetable_time}
        try:
            day = await self.bot.prayer_service.today(proposal)
        except (ValueError, RuntimeError) as error:
            await interaction.response.send_message(f"لم أحفظ الإعدادات لأن التحقق من المواقيت فشل: {error}", ephemeral=True)
            return
        self.bot.db.apply_guild_settings_patch(
            self.guild_id,
            city=city,
            country=country,
            timezone=zone_name,
            prayer_timetable_time=timetable_time,
        )
        image = render_prayer_card(day, city, country, generated_at=datetime.now(zone))
        accessible = (
            "مواقيت الصلاة: " + "، ".join(f"{name} {value}" for name, value in day.timings.items())
            if settings.get("text_equivalent_enabled") else None
        )
        embed, file = image_card_embed(
            "🕌 اكتمل الإعداد الأولي — معاينة مواقيت اليوم",
            image,
            "rahma-wizard-preview.png",
            colour=0x126E5A,
            footer="رحمة • معاينة خاصة للمشرف",
            description=accessible,
        )
        await interaction.response.send_message(
            embed=embed,
            file=file,
            content="تم حفظ الإعدادات. أكمِل اختيار قنوات التنبيهات من لوحة رحمة؛ لم تُرسل هذه المعاينة إلى بقية الأعضاء.",
            ephemeral=True,
        )


_TIME_RE = __import__("re").compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class SetupCog(commands.GroupCog, group_name="setup", group_description="إعداد رحمة للمسؤولين"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="wizard", description="إعداد أولي خطوة بخطوة لمواقيت الصلاة")
    @administrator_only()
    async def wizard(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        await interaction.response.send_modal(
            PrayerSetupWizard(self.bot, interaction.guild.id, self.bot.db.get_guild_settings(interaction.guild.id))
        )

    @app_commands.command(name="dashboard", description="عرض لوحة إعداد البوت")
    @administrator_only()
    async def dashboard(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        prayer_channel = self._channel_label(interaction.guild, settings.get("prayer_channel_id"))
        daily_channel = self._channel_label(interaction.guild, settings.get("daily_channel_id"))
        voice_channel = self._channel_label(interaction.guild, settings.get("quran_voice_channel_id"))
        embed, file = make_embed(
            "⚙️ لوحة تحكم رحمة",
            "**📖 القرآن:** استخدم `/quran browse` و`/setup quran`.\n"
            "**🤲 الأذكار:** استخدم `/azkar start`.\n"
            "**🕌 الصلاة:** استخدم `/setup prayer` ثم `/prayer times`.\n"
            "**🔔 التذكيرات:** استخدم `/setup reminders`.\n"
            "**🎨 المظهر:** استخدم `/setup appearance` لتغيير بانر قسم معين.",
            theme="reminder",
            settings=settings,
        )
        embed.add_field(name="الموقع", value=f"{settings.get('city') or 'غير مضبوط'}، {settings.get('country') or 'غير مضبوط'}\n{settings.get('timezone')}", inline=True)
        embed.add_field(name="القنوات", value=f"الصلاة: {prayer_channel}\nاليومي: {daily_channel}\nالصوت: {voice_channel}", inline=True)
        embed.add_field(name="صورة المواقيت اليومية", value=settings.get("prayer_timetable_time", "06:00"), inline=True)
        embed.add_field(name="الحساب", value=f"{METHOD_NAMES.get(int(settings.get('calculation_method', 5)), 'مخصص')}\nالعصر: {'حنفي' if int(settings.get('asr_school', 0)) else 'شافعي/جمهور'}", inline=False)
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="prayer", description="ضبط الموقع ومواقيت الصلاة")
    @app_commands.choices(calculation_method=METHOD_CHOICES)
    @administrator_only()
    async def prayer(
        self,
        interaction: discord.Interaction,
        city: str,
        country: str,
        timezone: str,
        calculation_method: app_commands.Choice[int] | None = None,
        asr_school: app_commands.Range[int, 0, 1] = 0,
        notification_channel: discord.TextChannel | None = None,
        timetable_time: str | None = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        try:
            ZoneInfo(timezone)
        except Exception:
            await interaction.response.send_message("منطقة زمنية غير صالحة. مثال صحيح: `Africa/Cairo`.", ephemeral=True)
            return
        if timetable_time is not None:
            timetable_time = timetable_time.strip()
            try:
                parsed_time = datetime.strptime(timetable_time, "%H:%M")
                if parsed_time.strftime("%H:%M") != timetable_time:
                    raise ValueError
            except ValueError:
                await interaction.response.send_message("وقت نشر صورة المواقيت يجب أن يكون بصيغة 24 ساعة `HH:MM`، مثل `06:30`.", ephemeral=True)
                return
        method = calculation_method.value if calculation_method else 5
        updates = {
            "city": city.strip(),
            "country": country.strip(),
            "timezone": timezone.strip(),
            "calculation_method": method,
            "asr_school": int(asr_school),
        }
        if timetable_time is not None:
            updates["prayer_timetable_time"] = timetable_time
        if notification_channel:
            updates["prayer_channel_id"] = notification_channel.id
        settings = self.bot.db.update_guild_settings(interaction.guild.id, **updates)
        embed, file = make_embed(
            "🕌 تم إعداد مواقيت الصلاة",
            f"**الموقع:** {settings['city']}، {settings['country']}\n**المنطقة:** {settings['timezone']}\n**الطريقة:** {METHOD_NAMES.get(method, method)}\n**العصر:** {'حنفي' if int(asr_school) else 'شافعي/جمهور'}\n**صورة المواقيت اليومية:** {settings.get('prayer_timetable_time', '06:00')}",
            theme="prayer",
            settings=settings,
        )
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="quran", description="ضبط قناة القرآن الصوتية والتشغيل التلقائي")
    @administrator_only()
    async def quran(
        self,
        interaction: discord.Interaction,
        voice_channel: discord.VoiceChannel,
        auto_play: bool = False,
        default_reciter_id: int | None = None,
        default_edition_id: str | None = None,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        existing = self.bot.db.get_guild_settings(interaction.guild.id)
        reciter_id = default_reciter_id or existing.get("default_reciter_id")
        edition_id = default_edition_id or existing.get("default_edition_id")
        if auto_play and not reciter_id:
            await interaction.response.send_message(
                "لتمكين الإذاعة الدائمة، ضع `default_reciter_id` الظاهر في `/quran browse`.", ephemeral=True
            )
            return
        selected_reader = await self.bot.quran_service.find(int(reciter_id), str(edition_id) if edition_id else None) if reciter_id else None
        if reciter_id and not selected_reader:
            await interaction.response.send_message("لم أجد القارئ أو المصحف. افتح `/quran browse` لاختيار إصدار متاح.", ephemeral=True)
            return
        if auto_play and selected_reader and not all(number in selected_reader.surahs for number in range(1, 115)):
            await interaction.response.send_message("المصحف المختار لا يتضمن جميع السور الـ114 ولا يصلح للإذاعة الدائمة.", ephemeral=True)
            return
        updates = {
            "quran_voice_channel_id": voice_channel.id,
            "quran_auto_play": auto_play,
        }
        if default_reciter_id:
            updates["default_reciter_id"] = default_reciter_id
        if selected_reader:
            updates["default_edition_id"] = selected_reader.edition_id
        settings = self.bot.db.update_guild_settings(
            interaction.guild.id,
            **updates,
        )
        broadcast_status = "غير مفعل"
        if auto_play:
            await self.bot.audio_player.stop(interaction.guild.id)
            started, broadcast_status = await self.bot.start_guild_broadcast(interaction.guild, settings)
            if not started:
                await interaction.response.send_message(f"تعذر تشغيل الإذاعة: {broadcast_status}", ephemeral=True)
                return
        elif self.bot.audio_player.state(interaction.guild.id).broadcast_tracks:
            await self.bot.audio_player.stop(interaction.guild.id)
            broadcast_status = "تم إيقاف الإذاعة الدائمة."
        embed, file = make_embed(
            "📖 تم حفظ إعداد القرآن",
            f"الروم الصوتي الافتراضي: {voice_channel.mention}\nالتشغيل التلقائي: {'مفعل' if auto_play else 'غير مفعل'}\n"
            f"القارئ الافتراضي: {selected_reader.name if selected_reader else 'غير مضبوط'}\n"
            f"المصحف/الرواية: {selected_reader.moshaf_name if selected_reader else 'غير مضبوط'}\n"
            f"**الحالة:** {broadcast_status}\n\nالتشغيل اليدوي يظل من الروم الذي يدخله المستخدم.",
            theme="quran",
            settings=settings,
        )
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="reminders", description="ضبط قنوات التنبيهات والمحتوى اليومي")
    @administrator_only()
    async def reminders(
        self,
        interaction: discord.Interaction,
        prayer_channel: discord.TextChannel,
        daily_channel: discord.TextChannel,
        friday_reminder: bool = True,
    ) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        settings = self.bot.db.update_guild_settings(
            interaction.guild.id,
            prayer_channel_id=prayer_channel.id,
            daily_channel_id=daily_channel.id,
            friday_reminder=friday_reminder,
        )
        embed, file = make_embed(
            "🔔 تم إعداد التذكيرات",
            f"**تنبيهات الصلاة:** {prayer_channel.mention}\n**المحتوى اليومي:** {daily_channel.mention}\n**تذكير الجمعة:** {'مفعل' if friday_reminder else 'غير مفعل'}",
            theme="reminder",
            settings=settings,
        )
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="appearance", description="تغيير صورة قسم برابط HTTPS")
    @app_commands.choices(theme=THEME_CHOICES)
    @administrator_only()
    async def appearance(self, interaction: discord.Interaction, theme: app_commands.Choice[str], image_url: str) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        parsed = urlparse(image_url)
        if parsed.scheme != "https" or not parsed.netloc:
            await interaction.response.send_message("ضع رابط HTTPS مباشر وموثوق للصورة.", ephemeral=True)
            return
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        banner_urls = dict(settings.get("banner_urls") or {})
        banner_urls[theme.value] = image_url
        settings = self.bot.db.update_guild_settings(interaction.guild.id, banner_urls=banner_urls)
        embed, file = make_embed(
            "🎨 تم تحديث المظهر",
            f"تم حفظ الصورة لقسم **{theme.name}**. يمكن العودة للبانر المحلي بحذف الرابط من قاعدة البيانات أو استخدام `/setup reset-banner` في نسخة لاحقة.",
            theme=theme.value,
            settings=settings,
        )
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @app_commands.command(name="reset-banner", description="العودة إلى البانر المحلي الافتراضي لقسم")
    @app_commands.choices(theme=THEME_CHOICES)
    @administrator_only()
    async def reset_banner(self, interaction: discord.Interaction, theme: app_commands.Choice[str]) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        banner_urls = dict(settings.get("banner_urls") or {})
        banner_urls.pop(theme.value, None)
        settings = self.bot.db.update_guild_settings(interaction.guild.id, banner_urls=banner_urls)
        embed, file = make_embed("🎨 تم استعادة البانر", f"عاد قسم **{theme.name}** إلى البانر المحلي الافتراضي.", theme=theme.value, settings=settings)
        await interaction.response.send_message(embed=embed, file=file, ephemeral=True)

    @staticmethod
    def _channel_label(guild: discord.Guild, channel_id: int | None) -> str:
        channel = guild.get_channel(channel_id) if channel_id else None
        return channel.mention if channel else "غير مضبوط"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SetupCog(bot))
