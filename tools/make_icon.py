"""Generate assets/clapoff.ico.

Renders the clapping-hands emoji from the system font onto a warm rounded
square. Falls back to a plain drawn mark if no emoji font is available, because
an icon that fails to build shouldn't fail the release.
"""

import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

ACCENT = (224, 112, 63, 255)
SIZES = [16, 24, 32, 48, 64, 128, 256]
EMOJI_FONTS = [
    r"C:\Windows\Fonts\seguiemj.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
]


def base(size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=ACCENT)
    glyph = None
    for path in EMOJI_FONTS:
        if not pathlib.Path(path).exists():
            continue
        for point in (int(size * 0.58), 109, 96, 64):   # seguiemj wants specific sizes
            try:
                glyph = ImageFont.truetype(path, point)
                break
            except OSError:
                continue
        if glyph:
            break
    if glyph is not None:
        try:
            d.text((size / 2, size / 2 + size * 0.02), "\N{CLAPPING HANDS SIGN}",
                   font=glyph, anchor="mm", embedded_color=True)
            return img
        except Exception:
            pass
    # Fallback: two white sound arcs, which at least reads as "listening".
    for i, r in enumerate((0.20, 0.32, 0.44)):
        box = (size / 2 - size * r, size / 2 - size * r,
               size / 2 + size * r, size / 2 + size * r)
        d.arc(box, start=-55, end=55, fill=(255, 255, 255, 255), width=max(2, size // 22))
    return img


def main():
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "assets/clapoff.ico")
    out.parent.mkdir(parents=True, exist_ok=True)
    art = base(256)
    art.save(out, sizes=[(s, s) for s in SIZES])
    art.save(out.with_suffix(".png"))
    print("wrote", out, "and", out.with_suffix(".png"))


if __name__ == "__main__":
    main()
