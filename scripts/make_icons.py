#!/usr/bin/env python3
"""Draw the installable app's icons, so they are reproducible rather than
   pasted in.

   The mark is the one the two approved artifacts use: a rounded square in the
   design system's blue with a serif 'e' on it. The blue is #215FFF, the
   artifacts' own `--accent`, and NOT the darker #1A50E6 that tokens.css
   carries. They are different jobs: the token is text on a white ground and
   has to clear 4.5:1, while this is a white glyph on a blue ground, which is
   the other way round and clears it comfortably.

   Two shapes are drawn for each size:

   - 'any' fills the square, because that is what a browser tab and a
     non-maskable launcher draw.
   - 'maskable' sits inside the safe zone. Android may crop a maskable icon
     to a circle, a squircle or a rounded square of its own choosing, and it
     guarantees only the centre 80%. A mark drawn to the edge loses its
     corners on exactly the devices this app is for, so the maskable one is
     the same mark at 62% on a full-bleed ground.

   Run: python3 scripts/make_icons.py
"""
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFont

BLUE = (33, 95, 255, 255)
WHITE = (255, 255, 255, 255)
OUT = pathlib.Path(__file__).resolve().parent.parent / "web" / "public" / "icons"

# A serif face, because the mark is set in one. Newsreader is not installed on
# a build machine, so these are the system serifs in order of nearness to it.
FACES = [
    "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Baskerville.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
]


def face(px: int) -> ImageFont.FreeTypeFont:
    for path in FACES:
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, px)
    raise SystemExit(
        "no serif face found; add one to FACES. Tried:\n  " + "\n  ".join(FACES))


def mark(size: int, inset: float) -> Image.Image:
    """The mark at `size`, its rounded square occupying `inset` of the canvas."""
    # Transparent behind the 'any' mark, so its rounded corners are corners
    # rather than blue on blue; full bleed behind the maskable one, because a
    # transparent corner there is a white notch after Android crops it.
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0) if inset == 1.0 else BLUE)
    d = ImageDraw.Draw(img)
    side = round(size * inset)
    off = (size - side) // 2
    if inset < 1.0:
        # Full bleed behind, so a circular crop still lands on blue.
        d.rounded_rectangle([off, off, off + side, off + side],
                            radius=round(side * 0.28), fill=BLUE)
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1],
                            radius=round(size * 0.22), fill=BLUE)

    f = face(round(side * 0.62))
    # Centre on the glyph's own ink box, not on its advance width: a serif 'e'
    # sits noticeably left of centre otherwise.
    box = d.textbbox((0, 0), "e", font=f)
    d.text((off + (side - (box[2] - box[0])) / 2 - box[0],
            off + (side - (box[3] - box[1])) / 2 - box[1]),
           "e", font=f, fill=WHITE)
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for size in (192, 512):
        p = OUT / f"icon-{size}.png"
        mark(size, 1.0).save(p)
        written.append(p)
        p = OUT / f"icon-maskable-{size}.png"
        mark(size, 0.62).save(p)
        written.append(p)
    # iOS draws its own rounded corners and never masks, and it composites a
    # transparent icon onto black, so this one is flattened onto the blue.
    p = OUT / "apple-touch-icon.png"
    flat = Image.new("RGBA", (180, 180), BLUE)
    flat.alpha_composite(mark(180, 1.0))
    flat.convert("RGB").save(p)
    written.append(p)

    for p in written:
        print("wrote", p.relative_to(OUT.parent.parent.parent), p.stat().st_size, "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
