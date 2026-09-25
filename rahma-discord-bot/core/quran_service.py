from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp


@dataclass(frozen=True, slots=True)
class Reciter:
    id: int
    name: str
    moshaf_name: str
    server: str
    surahs: frozenset[int]
    edition_id: str = ""

    def __post_init__(self) -> None:
        if not self.edition_id:
            normalized = f"{self.server.rstrip('/')}|{','.join(f'{number:03d}' for number in sorted(self.surahs))}"
            object.__setattr__(self, "edition_id", hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16])

    def stream_url(self, surah: int) -> str:
        if surah not in self.surahs:
            raise ValueError("هذه السورة غير متاحة في المصحف المختار لهذا القارئ.")
        return f"{self.server.rstrip('/')}/{surah:03d}.mp3"


class QuranService:
    """Loads unique Arabic/English reader records and every available moshaf."""

    def __init__(self, session: aiohttp.ClientSession, api_url: str) -> None:
        self.session = session
        self.api_url = api_url
        self._catalogue: list[Reciter] = []
        self._expires_at = datetime.min.replace(tzinfo=timezone.utc)
        self.raw_unique_reader_count = 0

    async def _fetch_language(self, language: str) -> dict[str, Any]:
        parts = urlsplit(self.api_url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["language"] = language
        localized_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        timeout = aiohttp.ClientTimeout(total=20)
        async with self.session.get(localized_url, timeout=timeout) as response:
            response.raise_for_status()
            return await response.json(content_type=None)

    async def catalogue(self, force_refresh: bool = False) -> list[Reciter]:
        now = datetime.now(timezone.utc)
        if self._catalogue and not force_refresh and now < self._expires_at:
            return self._catalogue

        results = await asyncio.gather(
            self._fetch_language("ar"),
            self._fetch_language("en"),
            return_exceptions=True,
        )
        payloads = [result for result in results if isinstance(result, dict)]
        if not payloads:
            error = next((result for result in results if isinstance(result, BaseException)), None)
            raise RuntimeError("تعذر تحميل قائمة القرّاء من المزود حالياً.") from error

        # Merge English then Arabic, so localized Arabic names win, and merge all editions.
        merged: dict[int, dict[str, Any]] = {}
        for payload in reversed(payloads):
            for raw_reciter in payload.get("reciters", []):
                try:
                    reciter_id = int(raw_reciter["id"])
                except (KeyError, TypeError, ValueError):
                    continue
                existing = merged.setdefault(reciter_id, {"moshaf": []})
                if str(raw_reciter.get("name", "")).strip():
                    existing["name"] = str(raw_reciter["name"]).strip()
                known_keys = {
                    self._edition_key(str(item.get("server", "")).strip(), str(item.get("surah_list", "")).strip())
                    for item in existing["moshaf"]
                }
                for moshaf in raw_reciter.get("moshaf") or []:
                    server = str(moshaf.get("server", "")).strip()
                    surah_list = str(moshaf.get("surah_list", "")).strip()
                    key = self._edition_key(server, surah_list)
                    if key in known_keys:
                        for index, previous in enumerate(existing["moshaf"]):
                            if self._edition_key(str(previous.get("server", "")).strip(), str(previous.get("surah_list", "")).strip()) == key:
                                if len(str(moshaf.get("name", ""))) > len(str(previous.get("name", ""))):
                                    existing["moshaf"][index] = dict(moshaf)
                                break
                    else:
                        existing["moshaf"].append(dict(moshaf))
                        known_keys.add(key)

        self.raw_unique_reader_count = len(merged)
        reciters: list[Reciter] = []
        for reciter_id, raw_reciter in merged.items():
            name = str(raw_reciter.get("name", "")).strip()
            for moshaf in raw_reciter.get("moshaf", []):
                server = str(moshaf.get("server", "")).strip()
                available = str(moshaf.get("surah_list", ""))
                try:
                    surahs = frozenset(int(value) for value in available.split(",") if value.strip())
                except ValueError:
                    continue
                if not (name and surahs and self._safe_stream_base(server)):
                    continue
                edition_id = self._edition_key(server, available)
                reciters.append(
                    Reciter(
                        id=reciter_id,
                        name=name,
                        moshaf_name=str(moshaf.get("name") or "مصحف صوتي"),
                        server=server,
                        surahs=surahs,
                        edition_id=edition_id,
                    )
                )

        if not reciters:
            raise RuntimeError("لم تُرجع خدمة القرّاء أي مصاحف صالحة للتشغيل.")
        self._catalogue = sorted(reciters, key=lambda reader: (reader.name.casefold(), reader.id, reader.moshaf_name.casefold()))
        self._expires_at = now + timedelta(hours=12)
        if any(isinstance(result, BaseException) for result in results):
            logging.warning("One localized reciter catalogue was unavailable; using the successful source response.")
        return self._catalogue

    @staticmethod
    def _edition_key(server: str, surah_list: str) -> str:
        normalized = f"{server.rstrip('/')}|{','.join(sorted(value.strip().zfill(3) for value in surah_list.split(',') if value.strip()))}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    async def editions_for(self, reciter_id: int) -> list[Reciter]:
        return [reader for reader in await self.catalogue() if reader.id == reciter_id]

    async def find(self, reciter_id: int, edition_id: str | None = None) -> Reciter | None:
        editions = await self.editions_for(reciter_id)
        if edition_id is not None:
            return next((edition for edition in editions if edition.edition_id == str(edition_id)), None)
        return editions[0] if editions else None

    async def find_edition(self, edition_id: str) -> Reciter | None:
        return next((edition for edition in await self.catalogue() if edition.edition_id == edition_id), None)

    async def search(self, query: str = "", limit: int | None = None) -> list[Reciter]:
        normalized = query.casefold().strip()
        all_editions = await self.catalogue()
        unique: dict[int, Reciter] = {}
        for edition in all_editions:
            if normalized and normalized not in edition.name.casefold():
                continue
            unique.setdefault(edition.id, edition)
        readers = sorted(unique.values(), key=lambda reader: (reader.name.casefold(), reader.id))
        return readers[:limit] if limit else readers

    @property
    def edition_count(self) -> int:
        return len(self._catalogue)

    @staticmethod
    def _safe_stream_base(value: str) -> bool:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        return parsed.scheme == "https" and bool(parsed.netloc)
