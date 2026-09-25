from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.embeds import make_embed
from core.content_card import image_card_embed, render_content_poster
from core.prayer_card import render_prayer_alert, render_prayer_card
from core.prayer_service import ARABIC_PRAYER_NAMES, PrayerDay

DAILY_CONTENT = (
    ("آية اليوم", "وَقُلْ رَبِّ زِدْنِي عِلْمًا", "طه: 114", "reminder"),
    ("حديث اليوم", "مَن كان يؤمن بالله واليوم الآخر فليقل خيرًا أو ليصمت.", "صحيح البخاري، 6018؛ صحيح مسلم، 47", "reminder"),
    ("ذكر اليوم", "سبحان الله وبحمده.", "صحيح البخاري، 6405", "azkar"),
    ("دعاء اليوم", "اللهم إني أسألك الهدى والتقى والعفاف والغنى.", "صحيح مسلم، 2721", "dua"),
)


class PrayerCog(commands.GroupCog, group_name="prayer", group_description="مواقيت الصلاة والنظام الإسلامي"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        if not getattr(bot, "disable_background_tasks", False):
            self.notifier.start()

    def cog_unload(self) -> None:
        if self.notifier.is_running():
            self.notifier.cancel()

    @app_commands.command(name="times", description="عرض مواقيت الصلاة اليوم")
    async def times(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        try:
            prayer_day = await self.bot.prayer_service.today(settings)
        except (ValueError, RuntimeError) as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        embed, file = self._prayer_card(prayer_day, settings)
        await interaction.response.send_message(embed=embed, file=file)

    @app_commands.command(name="hijri", description="عرض التاريخ الهجري وعدّاد رمضان")
    async def hijri(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        try:
            day = await self.bot.prayer_service.today(settings)
        except (ValueError, RuntimeError) as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        if day.hijri_month_number == 9:
            countdown = "نحن في شهر رمضان المبارك."
        else:
            months = (9 - day.hijri_month_number) % 12
            countdown = f"باقي تقريباً **{months}** شهر/أشهر على رمضان (وفق التقويم الحسابي للمزود)."
        embed, file = make_embed(
            "📅 التاريخ الهجري",
            f"**{day.hijri_date} هـ**\n{day.hijri_month_name} {day.hijri_year}\n{countdown}",
            theme="ramadan",
            source="AlAdhan / Islamic Network",
            settings=settings,
        )
        await interaction.response.send_message(embed=embed, file=file)

    @tasks.loop(seconds=30)
    async def notifier(self) -> None:
        for guild_id, settings in self.bot.db.iter_configured_guilds():
            try:
                zone = ZoneInfo(settings["timezone"])
                now = datetime.now(zone)
                if settings.get("city") and settings.get("country"):
                    day = await self.bot.prayer_service.today(settings, now)
                    channel_id = settings.get("prayer_channel_id")
                    channel = self.bot.get_channel(int(channel_id)) if channel_id else None
                    if isinstance(channel, discord.TextChannel):
                        if settings.get("prayer_alerts_enabled", True):
                            for prayer in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"):
                                if day.timings[prayer] != now.strftime("%H:%M"):
                                    continue
                                key = f"prayer:{prayer}"
                                if not self.bot.db.claim_notification(guild_id, key, now.date().isoformat()):
                                    continue
                                alert_image = render_prayer_alert(
                                    ARABIC_PRAYER_NAMES[prayer],
                                    day.timings[prayer],
                                    settings["city"],
                                    settings["country"],
                                )
                                alert, file = image_card_embed(
                                    f"🕌 وقت صلاة {ARABIC_PRAYER_NAMES[prayer]}",
                                    alert_image,
                                    "rahma-prayer-alert.png",
                                    colour=0x126E5A,
                                    footer="رحمة - تنبيه الصلاة",
                                    description=(
                                        f"حان الآن موعد صلاة {ARABIC_PRAYER_NAMES[prayer]} "
                                        f"في {settings['city']}، {settings['country']} الساعة {day.timings[prayer]}."
                                        if settings.get("text_equivalent_enabled") else None
                                    ),
                                )
                                await channel.send(embed=alert, file=file)
                    await self._send_daily_timetable(guild_id, settings, now, day)
                await self._send_daily_content(guild_id, settings, now)
            except Exception as error:
                print(f"Prayer notification error for guild {guild_id}: {error}")

    @notifier.before_loop
    async def before_notifier(self) -> None:
        await self.bot.wait_until_ready()

    async def _send_daily_timetable(self, guild_id: int, settings: dict, now: datetime, day: PrayerDay) -> None:
        """Post one full schedule at its configured local time, independent of prayer alerts."""
        if not settings.get("prayer_timetable_enabled", True):
            return
        if now.strftime("%H:%M") != settings.get("prayer_timetable_time", "06:00"):
            return
        channel_id = settings.get("prayer_channel_id")
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            return
        if not self.bot.db.claim_notification(guild_id, "prayer-timetable", now.date().isoformat()):
            return
        timetable, file = self._prayer_card(day, settings)
        await channel.send(embed=timetable, file=file)

    async def _send_daily_content(self, guild_id: int, settings: dict, now: datetime) -> None:
        daily_id = settings.get("daily_channel_id")
        if not daily_id:
            return
        channel = self.bot.get_channel(int(daily_id))
        if not isinstance(channel, discord.TextChannel):
            return
        # One combined daily-image post at its configured local time; duplicate delivery is atomically prevented.
        if (
            settings.get("daily_content_enabled", True)
            and now.strftime("%H:%M") == settings.get("daily_content_time", "08:00")
            and self.bot.db.claim_notification(guild_id, "daily-content", now.date().isoformat())
        ):
            image = render_content_poster(
                "محتوى رحمة اليوم",
                [(title, text, source) for title, text, source, _ in DAILY_CONTENT],
            )
            alt_text = "\n\n".join(
                f"{title}: {text}\nالمصدر: {source}"
                for title, text, source, _ in DAILY_CONTENT
            )
            embed, file = image_card_embed(
                "🤲 محتوى رحمة اليوم",
                image,
                "rahma-daily-reminder.png",
                colour=0x665191,
                description=alt_text if settings.get("text_equivalent_enabled") else None,
            )
            await channel.send(embed=embed, file=file)
        # Friday reminder is independently configurable and uses the same time zone.
        if (
            now.weekday() == 4
            and settings.get("friday_reminder", True)
            and now.strftime("%H:%M") == settings.get("friday_reminder_time", "09:00")
            and self.bot.db.claim_notification(guild_id, "friday-reminder", now.date().isoformat())
        ):
            image = render_content_poster(
                "تذكير الجمعة",
                [(None, "أكثروا من الصلاة والسلام على النبي ﷺ، وتهيؤوا لصلاة الجمعة.", "سنن أبي داود، 1047")],
            )
            friday_text = "أكثروا من الصلاة والسلام على النبي ﷺ، وتهيؤوا لصلاة الجمعة."
            embed, file = image_card_embed(
                "🕌 تذكير الجمعة", image, "rahma-friday-reminder.png", colour=0x665191,
                description=f"{friday_text}\nالمصدر: سنن أبي داود، 1047" if settings.get("text_equivalent_enabled") else None,
            )
            await channel.send(embed=embed, file=file)

    @staticmethod
    def _prayer_card(day: PrayerDay, settings: dict, highlight_prayer: str | None = None) -> tuple[discord.Embed, discord.File]:
        image = render_prayer_card(
            day,
            settings["city"],
            settings["country"],
            highlight_prayer=highlight_prayer,
            generated_at=datetime.now(ZoneInfo(settings["timezone"])),
        )
        embed, file = image_card_embed(
            "🕌 مواقيت الصلاة اليوم",
            image,
            "rahma-prayer-times.png",
            colour=0x126E5A,
            footer="المصدر: AlAdhan / Islamic Network • رحمة",
            description=(
                "مواقيت الصلاة: "
                + "، ".join(f"{ARABIC_PRAYER_NAMES.get(name, name)} {value}" for name, value in day.timings.items())
                if settings.get("text_equivalent_enabled") else None
            ),
        )
        return embed, file


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PrayerCog(bot))
