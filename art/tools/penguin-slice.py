"""Slice the generated green-screen sprite sheets into keyed animation strips.

Usage: python penguin-slice.py <sheets-dir> [out-dir]
  sheets-dir  the raw 1536 x 1024 sheets, one <name>.png per animation (kept
              outside the repository; see ../README.md)
  out-dir     where the strips and manifest.json go
              (default: ../../penguin_companion/anim)
Needs Pillow.
"""
import json
import os
import sys
from PIL import Image, ImageFilter

if len(sys.argv) < 2:
    sys.exit(__doc__)
SHEETS = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "penguin_companion", "anim")
os.makedirs(OUT, exist_ok=True)

# name: (cols, rows, fps, loop, scale)
# scale is the display scale that keeps the penguin one size on screen, matched
# by standing height against `idle` (peek by head width).
SPEC = {
    "walk": (4, 2, 10, True, 1.0),
    "idle": (3, 2, 5, True, 1.0),
    "peek": (3, 2, 4, False, 0.47),
    "talk": (3, 2, 8, True, 1.0),
    "wave": (3, 2, 7, True, 1.0),
    "think": (3, 2, 4, True, 1.0),
    "hop": (3, 2, 9, True, 1.13),
    "sleep": (3, 2, 3, True, 1.0),
    "charge": (3, 2, 9, True, 1.17),
    "alert": (3, 2, 8, True, 1.05),
    "turn": (3, 2, 6, False, 1.0),
    "beam": (3, 2, 8, False, 1.0),
}
FRAME_H = 240  # output frame height in px (2x for ~120 px on screen)


def key_image(img):
    px = img.load()
    w, h = img.size
    out = Image.new("RGBA", (w, h))
    op = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y][:3]
            dom = g - max(r, b)
            if g > 90 and dom > 55:
                op[x, y] = (0, 0, 0, 0)
            elif g > 70 and dom > 16:
                a = max(0, min(255, int(255 * (1 - (dom - 16) / 39))))
                op[x, y] = (r, max(r, b), b, a)
            else:
                op[x, y] = (r, g, b, 255)
    alpha = out.getchannel("A").filter(ImageFilter.MedianFilter(3))
    out.putalpha(alpha)
    return out


manifest = {}
for name, (cols, rows, fps, loop, display_scale) in SPEC.items():
    src = os.path.join(SHEETS, f"{name}.png")
    sheet = Image.open(src).convert("RGB")
    keyed = key_image(sheet)
    W, H = keyed.size
    cw, ch = W / cols, H / rows
    raw = []
    for r in range(rows):
        for c in range(cols):
            box = (round(c * cw), round(r * ch), round((c + 1) * cw), round((r + 1) * ch))
            raw.append((r, keyed.crop(box)))
    # Align rows: the generator places each row at its own height, so shift every row
    # so its lowest point (feet, or the peek cut line) and its mean centre match row 0.
    def bbox_of(img):
        return img.getchannel("A").point(lambda v: 255 if v > 48 else 0).getbbox()
    rows_bb = {}
    for r, cell in raw:
        bb = bbox_of(cell)
        if bb:
            rows_bb.setdefault(r, []).append(bb)
    ref_bottom = max(b[3] for b in rows_bb[0])
    ref_cx = sum((b[0] + b[2]) / 2 for b in rows_bb[0]) / len(rows_bb[0])
    shift = {}
    for r, bbs in rows_bb.items():
        bottom = max(b[3] for b in bbs)
        cx = sum((b[0] + b[2]) / 2 for b in bbs) / len(bbs)
        shift[r] = (round(ref_cx - cx), round(ref_bottom - bottom))
    M = 60  # canvas margin so shifted content never clips
    cells = []
    for r, cell in raw:
        dx, dy = shift.get(r, (0, 0))
        canvas = Image.new("RGBA", (cell.width + 2 * M, cell.height + 2 * M), (0, 0, 0, 0))
        canvas.paste(cell, (M + dx, M + dy), cell)
        cells.append(canvas)
    # One shared crop for the whole animation keeps motion (bob, hop) relative to the cell.
    union = None
    for cell in cells:
        bb = cell.getchannel("A").point(lambda v: 255 if v > 48 else 0).getbbox()
        if bb is None:
            continue
        union = bb if union is None else (min(union[0], bb[0]), min(union[1], bb[1]), max(union[2], bb[2]), max(union[3], bb[3]))
    pad = 6
    cw0, ch0 = cells[0].size
    union = (max(0, union[0] - pad), max(0, union[1] - pad), min(cw0, union[2] + pad), min(ch0, union[3] + pad))
    frames = [cell.crop(union) for cell in cells]
    fw0, fh0 = frames[0].size
    scale = FRAME_H / fh0
    fw = max(1, round(fw0 * scale))
    strip = Image.new("RGBA", (fw * len(frames), FRAME_H), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.paste(f.resize((fw, FRAME_H), Image.LANCZOS), (i * fw, 0))
    path = os.path.join(OUT, f"{name}.png")
    strip.save(path, optimize=True)
    manifest[name] = {"frames": len(frames), "w": fw, "h": FRAME_H, "fps": fps, "loop": loop, "scale": display_scale}
    print(name, len(frames), fw, FRAME_H, os.path.getsize(path))

with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=1)
print("sheet size", W, H)
