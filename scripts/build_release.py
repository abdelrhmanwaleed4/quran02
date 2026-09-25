from __future__ import annotations

from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("/home/ubuntu/rahma-discord-bot.zip")
EXCLUDED_DIRS = {".venv", "__pycache__"}
EXCLUDED_FILES = {".env", "rahma-discord-bot.zip"}

files: list[Path] = []
for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        continue
    if path.name in EXCLUDED_FILES or path.suffix in {".pyc", ".sqlite3"}:
        continue
    if path == ROOT / "MANIFEST.txt":
        continue
    files.append(path)

files = sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())
manifest = ROOT / "MANIFEST.txt"
manifest.write_text("\n".join(path.relative_to(ROOT).as_posix() for path in files + [manifest]) + "\n", encoding="utf-8")
files.append(manifest)
files.sort(key=lambda item: item.relative_to(ROOT).as_posix())

ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, Path("rahma-discord-bot") / path.relative_to(ROOT))

print(f"Release archive: {ARCHIVE}")
print(f"Included files: {len(files)}")
print(f"Archive size: {ARCHIVE.stat().st_size:,} bytes")
