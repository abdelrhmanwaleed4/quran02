from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for filename in ("duas.json", "azkar.json"):
    data = json.loads((ROOT / "data" / filename).read_text(encoding="utf-8"))
    print(filename)
    for key, group in data.items():
        items = group.get("items", [])
        longest = max((len(str(item.get("text", ""))) for item in items), default=0)
        print(f"  {key}: items={len(items)}, longest_text_chars={longest}")
