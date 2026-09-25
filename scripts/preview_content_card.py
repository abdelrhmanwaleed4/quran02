from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.content_card import render_content_poster

ROOT = Path(__file__).resolve().parents[1]
duas = json.loads((ROOT / "data" / "duas.json").read_text(encoding="utf-8"))
item = duas["istikharah"]["items"][0]
image = render_content_poster(
    "دعاء الاستخارة",
    [(item["title"], item["text"], item["source"])],
)
output = ROOT / "rahma-dua-preview.png"
output.write_bytes(image.getvalue())
print(output)
