from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_GUILD_SETTINGS: dict[str, Any] = {
    "city": "",
    "country": "",
    "timezone": "UTC",
    "calculation_method": 5,
    "asr_school": 0,
    "prayer_channel_id": None,
    "prayer_timetable_time": "06:00",
    "prayer_timetable_enabled": True,
    "prayer_alerts_enabled": True,
    "daily_channel_id": None,
    "daily_content_enabled": True,
    "daily_content_time": "08:00",
    "friday_reminder": True,
    "friday_reminder_time": "09:00",
    "text_equivalent_enabled": False,
    "quran_voice_channel_id": None,
    "quran_auto_play": False,
    "default_reciter_id": None,
    "default_edition_id": None,
    "banner_urls": {},
}


class Database:
    """Small SQLite store for non-sensitive, per-guild bot preferences."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sent_notifications (
                guild_id INTEGER NOT NULL,
                notice_key TEXT NOT NULL,
                notice_date TEXT NOT NULL,
                PRIMARY KEY (guild_id, notice_key, notice_date)
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def get_guild_settings(self, guild_id: int) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT payload FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        if not row:
            return DEFAULT_GUILD_SETTINGS.copy()
        payload = json.loads(row["payload"])
        return {**DEFAULT_GUILD_SETTINGS, **payload}

    def update_guild_settings(self, guild_id: int, **updates: Any) -> dict[str, Any]:
        settings = self.get_guild_settings(guild_id)
        settings.update({key: value for key, value in updates.items() if value is not None})
        self.connection.execute(
            """
            INSERT INTO guild_settings(guild_id, payload) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET payload = excluded.payload
            """,
            (guild_id, json.dumps(settings, ensure_ascii=False)),
        )
        self.connection.commit()
        return settings

    def apply_guild_settings_patch(self, guild_id: int, **updates: Any) -> dict[str, Any]:
        """Persist explicitly supplied values, including nulls that clear a selection."""
        settings = self.get_guild_settings(guild_id)
        settings.update(updates)
        self.connection.execute(
            """
            INSERT INTO guild_settings(guild_id, payload) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET payload = excluded.payload
            """,
            (guild_id, json.dumps(settings, ensure_ascii=False)),
        )
        self.connection.commit()
        return settings

    def iter_configured_guilds(self) -> list[tuple[int, dict[str, Any]]]:
        rows = self.connection.execute("SELECT guild_id, payload FROM guild_settings").fetchall()
        return [
            (int(row["guild_id"]), {**DEFAULT_GUILD_SETTINGS, **json.loads(row["payload"])})
            for row in rows
        ]

    def claim_notification(self, guild_id: int, notice_key: str, notice_date: str) -> bool:
        """Atomically mark a notice as sent, returning False for duplicates."""
        try:
            self.connection.execute(
                "INSERT INTO sent_notifications(guild_id, notice_key, notice_date) VALUES (?, ?, ?)",
                (guild_id, notice_key, notice_date),
            )
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return False
