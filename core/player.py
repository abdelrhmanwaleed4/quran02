from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import discord

from core.quran_data import SURAH_BY_NUMBER
from core.quran_service import Reciter


Announcement = Callable[["Track"], Awaitable[None]]


@dataclass(slots=True)
class Track:
    reciter: Reciter
    surah: int
    requested_by: str
    text_channel_id: int


@dataclass(slots=True)
class GuildPlayer:
    queue: deque[Track] = field(default_factory=deque)
    broadcast_tracks: tuple[Track, ...] = ()
    repeat_broadcast: bool = True
    now_playing: Track | None = None
    volume: float = 0.5
    muted: bool = False
    audio_source: discord.PCMVolumeTransformer | None = None
    leave_task: asyncio.Task[None] | None = None


class AudioPlayer:
    """Guild-isolated, stream-only player using FFmpeg and Discord voice."""

    def __init__(self, bot: discord.Client, announce: Announcement) -> None:
        self.bot = bot
        self.announce = announce
        self.loop = asyncio.get_running_loop()
        self.players: dict[int, GuildPlayer] = {}
        self.locks: dict[int, asyncio.Lock] = {}

    def state(self, guild_id: int) -> GuildPlayer:
        return self.players.setdefault(guild_id, GuildPlayer())

    async def enqueue(
        self,
        guild: discord.Guild,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        tracks: list[Track],
        *,
        broadcast: bool = False,
    ) -> None:
        state = self.state(guild.id)
        self._cancel_leave_task(state)
        if broadcast:
            state.broadcast_tracks = tuple(tracks)
            state.repeat_broadcast = True
        voice = guild.voice_client
        if voice and voice.channel != voice_channel:
            await voice.move_to(voice_channel)
        elif not voice:
            voice = await voice_channel.connect(self_deaf=True)
        state.queue.extend(tracks)
        if not voice.is_playing() and not voice.is_paused() and state.now_playing is None:
            await self._play_next(guild.id)

    async def _play_next(self, guild_id: int) -> None:
        lock = self.locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                return
            voice = guild.voice_client
            state = self.state(guild_id)
            state.now_playing = None
            state.audio_source = None
            if not voice:
                return
            if not state.queue and state.broadcast_tracks and state.repeat_broadcast:
                # A configured broadcast continuously replays the selected complete khatmah.
                state.queue.extend(state.broadcast_tracks)
            elif not state.queue and state.broadcast_tracks:
                # Repeat was disabled: finish this khatmah, then return to idle/auto-leave.
                state.broadcast_tracks = ()
            if not state.queue:
                self.schedule_leave_if_empty(guild_id)
                return

            track = state.queue.popleft()
            state.now_playing = track
            raw_source = discord.FFmpegPCMAudio(
                track.reciter.stream_url(track.surah),
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn -loglevel warning",
            )
            audible_volume = 0.0 if state.muted else state.volume
            source = discord.PCMVolumeTransformer(raw_source, volume=audible_volume)
            state.audio_source = source

            def after(error: Exception | None) -> None:
                if error:
                    print(f"Voice playback error in guild {guild_id}: {error}")
                future = asyncio.run_coroutine_threadsafe(self._play_next(guild_id), self.loop)
                try:
                    future.result()
                except Exception as exc:  # pragma: no cover - callback thread safety
                    print(f"Queue continuation error: {exc}")

            voice.play(source, after=after)
            if track.text_channel_id:
                await self.announce(track)

    async def pause(self, guild_id: int) -> bool:
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client and guild.voice_client.is_playing():
            guild.voice_client.pause()
            return True
        return False

    async def resume(self, guild_id: int) -> bool:
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client and guild.voice_client.is_paused():
            guild.voice_client.resume()
            return True
        return False

    async def skip(self, guild_id: int) -> bool:
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client and (guild.voice_client.is_playing() or guild.voice_client.is_paused()):
            guild.voice_client.stop()
            return True
        return False

    def set_volume(self, guild_id: int, volume: float) -> float:
        state = self.state(guild_id)
        state.volume = max(0.0, min(1.0, round(volume, 2)))
        if state.audio_source:
            state.audio_source.volume = 0.0 if state.muted else state.volume
        return state.volume

    def toggle_mute(self, guild_id: int) -> bool:
        state = self.state(guild_id)
        state.muted = not state.muted
        if state.audio_source:
            state.audio_source.volume = 0.0 if state.muted else state.volume
        return state.muted

    def toggle_repeat(self, guild_id: int) -> bool:
        state = self.state(guild_id)
        state.repeat_broadcast = not state.repeat_broadcast
        return state.repeat_broadcast

    async def stop(self, guild_id: int) -> None:
        state = self.state(guild_id)
        self._cancel_leave_task(state)
        state.queue.clear()
        state.broadcast_tracks = ()
        state.repeat_broadcast = False
        state.now_playing = None
        state.audio_source = None
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            guild.voice_client.stop()
            await guild.voice_client.disconnect(force=True)

    def schedule_leave_if_empty(self, guild_id: int, wait_seconds: int = 90) -> None:
        state = self.state(guild_id)
        if state.broadcast_tracks:
            return
        self._cancel_leave_task(state)
        state.leave_task = asyncio.create_task(self._leave_when_empty(guild_id, wait_seconds))

    def cancel_scheduled_leave(self, guild_id: int) -> None:
        self._cancel_leave_task(self.state(guild_id))

    async def _leave_when_empty(self, guild_id: int, wait_seconds: int) -> None:
        await asyncio.sleep(wait_seconds)
        guild = self.bot.get_guild(guild_id)
        state = self.state(guild_id)
        if not guild or not guild.voice_client or state.broadcast_tracks:
            return
        non_bot_members = [member for member in guild.voice_client.channel.members if not member.bot]
        if not non_bot_members:
            await self.stop(guild_id)

    @staticmethod
    def _cancel_leave_task(state: GuildPlayer) -> None:
        if state.leave_task and not state.leave_task.done():
            state.leave_task.cancel()
        state.leave_task = None

    def queue_lines(self, guild_id: int, limit: int = 10) -> list[str]:
        state = self.state(guild_id)
        lines: list[str] = []
        if state.broadcast_tracks:
            lines.append("**📡 الإذاعة الدائمة:** مفعّلة (تكرار الختمة " + ("مفعل" if state.repeat_broadcast else "متوقف") + ").")
        if state.now_playing:
            lines.append(f"**▶ الآن:** {SURAH_BY_NUMBER[state.now_playing.surah]} — {state.now_playing.reciter.name}")
        for index, track in enumerate(list(state.queue)[:limit], start=1):
            lines.append(f"`{index}.` {SURAH_BY_NUMBER[track.surah]} — {track.reciter.name}")
        return lines
