from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from aiohttp import web

from core.content_card import image_card_embed, render_content_poster
from core.prayer_card import render_prayer_alert, render_prayer_card
from core.prayer_service import ARABIC_PRAYER_NAMES, METHOD_NAMES
from core.quran_data import SURAH_BY_NUMBER

_LOG = logging.getLogger("rahma.dashboard_api")
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_API_PREFIX = "/api/dashboard"
_MAX_CLOCK_SKEW = 60
_NONCE_TTL = 120
_RATE_WINDOW = 60.0
_ACTOR_ID_KEY = web.AppKey("rahma_actor_id", str)
_RAW_BODY_KEY = web.AppKey("rahma_raw_body", bytes)


class DashboardApi:
    """Small same-loop API for a separately hosted, server-side dashboard.

    Requests are authenticated with a timestamped HMAC signature, random nonce,
    body hash, exact URL path/query, and dashboard-side operator ID. The shared
    secret is never sent to a browser. User authorization is enforced separately
    by the dashboard's Discord OAuth backend before it calls this service.
    """

    def __init__(self, bot: Any, secret: str, allow_origins: str = "") -> None:
        self.bot = bot
        self.secret = secret.encode("utf-8")
        self.allowed_origins = {origin.strip().rstrip("/") for origin in allow_origins.split(",") if origin.strip()}
        self.seen_nonces: dict[str, float] = {}
        self.request_times: dict[str, deque[float]] = defaultdict(deque)
        self.runner: web.AppRunner | None = None
        self.app = web.Application(
            middlewares=[self._error_response],
            client_max_size=32 * 1024,
        )
        self.app.add_routes(
            [
                web.get(f"{_API_PREFIX}/health", self.health),
                web.get(f"{_API_PREFIX}/guilds", self.guilds),
                web.get(f"{_API_PREFIX}/guilds/{{guild_id}}", self.guild_detail),
                web.patch(f"{_API_PREFIX}/guilds/{{guild_id}}/settings", self.update_settings),
                web.post(f"{_API_PREFIX}/guilds/{{guild_id}}/preview", self.preview),
                web.post(f"{_API_PREFIX}/guilds/{{guild_id}}/radio", self.radio),
                web.get(f"{_API_PREFIX}/catalogue", self.catalogue),
            ]
        )

    async def start(self, host: str, port: int) -> None:
        if len(self.secret) < 32:
            raise RuntimeError("DASHBOARD_SHARED_SECRET must contain at least 32 UTF-8 bytes.")
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, host=host, port=port)
        await site.start()
        _LOG.info("Dashboard API listening at configured bind address %s:%s", host, port)

    async def close(self) -> None:
        if self.runner:
            await self.runner.cleanup()
            self.runner = None

    @web.middleware
    async def _error_response(self, request: web.Request, handler):
        try:
            return await self._authenticate(request, handler)
        except web.HTTPException as error:
            headers = {"Retry-After": error.headers["Retry-After"]} if error.headers and error.headers.get("Retry-After") else {}
            return web.json_response({"message": error.text, "status": error.status}, status=error.status, headers=headers)

    @web.middleware
    async def _authenticate(self, request: web.Request, handler):
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") not in self.allowed_origins:
            raise web.HTTPForbidden(text="This endpoint accepts signed server-to-server calls only.")

        if not request.path.startswith(_API_PREFIX + "/"):
            return await handler(request)

        raw_body = await request.read()
        timestamp_text = request.headers.get("X-Rahma-Timestamp", "")
        nonce = request.headers.get("X-Rahma-Nonce", "")
        actor = request.headers.get("X-Rahma-Actor", "")
        supplied = request.headers.get("X-Rahma-Signature", "")
        if not timestamp_text.isascii() or not timestamp_text.isdigit() or not re.fullmatch(r"[A-Za-z0-9_-]{16,96}", nonce):
            raise web.HTTPUnauthorized(text="Missing or invalid signature metadata.")
        try:
            timestamp = int(timestamp_text)
        except ValueError:
            raise web.HTTPUnauthorized(text="Invalid timestamp.") from None
        if abs(int(time.time()) - timestamp) > _MAX_CLOCK_SKEW:
            raise web.HTTPUnauthorized(text="Expired request signature.")
        now = time.monotonic()
        if nonce in self.seen_nonces:
            raise web.HTTPUnauthorized(text="Request nonce has already been used.")

        body_hash = hashlib.sha256(raw_body).hexdigest()
        canonical = f"{timestamp_text}\n{nonce}\n{request.method}\n{request.raw_path}\n{body_hash}\n{actor}"
        expected = hmac.new(self.secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        if not actor.isascii() or len(actor) > 32 or not supplied or not hmac.compare_digest(expected, supplied.lower()):
            raise web.HTTPUnauthorized(text="Invalid dashboard signature.")

        self.seen_nonces[nonce] = now
        expired = [key for key, seen in self.seen_nonces.items() if now - seen > _NONCE_TTL]
        for key in expired:
            self.seen_nonces.pop(key, None)

        bucket = self.request_times[actor]
        while bucket and now - bucket[0] > _RATE_WINDOW:
            bucket.popleft()
        if len(bucket) >= 90:
            raise web.HTTPTooManyRequests(text="Dashboard request limit reached; wait a moment.", headers={"Retry-After": "60"})
        bucket.append(now)

        request[_ACTOR_ID_KEY] = actor
        request[_RAW_BODY_KEY] = raw_body
        return await handler(request)

    async def _json_body(self, request: web.Request) -> dict[str, Any]:
        try:
            value = json.loads(request.get(_RAW_BODY_KEY, b"{}").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise web.HTTPBadRequest(text="Expected a valid JSON object.") from None
        if not isinstance(value, dict):
            raise web.HTTPBadRequest(text="Expected a JSON object.")
        return value

    @staticmethod
    def _guild_id(request: web.Request) -> int:
        value = request.match_info.get("guild_id", "")
        if not value.isascii() or not value.isdigit() or len(value) > 22:
            raise web.HTTPBadRequest(text="Invalid Discord server ID.")
        return int(value)

    def _guild(self, request: web.Request) -> discord.Guild:
        guild = self.bot.get_guild(self._guild_id(request))
        if guild is None:
            raise web.HTTPNotFound(text="رحمة غير موجودة في هذا السيرفر حالياً.")
        return guild

    async def health(self, _: web.Request) -> web.Response:
        try:
            readers = await self.bot.quran_service.catalogue()
            reader_count = self.bot.quran_service.raw_unique_reader_count
            editions = len(readers)
        except Exception:
            reader_count, editions = 0, 0
        return web.json_response({
            "ok": True,
            "bot_name": "رحمة",
            "connected": bool(self.bot.is_ready()),
            "guild_count": len(self.bot.guilds),
            "reciter_count": reader_count,
            "edition_count": editions,
            "checked_at": datetime.now().astimezone().isoformat(),
        })

    async def guilds(self, _: web.Request) -> web.Response:
        result = []
        for guild in sorted(self.bot.guilds, key=lambda item: item.name.casefold()):
            result.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon_url": guild.icon.url if guild.icon else None,
                "member_count": guild.member_count,
                "owner_id": str(guild.owner_id) if guild.owner_id else None,
            })
        return web.json_response({"guilds": result})

    async def guild_detail(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        settings = self.bot.db.get_guild_settings(guild.id)
        state = self.bot.audio_player.state(guild.id)
        voice = guild.voice_client
        current = state.now_playing
        radio = {
            "connected": bool(voice and voice.is_connected()),
            "playing": bool(voice and voice.is_playing()),
            "paused": bool(voice and voice.is_paused()),
            "broadcast": bool(state.broadcast_tracks),
            "repeat": state.repeat_broadcast,
            "muted": state.muted,
            "volume": state.volume,
            "queue_length": len(state.queue),
            "voice_channel_id": str(voice.channel.id) if voice and voice.channel else None,
            "voice_channel_name": voice.channel.name if voice and voice.channel else None,
            "current": ({
                "surah": current.surah,
                "surah_name": SURAH_BY_NUMBER[current.surah],
                "reader_id": current.reciter.id,
                "reader_name": current.reciter.name,
                "edition_id": current.reciter.edition_id,
                "edition_name": current.reciter.moshaf_name,
            } if current else None),
        }
        return web.json_response({
            "guild": {"id": str(guild.id), "name": guild.name, "icon_url": guild.icon.url if guild.icon else None},
            "settings": self._safe_settings(settings),
            "text_channels": [
                {"id": str(channel.id), "name": channel.name}
                for channel in guild.text_channels
                if channel.permissions_for(guild.me).send_messages
            ],
            "voice_channels": [
                {"id": str(channel.id), "name": channel.name}
                for channel in guild.voice_channels
                if channel.permissions_for(guild.me).connect
            ],
            "radio": radio,
            "methods": [{"id": key, "name": label} for key, label in METHOD_NAMES.items()],
            "available_timezones": ["Africa/Cairo", "Asia/Riyadh", "Asia/Dubai", "Europe/London", "America/New_York", "UTC"],
        })

    @staticmethod
    def _safe_settings(settings: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "city", "country", "timezone", "calculation_method", "asr_school",
            "prayer_channel_id", "prayer_timetable_time", "prayer_timetable_enabled",
            "prayer_alerts_enabled", "daily_channel_id", "daily_content_enabled", "daily_content_time",
            "friday_reminder", "friday_reminder_time", "text_equivalent_enabled", "quran_voice_channel_id",
            "quran_auto_play", "default_reciter_id", "default_edition_id",
        }
        result = {key: settings.get(key) for key in allowed}
        for key in ("prayer_channel_id", "daily_channel_id", "quran_voice_channel_id"):
            result[key] = str(settings[key]) if settings.get(key) is not None else None
        return result

    async def update_settings(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        body = await self._json_body(request)
        allowed = {
            "city", "country", "timezone", "calculation_method", "asr_school",
            "prayer_channel_id", "prayer_timetable_time", "prayer_timetable_enabled",
            "prayer_alerts_enabled", "daily_channel_id", "daily_content_enabled", "daily_content_time",
            "friday_reminder", "friday_reminder_time", "text_equivalent_enabled", "quran_voice_channel_id",
            "quran_auto_play", "default_reciter_id", "default_edition_id",
        }
        if not body or set(body) - allowed:
            raise web.HTTPBadRequest(text="Settings payload is empty or contains unsupported fields.")
        current = self.bot.db.get_guild_settings(guild.id)
        settings = {**current, **body}

        for key in ("city", "country"):
            value = settings.get(key)
            if key in body and (not isinstance(value, str) or not value.strip() or len(value.strip()) > 80):
                raise web.HTTPBadRequest(text=f"{key} must be a non-empty string no longer than 80 characters.")
            if isinstance(value, str):
                if len(value.strip()) > 80:
                    raise web.HTTPBadRequest(text=f"{key} cannot exceed 80 characters.")
                settings[key] = value.strip()
        if not isinstance(settings.get("timezone"), str) or len(settings["timezone"]) > 64:
            raise web.HTTPBadRequest(text="Invalid timezone.")
        try:
            ZoneInfo(settings["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise web.HTTPBadRequest(text="Unknown IANA timezone.") from None
        try:
            settings["calculation_method"] = int(settings["calculation_method"])
            settings["asr_school"] = int(settings["asr_school"])
        except (TypeError, ValueError):
            raise web.HTTPBadRequest(text="Invalid calculation method or Asr school.") from None
        if settings["calculation_method"] not in METHOD_NAMES or settings["asr_school"] not in (0, 1):
            raise web.HTTPBadRequest(text="Unsupported prayer calculation settings.")
        for key in ("prayer_timetable_time", "daily_content_time", "friday_reminder_time"):
            if not isinstance(settings.get(key), str) or not _TIME_RE.fullmatch(settings[key]):
                raise web.HTTPBadRequest(text=f"{key} must use HH:MM in 24-hour time.")
        for key in ("prayer_timetable_enabled", "prayer_alerts_enabled", "daily_content_enabled", "friday_reminder", "text_equivalent_enabled", "quran_auto_play"):
            if key in body and not isinstance(body[key], bool):
                raise web.HTTPBadRequest(text=f"{key} must be a boolean.")

        for key, channel_type in (
            ("prayer_channel_id", discord.TextChannel),
            ("daily_channel_id", discord.TextChannel),
            ("quran_voice_channel_id", discord.VoiceChannel),
        ):
            if key not in body:
                continue
            raw_id = body[key]
            if raw_id is None:
                settings[key] = None
                continue
            try:
                channel_id = int(raw_id)
            except (TypeError, ValueError):
                raise web.HTTPBadRequest(text=f"{key} must be a valid Discord channel ID or null.") from None
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, channel_type):
                raise web.HTTPBadRequest(text=f"{key} must refer to an appropriate channel in this server.")
            perms = channel.permissions_for(guild.me)
            if isinstance(channel, discord.TextChannel) and not perms.send_messages:
                raise web.HTTPBadRequest(text=f"Rahma cannot send messages to {channel.name}.")
            if isinstance(channel, discord.VoiceChannel) and not perms.connect:
                raise web.HTTPBadRequest(text=f"Rahma cannot connect to {channel.name}.")
            settings[key] = channel_id

        previous = current
        reader_id = settings.get("default_reciter_id")
        if reader_id in (None, ""):
            settings["default_reciter_id"] = None
            settings["default_edition_id"] = None
        else:
            try:
                reader_id = int(reader_id)
            except (TypeError, ValueError):
                raise web.HTTPBadRequest(text="default_reciter_id must be a valid reader ID.") from None
            editions = await self.bot.quran_service.editions_for(reader_id)
            if not editions:
                raise web.HTTPBadRequest(text="Reader not found in the current catalogue.")
            edition_id = settings.get("default_edition_id") or editions[0].edition_id
            selected = next((item for item in editions if item.edition_id == str(edition_id)), None)
            if not selected:
                raise web.HTTPBadRequest(text="Selected recitation edition does not belong to that reader.")
            settings["default_reciter_id"] = reader_id
            settings["default_edition_id"] = selected.edition_id
            if settings.get("quran_auto_play") and not all(number in selected.surahs for number in range(1, 115)):
                raise web.HTTPBadRequest(text="Continuous broadcast requires an edition with all 114 surahs.")

        # Apply normalized IDs/integers and the resolved edition, not raw client strings.
        normalized = {key: settings[key] for key in body if key in settings}
        normalized.update({key: settings[key] for key in ("default_reciter_id", "default_edition_id")})
        self.bot.db.apply_guild_settings_patch(guild.id, **normalized)
        saved = self.bot.db.get_guild_settings(guild.id)

        if previous.get("quran_auto_play") and not saved.get("quran_auto_play"):
            await self.bot.audio_player.stop(guild.id)
        elif saved.get("quran_auto_play") and (
            not previous.get("quran_auto_play")
            or previous.get("quran_voice_channel_id") != saved.get("quran_voice_channel_id")
            or previous.get("default_reciter_id") != saved.get("default_reciter_id")
            or previous.get("default_edition_id") != saved.get("default_edition_id")
        ):
            await self.bot.audio_player.stop(guild.id)
            started, message = await self.bot.start_guild_broadcast(guild, saved)
            if not started:
                self.bot.db.apply_guild_settings_patch(guild.id, quran_auto_play=False)
                raise web.HTTPBadRequest(text=message)

        _LOG.info("Dashboard settings updated for guild %s by actor %s", guild.id, request[_ACTOR_ID_KEY])
        return web.json_response({"ok": True, "guild_id": str(guild.id), "settings": self._safe_settings(saved)})

    async def catalogue(self, request: web.Request) -> web.Response:
        query = request.query.get("q", "").strip()
        all_editions = await self.bot.quran_service.catalogue()
        grouped: dict[int, dict[str, Any]] = {}
        for edition in all_editions:
            if query and query.casefold() not in edition.name.casefold():
                continue
            group = grouped.setdefault(edition.id, {"id": edition.id, "name": edition.name, "editions": []})
            group["editions"].append({
                "id": edition.edition_id,
                "name": edition.moshaf_name,
                "surah_count": len(edition.surahs),
                "full_khatmah": all(number in edition.surahs for number in range(1, 115)),
            })
        reciters = sorted(grouped.values(), key=lambda item: (item["name"].casefold(), item["id"]))
        return web.json_response({
            "reciters": reciters,
            "reciter_count": self.bot.quran_service.raw_unique_reader_count,
            "edition_count": len(all_editions),
            "source": "MP3Quran.net",
        })

    async def preview(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        settings = self.bot.db.get_guild_settings(guild.id)
        body = await self._json_body(request)
        kind = body.get("kind")
        channels_by_type = {
            "prayer": settings.get("prayer_channel_id"),
            "timetable": settings.get("prayer_channel_id"),
            "daily": settings.get("daily_channel_id"),
            "friday": settings.get("daily_channel_id"),
        }
        channel_id = channels_by_type.get(kind)
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel):
            raise web.HTTPBadRequest(text="Configure a suitable text channel before sending a preview.")

        actor = request[_ACTOR_ID_KEY]
        now = time.monotonic()
        bucket = self.request_times[f"preview:{guild.id}"]
        while bucket and now - bucket[0] > 30:
            bucket.popleft()
        if bucket:
            raise web.HTTPTooManyRequests(text="Wait 30 seconds between preview posts.", headers={"Retry-After": "30"})
        bucket.append(now)

        if kind in ("prayer", "timetable"):
            if not settings.get("city") or not settings.get("country"):
                raise web.HTTPBadRequest(text="Complete the setup wizard before generating a prayer preview.")
            day = await self.bot.prayer_service.today(settings)
            if kind == "timetable":
                image = render_prayer_card(day, settings["city"], settings["country"], generated_at=datetime.now(ZoneInfo(settings["timezone"])))
                embed, file = image_card_embed(
                    "🕌 معاينة مواقيت الصلاة اليومية", image, "rahma-preview-prayer-times.png",
                    colour=0x126E5A, footer="رحمة • معاينة خاصة",
                )
            else:
                prayer = next((name for name in ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha") if name in day.timings), "Fajr")
                image = render_prayer_alert(ARABIC_PRAYER_NAMES[prayer], day.timings[prayer], settings["city"], settings["country"])
                embed, file = image_card_embed(
                    f"🕌 معاينة تنبيه {ARABIC_PRAYER_NAMES[prayer]}", image,
                    "rahma-preview-prayer-alert.png", colour=0x126E5A, footer="رحمة • معاينة خاصة",
                )
        else:
            from cogs.prayer import DAILY_CONTENT

            if kind == "daily":
                image = render_content_poster("معاينة المحتوى اليومي", [(title, text, source) for title, text, source, _ in DAILY_CONTENT])
                alt_text = "\n".join(f"{title}: {text} — {source}" for title, text, source, _ in DAILY_CONTENT)
                title = "🤲 معاينة المحتوى اليومي"
            elif kind == "friday":
                friday_text = "أكثروا من الصلاة والسلام على النبي ﷺ، وتهيؤوا لصلاة الجمعة."
                friday_source = "سنن أبي داود، 1047"
                image = render_content_poster("تذكير الجمعة", [(None, friday_text, friday_source)])
                alt_text = f"{friday_text}\nالمصدر: {friday_source}"
                title = "🕌 معاينة تذكير الجمعة"
            else:
                raise web.HTTPBadRequest(text="Unknown preview kind.")
            embed, file = image_card_embed(
                title, image, f"rahma-preview-{kind}.png", colour=0x665191,
                footer="رحمة • معاينة خاصة",
                description=alt_text if settings.get("text_equivalent_enabled") else None,
            )

        await channel.send(embed=embed, file=file)
        _LOG.info("Dashboard sent %s preview to guild %s by actor %s", kind, guild.id, actor)
        return web.json_response({"ok": True, "preview": kind, "channel_id": str(channel.id), "channel_name": channel.name})

    async def radio(self, request: web.Request) -> web.Response:
        guild = self._guild(request)
        body = await self._json_body(request)
        action = body.get("action")
        player = self.bot.audio_player
        state = player.state(guild.id)
        voice = guild.voice_client

        if action == "start":
            settings = self.bot.db.get_guild_settings(guild.id)
            if not settings.get("default_reciter_id"):
                raise web.HTTPBadRequest(text="اختر القارئ والمصحف أولاً.")
            await player.stop(guild.id)
            started, message = await self.bot.start_guild_broadcast(guild, settings)
            if not started:
                raise web.HTTPBadRequest(text=message)
        elif action == "volume":
            value = body.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 1:
                raise web.HTTPBadRequest(text="Volume must be between 0 and 1.")
            player.set_volume(guild.id, float(value))
        elif action == "mute":
            desired = body.get("value")
            if not isinstance(desired, bool):
                raise web.HTTPBadRequest(text="Mute value must be a boolean.")
            if desired != state.muted:
                player.toggle_mute(guild.id)
        elif action == "repeat":
            desired = body.get("value")
            if not isinstance(desired, bool):
                raise web.HTTPBadRequest(text="Repeat value must be a boolean.")
            if desired != state.repeat_broadcast:
                player.toggle_repeat(guild.id)
        elif action in ("pause", "resume", "skip", "stop"):
            if action == "pause":
                ok = await player.pause(guild.id)
            elif action == "resume":
                ok = await player.resume(guild.id)
            elif action == "skip":
                ok = await player.skip(guild.id)
            else:
                await player.stop(guild.id)
                ok = True
            if not ok:
                raise web.HTTPConflict(text="There is no active track for that action.")
        elif action != "status":
            raise web.HTTPBadRequest(text="Unknown radio action.")

        state = player.state(guild.id)
        voice = guild.voice_client
        current = state.now_playing
        result = {
            "connected": bool(voice and voice.is_connected()),
            "playing": bool(voice and voice.is_playing()),
            "paused": bool(voice and voice.is_paused()),
            "broadcast": bool(state.broadcast_tracks),
            "repeat": state.repeat_broadcast,
            "muted": state.muted,
            "volume": state.volume,
            "queue_length": len(state.queue),
            "voice_channel_id": str(voice.channel.id) if voice and voice.channel else None,
            "voice_channel_name": voice.channel.name if voice and voice.channel else None,
            "current": ({
                "surah": current.surah,
                "surah_name": SURAH_BY_NUMBER[current.surah],
                "reader_id": current.reciter.id,
                "reader_name": current.reciter.name,
                "edition_id": current.reciter.edition_id,
                "edition_name": current.reciter.moshaf_name,
            } if current else None),
        }
        _LOG.info("Dashboard radio action=%s guild=%s actor=%s", action, guild.id, request[_ACTOR_ID_KEY])
        return web.json_response({"ok": True, "radio": result})


def make_dashboard_api(bot: Any, secret: str, allow_origins: str = "") -> DashboardApi:
    """Create a dashboard API instance suitable for owning in the bot lifecycle."""
    return DashboardApi(bot, secret, allow_origins)


def sign_request(secret: str, method: str, raw_path: str, body: bytes, actor: str, timestamp: str, nonce: str) -> str:
    """Canonical signer used by tests and manual integration diagnostics."""
    canonical = (
        f"{timestamp}\n{nonce}\n{method.upper()}\n{raw_path}\n"
        f"{hashlib.sha256(body).hexdigest()}\n{actor}"
    )
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def make_nonce() -> str:
    return secrets.token_urlsafe(24)


def utc_timestamp() -> str:
    return str(int(time.time()))


__all__ = ["DashboardApi", "make_dashboard_api", "make_nonce", "sign_request", "utc_timestamp"]
