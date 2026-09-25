from __future__ import annotations

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from core.content_card import image_card_embed, render_content_poster


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "duas.json"
DUAS = json.loads(DATA_PATH.read_text(encoding="utf-8"))
DUA_CHOICES = [app_commands.Choice(name=value["label"], value=key) for key, value in DUAS.items()]


class DuasCog(commands.GroupCog, group_name="dua", group_description="الأدعية المأثورة"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="show", description="عرض أدعية موثقة حسب النوع")
    @app_commands.choices(category=DUA_CHOICES)
    async def show(self, interaction: discord.Interaction, category: app_commands.Choice[str]) -> None:
        if not interaction.guild:
            await interaction.response.send_message("هذا الأمر متاح داخل السيرفر فقط.", ephemeral=True)
            return
        collection = DUAS[category.value]
        settings = self.bot.db.get_guild_settings(interaction.guild.id)
        sections = [
            (item["title"], item["text"], item["source"])
            for item in collection["items"]
        ]
        image = render_content_poster(collection["label"], sections)
        embed, file = image_card_embed(
            f"🕋 {collection['label']}",
            image,
            "rahma-duas.png",
            colour=0x1E5C74,
            description=(
                "\n\n".join(
                    f"{item['title']}: {item['text']}\nالمصدر: {item['source']}"
                    for item in collection["items"]
                )
                if settings.get("text_equivalent_enabled") else None
            ),
        )
        await interaction.response.send_message(embed=embed, file=file)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DuasCog(bot))
