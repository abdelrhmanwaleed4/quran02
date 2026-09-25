# رحمة (Rahma) — Discord Islamic Companion

**رحمة (Rahma)** is an Arabic-first Discord bot for Quran recitation, adhkar, dua, prayer times, daily Islamic reminders, Hijri date, and an admin-controlled visual identity. It is designed to run as an independent bot, not as an add-on to a moderation bot.

> **Religious-content safety:** Quran audio is streamed only from the configured recitation provider; prayer times are calculated by the selected method and city; the bundled adhkar and duas are deliberately small, sourced entries. Administrators should review any future content pack with a qualified scholar before enabling it.

## Included V1 features

| Area | What is included |
| --- | --- |
| Quran | Browse a live Arabic reciter catalogue, choose a reciter then a surah, voice playback, queue, full-khatmah queue, pause/resume/skip/stop, automatic leave when a room becomes empty, and an optional continuous full-khatmah radio with interactive sound controls. |
| Adhkar | Morning, evening, sleep, waking, after-prayer, mosque-entry/exit and general adhkar. Every dhikr and its reference are printed inside its image card. |
| Duas | Quranic duas, prophets' duas, general supplications, travel, distress and istikharah, all rendered with their sources inside images. |
| Prayer times | City/country/time-zone setup, calculation method and madhhab selection, one concise Arabic alert image at each prayer, and a separate full timetable image posted once daily at a configurable local time. |
| Daily Islamic system | Hijri date, Ramadan countdown, Friday reminder, daily verse, hadith, dhikr and dua; reminder and content text appears inside its image. |
| Appearance | Every public bot response is a Discord embed with a relevant local banner. Admins can override banner URLs without changing code. |
| Admin control | `/setup dashboard`, `/setup prayer`, `/setup quran`, `/setup reminders`, and `/setup appearance` keep configuration in SQLite per server. |

## Quick start

1. Create a Discord application and Bot at [Discord Developer Portal](https://discord.com/developers/applications), then copy its token.
2. Install the app in the server with the `bot` and `applications.commands` scopes. Grant **View Channels**, **Send Messages**, **Embed Links**, **Attach Files**, **Connect**, **Speak**, and **Use Voice Activity**. The bot does not need Message Content Intent.
3. Install Python 3.11+ and **FFmpeg** on the host. On Ubuntu: `sudo apt-get update && sudo apt-get install -y ffmpeg python3-venv fonts-noto-core`.
4. Copy `.env.example` to `.env`, set `DISCORD_TOKEN`, and choose an owner ID only if you want owner-level diagnostics.
5. Run the commands below.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

6. In Discord, run `/setup dashboard`, then `/setup prayer` and `/setup quran` as an administrator. Use `/quran browse` to start a recitation.

## Deployment options

| Approach | Tradeoffs | Cost | Setup complexity |
| --- | --- | --- | --- |
| **Managed always-on application hosting** | Best for a normal community bot; it stays connected to Discord without a personal computer. Audio/FFmpeg support must be available in the host image. | Hosting usage charges may apply. | Low–medium |
| **Your own computer or VPS with the provided system service** | Full control of Python, FFmpeg and logs; the device/server must stay online. | Free on an existing computer; VPS cost varies. | Medium |

For a reliable voice bot, use an always-on host. The current sandbox is intentionally not a deployment target: it hibernates and has no Discord token. The included `systemd/rahma-discord-bot.service` lets an Ubuntu host restart the bot automatically.

## Commands

| Command | Purpose |
| --- | --- |
| `/quran browse` | Search the live catalogue of readers, select a reciter and a specific moshaf edition from paged lists, and then choose a surah. |
| `/quran full` | Queue all 114 surahs from the selected reader and edition. |
| `/quran radio <reciter_id>` | Start a continuous full-khatmah broadcast in your current voice channel and post controls for volume, mute, pause/resume, skip, repeat, and stop. |
| `/quran controls` | Post another panel for the active broadcast. Controls work only for members in the bot’s current voice channel. |
| `/quran play <surah> <reciter_id>` | Direct voice playback using a reader ID shown by the browser. |
| `/quran pause`, `/quran resume`, `/quran skip`, `/quran stop`, `/quran queue` | Voice-player controls. |
| `/azkar start` | Starts an interactive dhikr sequence; each entry's words and source are inside the image. |
| `/dua show` | Shows every dua in the chosen category, with text and reference inside a Rahma image. |
| `/prayer times` | Shows a generated Arabic PNG schedule using the configured location and source timings. |
| `/prayer hijri` | Shows the Hijri date and Ramadan countdown. |
| `/setup dashboard` | Posts the visual administration dashboard. |
| `/setup prayer ...` | Configures location, time zone, channel, method, madhhab, and the daily timetable-image time (`HH:MM`, default `06:00`). |
| `/setup quran ...` | Stores the default voice channel and auto-play preference. To enable the continuous radio, supply `auto_play:true` plus a full-khatmah `default_reciter_id` displayed by `/quran browse`. |
| `/setup reminders ...` | Configures reminder and daily-content channels. |
| `/setup appearance ...` | Optionally overrides the local banner with a safe HTTPS image URL. |

## Data sources and attribution

| Data | Provider | Use in this project |
| --- | --- | --- |
| Quran recitation catalogue and MP3 streams | [MP3Quran](https://www.mp3quran.net/eng/api) | Merges Arabic and English catalogue responses, deduplicates by reader ID, exposes each distinct moshaf edition, and fetches stream URLs at runtime. The latest live smoke check found **242 unique readers and 288 editions**; the provider catalogue may change. No recordings are bundled. |
| Prayer timings and Hijri date | [AlAdhan / Islamic Network](https://aladhan.com/prayer-times-api) | Fetches today’s timings by configured city and country, with a selected calculation method and madhhab. |
| Quranic and hadith references | [Quran.com](https://quran.com/) and the cited canonical collections | The data pack labels each entry with a source reference; it does not claim to issue religious rulings. |

## Production checklist

- Keep `DISCORD_TOKEN` only in `.env`/a secret manager; never commit it.
- Enable **Server Members Intent** only if a future feature actually needs it; this V1 does not.
- Give the bot only the permissions listed above, ideally in a dedicated channel.
- Confirm the city, time zone, calculation method, and madhhab with the server administrator before enabling notices. Prayer times differ between calculation authorities and local mosque announcements may take precedence.
- Review the streaming provider’s terms of use and availability for the intended server before a public launch.
- Daily timetable images use Arabic-capable fonts and display the provider's exact times, configured location, dates, and calculation method. They are posted once per local day at the configured time (default `06:00`).
- Each prayer alert is its own quiet dark image card showing the prayer name, exact local time, and configured location.
- Backup `data/rahma.sqlite3` regularly; it stores per-server settings only, not tokens.

## Project layout

```text
rahma-discord-bot/
├── bot.py
├── cogs/                 # Slash-command feature modules
├── core/                 # Config, database, embeds, services and UI
├── data/                 # Curated Arabic content packs and SQLite data
├── assets/               # Local themed banners attached to embeds
├── systemd/              # Optional Ubuntu service unit
├── tests/                # Offline tests
├── .env.example
└── requirements.txt
```
