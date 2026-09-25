# رحمة (Rahma) visual identity

Rahma is Arabic-first and uses midnight navy, burgundy accents, warm gold edging, a crescent, and restrained Islamic geometric ornament. The existing crescent-and-arch icon is text-free and remains suitable for the Rahma brand; the bot name is displayed as **رحمة** in newly rendered prayer, dua, adhkar, and reminder cards.

## Assets

- `assets/rahma-bot-avatar.png` — square bot profile image. To change the live Discord icon, open **Applications → رحمة → General Information → App Icon** in the Discord Developer Portal, upload this PNG, and save.
- `assets/quran-banner.png` — Quran and recitation embeds.
- `assets/azkar-banner.png` — adhkar and dua embeds.
- `assets/prayer-banner.png` — prayer alerts and daily prayer timetables.
- `assets/ramadan-banner.png` — Ramadan and Hijri date.
- `assets/reminder-banner.png` — daily and Friday reminders.

Section banners are wired into the bot. The image-generation assets contain no wordmark, so changing the name does not distort or misspell Arabic typography. Reminder/dhikr/dua copy, including source references, is rendered into the image itself. The bot's public avatar/display name must be changed once in the Discord Developer Portal; the source package includes the correctly named icon asset.

To rename an existing running deployment from Noor, update the Discord application display name to **رحمة**, install the `rahma-discord-bot.service` unit shown in `DEPLOY.md`, and retain any existing `DATABASE_PATH` value in `.env` if you want to keep the old SQLite settings file.

Admins can still override section banner URLs through `/setup appearance`.

All branded backgrounds stay text-free. Dynamic Arabic text is rendered deterministically in the bot so the quoted dua and references are preserved exactly.
