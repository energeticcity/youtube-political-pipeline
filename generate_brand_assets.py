"""
Generate Dad Joke Fix brand assets with Pillow.

Outputs (saved to brand/):
- youtube_banner.png        2048x1152 (safe area 1235x338)
- profile_image.png         1024x1024 (TikTok/IG/YouTube profile circle)
- watermark.png             300x300 transparent (YouTube branding watermark)
- dad_avatar_placeholder.jpg 1024x1024 (deliberately a placeholder — swap with real Hank before launch)

Run once: python generate_brand_assets.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).parent / "fonts"
OUT_DIR = Path(__file__).parent / "brand"
OUT_DIR.mkdir(exist_ok=True)

NAVY = (26, 26, 46)
YELLOW = (255, 195, 70)
DARK_TEXT = (20, 20, 30)
WHITE = (255, 255, 255)
LIGHT_NAVY = (40, 40, 70)


def font(size: int, weight: str = "ExtraBold") -> ImageFont.FreeTypeFont:
    candidates = [
        FONTS_DIR / f"Montserrat-{weight}.ttf",
        FONTS_DIR / "Montserrat-ExtraBold.ttf",
        FONTS_DIR / "Montserrat-Bold.ttf",
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def text_size(draw, text, fnt):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered(draw, text, fnt, cx, cy, fill):
    w, h = text_size(draw, text, fnt)
    draw.text((cx - w // 2, cy - h // 2), text, font=fnt, fill=fill)


# ── YouTube banner: 2048x1152, safe area 1235x338 centred ────────────────────

def make_banner():
    W, H = 2048, 1152
    img = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    # Diagonal yellow accent band
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(band)
    band_draw.polygon([
        (W * 0.55, 0),
        (W, 0),
        (W, H * 0.4),
        (W * 0.78, H * 0.4),
    ], fill=(*YELLOW, 60))
    img.paste(Image.alpha_composite(img.convert("RGBA"), band).convert("RGB"))

    # Top + bottom yellow stripes
    draw.rectangle([0, 0, W, 16], fill=YELLOW)
    draw.rectangle([0, H - 16, W, H], fill=YELLOW)

    # Title (centred in safe area)
    cx, cy = W // 2, H // 2

    title_font = font(220, "ExtraBold")
    sub_font = font(72, "Bold")
    times_font = font(56, "SemiBold")

    draw_centered(draw, "DAD JOKE FIX", title_font, cx, cy - 80, YELLOW)
    draw_centered(draw, "TWO DAD JOKES EVERY DAY", sub_font, cx, cy + 60, WHITE)
    draw_centered(draw, "fresh groans  ·  10am + 6pm ET", times_font, cx, cy + 150, YELLOW)

    out = OUT_DIR / "youtube_banner.png"
    img.save(out, "PNG")
    print(f"  {out}")


# ── Profile image: 1024x1024 ──────────────────────────────────────────────────

def make_profile():
    W = 1024
    img = Image.new("RGB", (W, W), YELLOW)
    draw = ImageDraw.Draw(img)

    # Inner navy circle
    margin = 40
    draw.ellipse([margin, margin, W - margin, W - margin], fill=NAVY)

    # Yellow ring
    ring = 18
    draw.ellipse(
        [margin - ring, margin - ring, W - margin + ring, W - margin + ring],
        outline=YELLOW, width=ring,
    )

    # Inner text
    title_font = font(180, "ExtraBold")
    sub_font = font(76, "ExtraBold")

    draw_centered(draw, "DAD", title_font, W // 2, W // 2 - 100, YELLOW)
    draw_centered(draw, "JOKE", title_font, W // 2, W // 2 + 80, YELLOW)
    draw_centered(draw, "FIX", sub_font, W // 2, W // 2 + 240, WHITE)

    out = OUT_DIR / "profile_image.png"
    img.save(out, "PNG")
    print(f"  {out}")


# ── Watermark: 300x300 transparent yellow circle with smile ───────────────────

def make_watermark():
    W = 300
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Yellow circle
    draw.ellipse([10, 10, W - 10, W - 10], fill=(*YELLOW, 240))
    # Inner navy circle
    inner = 30
    draw.ellipse([inner, inner, W - inner, W - inner], fill=(*NAVY, 255))

    # "DJF" monogram
    fnt = font(110, "ExtraBold")
    draw_centered(draw, "DJF", fnt, W // 2, W // 2 - 6, YELLOW)

    out = OUT_DIR / "watermark.png"
    img.save(out, "PNG")
    print(f"  {out}")


# ── Dad avatar placeholder: clearly marked, must be replaced ─────────────────

def make_dad_placeholder():
    W = 1024
    img = Image.new("RGB", (W, W), YELLOW)
    draw = ImageDraw.Draw(img)

    # Stylised face circle
    face_c = (W // 2, int(W * 0.44))
    face_r = int(W * 0.30)
    draw.ellipse(
        [face_c[0] - face_r, face_c[1] - face_r,
         face_c[0] + face_r, face_c[1] + face_r],
        fill=(245, 220, 180),
    )
    # Eyes
    eye_y = face_c[1] - 20
    eye_dx = 90
    for ex in (face_c[0] - eye_dx, face_c[0] + eye_dx):
        draw.ellipse([ex - 18, eye_y - 18, ex + 18, eye_y + 18], fill=DARK_TEXT)
    # Smile
    smile_box = [face_c[0] - 90, face_c[1] + 10, face_c[0] + 90, face_c[1] + 100]
    draw.arc(smile_box, start=20, end=160, fill=DARK_TEXT, width=10)
    # Stubble dots
    for x in range(face_c[0] - 70, face_c[0] + 80, 14):
        draw.ellipse([x - 3, face_c[1] + 95, x + 3, face_c[1] + 101], fill=(120, 100, 80))

    # Warning band
    band_y = int(W * 0.78)
    draw.rectangle([0, band_y, W, band_y + 180], fill=NAVY)
    warn_font = font(64, "ExtraBold")
    sub_font = font(34, "Bold")
    draw_centered(draw, "REPLACE ME", warn_font, W // 2, band_y + 60, YELLOW)
    draw_centered(draw, "swap with real Hank photo before launch", sub_font, W // 2, band_y + 130, WHITE)

    out = OUT_DIR / "dad_avatar_placeholder.jpg"
    img.save(out, "JPEG", quality=92)
    print(f"  {out}")


if __name__ == "__main__":
    print("Generating brand assets...")
    make_banner()
    make_profile()
    make_watermark()
    make_dad_placeholder()
    print(f"Done. See {OUT_DIR}/")
