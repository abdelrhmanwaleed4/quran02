from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    database_path: Path
    mp3quran_api_url: str
    aladhan_api_url: str
    log_level: str
    owner_id: int | None
    sync_guild_id: int | None
    dashboard_shared_secret: str | None
    dashboard_api_host: str
    dashboard_api_port: int
    dashboard_api_allow_origins: str


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def load_settings() -> Settings:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Copy .env.example to .env and add the bot token.")

    root = Path(__file__).resolve().parents[1]
    raw_database_path = os.getenv("DATABASE_PATH", "data/rahma.sqlite3")
    database_path = Path(raw_database_path)
    if not database_path.is_absolute():
        database_path = root / database_path

    return Settings(
        discord_token=token,
        database_path=database_path,
        mp3quran_api_url=os.getenv(
            "MP3QURAN_API_URL", "https://www.mp3quran.net/api/v3/reciters?language=ar"
        ).strip(),
        aladhan_api_url=os.getenv("ALADHAN_API_URL", "https://api.aladhan.com/v1").rstrip("/"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        owner_id=_optional_int("BOT_OWNER_ID"),
        sync_guild_id=_optional_int("COMMAND_SYNC_GUILD_ID"),
        dashboard_shared_secret=os.getenv("DASHBOARD_SHARED_SECRET", "").strip() or None,
        dashboard_api_host=os.getenv("DASHBOARD_API_HOST", "127.0.0.1").strip(),
        dashboard_api_port=int(os.getenv("DASHBOARD_API_PORT", "8787")),
        dashboard_api_allow_origins=os.getenv("DASHBOARD_API_ALLOW_ORIGINS", "").strip(),
    )
