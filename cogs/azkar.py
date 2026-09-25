from __future__ import annotations

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.embeds import make_embed
from core.views import AzkarView


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "azkar.json"
AZKAR = json.loads(DATA_PATH.read_text(encoding="utf-8"))
AZKAR_CHOICES = [app_commands.Choice(name=value["label"], value=key) for key, value in AZKAR.items()]


class AzkarCog(commands.GroupCog, group_name="azkar", group_description="الأذكار التفاعلية"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="start", description="بدء أذكار تفاعلية مع عداد لكل ذكر")
    @app_commands.choices(kind=AZKAR_CHOICES)
    async def start(self, interaction: discord.Interaction, kind: app_commands.Choice[str]) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        collection = AZKAR[kind.value]
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        view = AzkarView(interaction.user.id, collection["label"], collection["items"], settings)
        embed, file = view.render()
        await interaction.response.send_message(embed=embed, file=file, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AzkarCog(bot))
