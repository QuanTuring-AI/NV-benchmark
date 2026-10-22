#!/usr/bin/env python3
"""Vol.5 · a test image with Chinese text, made here so that an OCR smoke test has a known answer.

The text is two opening articles of public statutes of Taiwan (statutes are not subject to copyright there), a line of
digits and Latin letters, and a short table-like line. It is rendered in black on white at a size a scanned page would
have (about 150 dpi for A5), with the open font Noto Sans TC. The text is written beside the image as the expected
answer; an OCR result can then be scored by how many of these characters it returns.

usage: make_zh_test_image.py --font FILE.ttf --out-dir DIR      (writes zh_statute_text.png and zh_statute_text.txt)
"""
import argparse, hashlib, json, os

from PIL import Image, ImageDraw, ImageFont, __version__ as pil_version

LINES = [
    "著作權法 第一條",
    "為保障著作人著作權益，調和社會公共利益，",
    "促進國家文化發展，特制定本法。",
    "本法未規定者，適用其他法律之規定。",
    "",
    "個人資料保護法 第一條",
    "為規範個人資料之蒐集、處理及利用，",
    "以避免人格權受侵害，並促進個人資料之合理利用，",
    "特制定本法。",
    "",
    "Article 1 · 2026-10-04 · NT$ 1,234,567 · 98.6%",
    "項目 數量 單位：公噸 二氧化碳當量 12,345.67",
]

ap = argparse.ArgumentParser(); ap.add_argument("--font", required=True); ap.add_argument("--out-dir", required=True)
ap.add_argument("--size", type=int, default=34)
a = ap.parse_args()
font = ImageFont.truetype(a.font, a.size)
W, H, margin, step = 1240, 874, 70, int(a.size * 1.75)
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)
y = margin
for line in LINES:
    d.text((margin, y), line, font=font, fill="black")
    y += step
os.makedirs(a.out_dir, exist_ok=True)
png = os.path.join(a.out_dir, "zh_statute_text.png"); txt = os.path.join(a.out_dir, "zh_statute_text.txt")
img.save(png, optimize=False)
open(txt, "w", encoding="utf-8", newline="\n").write("\n".join(LINES) + "\n")
chars = [c for line in LINES for c in line if not c.isspace()]
print(json.dumps({"image": os.path.basename(png), "bytes": os.path.getsize(png), "sha256": hashlib.sha256(open(png, "rb").read()).hexdigest(),
                  "size": [W, H], "font": os.path.basename(a.font), "font_size": a.size, "pillow": pil_version,
                  "lines": sum(1 for l in LINES if l), "characters_without_spaces": len(chars), "cjk_characters": sum(1 for c in chars if "一" <= c <= "鿿")}))
