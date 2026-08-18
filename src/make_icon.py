"""One-off: generate the home-screen icon(s) for docs/. Run manually if you
ever want to change the design -- this isn't part of the normal run_all
pipeline."""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(ROOT, "docs")

BG = (30, 30, 36)
ACCENT = (255, 190, 60)


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    text = "SS"
    font_size = int(size * 0.46)
    try:
        font = ImageFont.truetype("segoeuib.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text, fill=ACCENT, font=font)
    return img


if __name__ == "__main__":
    os.makedirs(DOCS_DIR, exist_ok=True)
    make_icon(180).save(os.path.join(DOCS_DIR, "icon-180.png"))
    make_icon(32).save(os.path.join(DOCS_DIR, "favicon.png"))
    print("saved icon-180.png / favicon.png to docs/")
