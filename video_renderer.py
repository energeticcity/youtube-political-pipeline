#!/usr/bin/env python3
"""
Custom video renderer for The Political Lens YouTube channel.
Generates professional news-style videos with animated text overlays,
background stock footage, and voiceover audio.

Style: Dark overlay on stock footage + bold headline + animated talking point cards
Inspired by: TLDR News, Vox, and top faceless political channels
"""

import os
import math
import json
import struct
import tempfile
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ── Configuration ─────────────────────────────────────────────────────────────

WIDTH = 1920
HEIGHT = 1080
FPS = 30

# Colors
RED_ACCENT = "#CC0000"
DARK_BG = (4, 4, 18)
DARK_OVERLAY = (4, 4, 18, 210)  # 82% opacity
WHITE = (255, 255, 255)
LIGHT_GRAY = (180, 180, 180)
RED_RGB = (204, 0, 0)
CARD_BG = (20, 20, 40, 220)

# Font paths — will search common locations
FONT_DIRS = [
    Path(__file__).parent / "fonts",
    Path.home() / ".fonts",
    Path("/usr/share/fonts/truetype"),
    Path("/usr/local/share/fonts"),
    Path("/sessions/practical-admiring-keller/fonts"),
]


def find_font(name: str) -> str:
    """Find a font file by name across known directories."""
    for d in FONT_DIRS:
        p = d / name
        if p.exists():
            return str(p)
    # Fallback: try the name directly
    return name


FONT_BOLD = find_font("Montserrat-Bold.ttf")
FONT_EXTRABOLD = find_font("Montserrat-ExtraBold.ttf")
FONT_REGULAR = find_font("Montserrat-Regular.ttf")
FONT_SEMIBOLD = find_font("Montserrat-SemiBold.ttf")


# ── MP3 Duration Helper ──────────────────────────────────────────────────────

def get_mp3_duration(mp3_path: str) -> float:
    """Get duration of an MP3 file using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", mp3_path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        # Fallback: estimate from file size (128kbps)
        size = os.path.getsize(mp3_path)
        return size / (128 * 1000 / 8)


# ── Text Wrapping ─────────────────────────────────────────────────────────────

def wrap_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


# ── Frame Generation ──────────────────────────────────────────────────────────

def draw_text_with_shadow(draw, pos, text, font, fill, shadow_color=(0, 0, 0), shadow_offset=3):
    """Draw text with a drop shadow for depth."""
    x, y = pos
    # Draw shadow
    draw.text((x + shadow_offset, y + shadow_offset), text, fill=shadow_color, font=font)
    # Draw main text
    draw.text((x, y), text, fill=fill, font=font)


def draw_rounded_rect(draw, bbox, radius, fill):
    """Draw a rectangle with rounded corners."""
    x1, y1, x2, y2 = bbox
    # Draw main rect
    draw.rectangle([(x1 + radius, y1), (x2 - radius, y2)], fill=fill)
    draw.rectangle([(x1, y1 + radius), (x2, y2 - radius)], fill=fill)
    # Draw four corner circles
    draw.ellipse([(x1, y1), (x1 + 2*radius, y1 + 2*radius)], fill=fill)
    draw.ellipse([(x2 - 2*radius, y1), (x2, y1 + 2*radius)], fill=fill)
    draw.ellipse([(x1, y2 - 2*radius), (x1 + 2*radius, y2)], fill=fill)
    draw.ellipse([(x2 - 2*radius, y2 - 2*radius), (x2, y2)], fill=fill)


def create_gradient_overlay(width, height):
    """Create a vertical gradient overlay (darker at top and bottom, slightly lighter in middle)."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for y in range(height):
        # Stronger at top and bottom, lighter in the middle
        if y < height * 0.3:
            alpha = int(230 - (y / (height * 0.3)) * 40)
        elif y > height * 0.7:
            frac = (y - height * 0.7) / (height * 0.3)
            alpha = int(190 + frac * 40)
        else:
            alpha = 190
        for x in range(width):
            img.putpixel((x, y), (4, 4, 18, alpha))
    return img


def create_gradient_overlay_fast(width, height):
    """Fast gradient overlay using line-by-line drawing."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        if y < height * 0.3:
            alpha = int(230 - (y / (height * 0.3)) * 40)
        elif y > height * 0.7:
            frac = (y - height * 0.7) / (height * 0.3)
            alpha = int(190 + frac * 40)
        else:
            alpha = 190
        draw.line([(0, y), (width, y)], fill=(4, 4, 18, alpha))
    return img


def create_overlay_frame(
    headline: str,
    talking_point: str | None,
    point_number: int,
    channel_name: str = "THE POLITICAL LENS",
    category: str = "POLITICS",
    progress: float = 0.0,
    show_cta: bool = False,
) -> Image.Image:
    """
    Generate a single overlay frame (transparent PNG) with all text elements.
    This will be composited on top of the background video.
    """
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))

    # ── Gradient overlay (more cinematic than flat) ──
    gradient = create_gradient_overlay_fast(WIDTH, HEIGHT)
    img = Image.alpha_composite(img, gradient)
    draw = ImageDraw.Draw(img)

    # ── Top red accent bar (thicker for impact) ──
    draw.rectangle([(0, 0), (WIDTH, 6)], fill=RED_RGB)

    # ── Left red stripe ──
    draw.rectangle([(0, 0), (8, HEIGHT)], fill=RED_RGB)

    # ── Bottom red accent bar ──
    draw.rectangle([(0, HEIGHT - 3), (WIDTH, HEIGHT)], fill=RED_RGB)

    # ── Channel name (top center with letter spacing feel) ──
    try:
        font_channel = ImageFont.truetype(FONT_BOLD, 24)
    except Exception:
        font_channel = ImageFont.load_default()
    # Add dot separators for a broadcast look
    channel_display = " \u2022 ".join(channel_name.split())
    channel_bbox = draw.textbbox((0, 0), channel_display, font=font_channel)
    cw = channel_bbox[2] - channel_bbox[0]
    draw.text(((WIDTH - cw) / 2, 30), channel_display, fill=RED_RGB, font=font_channel)

    # ── Thin line under channel name ──
    line_y = 62
    line_w = 300
    draw.rectangle([((WIDTH - line_w) / 2, line_y), ((WIDTH + line_w) / 2, line_y + 1)], fill=(204, 0, 0, 120))

    # ── Category badge (top left, rounded) ──
    try:
        font_badge = ImageFont.truetype(FONT_EXTRABOLD, 18)
    except Exception:
        font_badge = ImageFont.load_default()
    badge_text = category.upper()
    badge_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    bw = badge_bbox[2] - badge_bbox[0]
    bh = badge_bbox[3] - badge_bbox[1]
    badge_x, badge_y = 50, 85
    draw_rounded_rect(draw,
        (badge_x - 14, badge_y - 8, badge_x + bw + 14, badge_y + bh + 8),
        radius=6, fill=RED_RGB,
    )
    draw.text((badge_x, badge_y), badge_text, fill=WHITE, font=font_badge)

    # ── "BREAKING" / "LIVE" indicator dot (top right) ──
    try:
        font_live = ImageFont.truetype(FONT_SEMIBOLD, 16)
    except Exception:
        font_live = ImageFont.load_default()
    # Red dot
    dot_x = WIDTH - 180
    dot_y = 33
    draw.ellipse([(dot_x, dot_y), (dot_x + 12, dot_y + 12)], fill=RED_RGB)
    draw.text((dot_x + 20, dot_y - 2), "LIVE ANALYSIS", fill=LIGHT_GRAY, font=font_live)

    # ── Main headline (center-left, large bold text with shadow) ──
    try:
        font_headline = ImageFont.truetype(FONT_EXTRABOLD, 68)
    except Exception:
        font_headline = ImageFont.load_default()
    headline_lines = wrap_text(draw, headline.upper(), font_headline, WIDTH - 200)
    headline_y = 180
    for line in headline_lines[:3]:  # Max 3 lines
        draw_text_with_shadow(draw, (60, headline_y), line, font_headline, WHITE, shadow_offset=4)
        line_bbox = draw.textbbox((0, 0), line, font=font_headline)
        headline_y += (line_bbox[3] - line_bbox[1]) + 8

    # ── Red divider line (angled end for dynamism) ──
    divider_y = headline_y + 20
    draw.rectangle([(60, divider_y), (440, divider_y + 5)], fill=RED_RGB)
    # Small gradient fade on the right end
    for i in range(40):
        alpha = int(255 * (1 - i / 40))
        draw.rectangle([(440 + i, divider_y), (441 + i, divider_y + 5)], fill=(204, 0, 0, alpha))

    # ── Talking point card (lower third area) ──
    if talking_point:
        card_y = 680
        card_h = 130
        card_margin = 50

        # Card background with subtle border
        card_bg = Image.new("RGBA", (WIDTH - card_margin * 2, card_h), (15, 15, 35, 230))
        img.paste(card_bg, (card_margin, card_y), card_bg)
        draw = ImageDraw.Draw(img)

        # Top border on card
        draw.rectangle([(card_margin, card_y), (WIDTH - card_margin, card_y + 2)], fill=(204, 0, 0, 150))

        # Point number indicator (larger, more prominent)
        try:
            font_num = ImageFont.truetype(FONT_EXTRABOLD, 44)
        except Exception:
            font_num = ImageFont.load_default()
        num_text = str(point_number)
        num_box_w = 70
        draw.rectangle(
            [(card_margin, card_y), (card_margin + num_box_w, card_y + card_h)],
            fill=RED_RGB,
        )
        num_bbox = draw.textbbox((0, 0), num_text, font=font_num)
        nw = num_bbox[2] - num_bbox[0]
        nh = num_bbox[3] - num_bbox[1]
        draw.text(
            (card_margin + (num_box_w - nw) / 2, card_y + (card_h - nh) / 2 - 5),
            num_text, fill=WHITE, font=font_num,
        )

        # Point text (with shadow)
        try:
            font_point = ImageFont.truetype(FONT_SEMIBOLD, 34)
        except Exception:
            font_point = ImageFont.load_default()
        point_lines = wrap_text(draw, talking_point, font_point, WIDTH - card_margin * 2 - 140)
        py = card_y + 25
        for pl in point_lines[:2]:
            draw_text_with_shadow(draw, (card_margin + 90, py), pl, font_point, WHITE, shadow_offset=2)
            py += 44

        # Point count indicator (e.g., "2 of 4")
        try:
            font_count = ImageFont.truetype(FONT_REGULAR, 16)
        except Exception:
            font_count = ImageFont.load_default()
        count_text = f"POINT {point_number} OF 4"
        count_bbox = draw.textbbox((0, 0), count_text, font=font_count)
        draw.text(
            (WIDTH - card_margin - (count_bbox[2] - count_bbox[0]) - 10, card_y + card_h - 28),
            count_text, fill=LIGHT_GRAY, font=font_count,
        )

    # ── Bottom ticker bar ──
    ticker_y = HEIGHT - 50
    ticker_bg = Image.new("RGBA", (WIDTH, 44), (10, 10, 30, 200))
    img.paste(ticker_bg, (0, ticker_y), ticker_bg)
    draw = ImageDraw.Draw(img)

    try:
        font_ticker = ImageFont.truetype(FONT_REGULAR, 16)
    except Exception:
        font_ticker = ImageFont.load_default()
    # Red "LIVE" tag in ticker
    draw.rectangle([(20, ticker_y + 10), (72, ticker_y + 34)], fill=RED_RGB)
    try:
        font_ticker_tag = ImageFont.truetype(FONT_BOLD, 14)
    except Exception:
        font_ticker_tag = font_ticker
    draw.text((28, ticker_y + 13), "LIVE", fill=WHITE, font=font_ticker_tag)
    draw.text((85, ticker_y + 13), "THE POLITICAL LENS  \u2022  Daily Political Analysis  \u2022  Subscribe for Updates",
              fill=LIGHT_GRAY, font=font_ticker)

    # ── Progress bar (bottom, under ticker) ──
    bar_y = HEIGHT - 6
    bar_width = int(WIDTH * progress)
    draw.rectangle([(0, bar_y), (WIDTH, HEIGHT)], fill=(40, 40, 60))  # Track
    draw.rectangle([(0, bar_y), (bar_width, HEIGHT)], fill=RED_RGB)  # Fill

    # ── CTA (end card) ──
    if show_cta:
        # Darken the entire frame more for CTA
        cta_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (4, 4, 18, 180))
        img = Image.alpha_composite(img, cta_overlay)
        draw = ImageDraw.Draw(img)

        try:
            font_cta = ImageFont.truetype(FONT_EXTRABOLD, 52)
            font_cta_sub = ImageFont.truetype(FONT_REGULAR, 28)
        except Exception:
            font_cta = ImageFont.load_default()
            font_cta_sub = font_cta

        # Large red subscribe box
        box_w, box_h = 700, 80
        box_x = (WIDTH - box_w) / 2
        box_y = HEIGHT / 2 - 80
        draw_rounded_rect(draw, (box_x, box_y, box_x + box_w, box_y + box_h), radius=10, fill=RED_RGB)

        cta_text = "SUBSCRIBE NOW"
        cta_bbox = draw.textbbox((0, 0), cta_text, font=font_cta)
        cta_w = cta_bbox[2] - cta_bbox[0]
        cta_h = cta_bbox[3] - cta_bbox[1]
        draw.text(((WIDTH - cta_w) / 2, box_y + (box_h - cta_h) / 2 - 5), cta_text, fill=WHITE, font=font_cta)

        sub_text = "Daily political analysis you won't find anywhere else"
        sub_bbox = draw.textbbox((0, 0), sub_text, font=font_cta_sub)
        sub_w = sub_bbox[2] - sub_bbox[0]
        draw.text(((WIDTH - sub_w) / 2, box_y + box_h + 25), sub_text, fill=LIGHT_GRAY, font=font_cta_sub)

        # Bell icon hint
        try:
            font_bell = ImageFont.truetype(FONT_SEMIBOLD, 22)
        except Exception:
            font_bell = font_cta_sub
        bell_text = "Hit the bell so you never miss an update"
        bell_bbox = draw.textbbox((0, 0), bell_text, font=font_bell)
        bell_w = bell_bbox[2] - bell_bbox[0]
        draw.text(((WIDTH - bell_w) / 2, box_y + box_h + 70), bell_text, fill=(150, 150, 150), font=font_bell)

    return img


# ── Thumbnail Generation ──────────────────────────────────────────────────────

def render_thumbnail(
    thumb_text: str,
    category: str,
    bg_frame_path: str | None = None,
    output_path: str = "thumbnail.jpg",
) -> str:
    """Generate a YouTube thumbnail (1280x720) — designed for maximum click-through rate."""
    TW, TH = 1280, 720
    img = Image.new("RGBA", (TW, TH), DARK_BG + (255,))

    # If we have a background frame, use it
    if bg_frame_path and os.path.exists(bg_frame_path):
        bg = Image.open(bg_frame_path).convert("RGBA").resize((TW, TH))
        img = Image.alpha_composite(img, bg)

    # Gradient overlay (darker at edges for vignette effect)
    gradient = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(gradient)
    for y in range(TH):
        # Stronger darkness at top and bottom
        if y < TH * 0.15:
            alpha = int(240 - (y / (TH * 0.15)) * 30)
        elif y > TH * 0.85:
            frac = (y - TH * 0.85) / (TH * 0.15)
            alpha = int(210 + frac * 30)
        else:
            alpha = 200
        gdraw.line([(0, y), (TW, y)], fill=(4, 4, 18, alpha))
    img = Image.alpha_composite(img, gradient)
    draw = ImageDraw.Draw(img)

    # Top red bar (thick)
    draw.rectangle([(0, 0), (TW, 8)], fill=RED_RGB)
    # Left stripe
    draw.rectangle([(0, 0), (8, TH)], fill=RED_RGB)
    # Bottom bar
    draw.rectangle([(0, TH - 4), (TW, TH)], fill=RED_RGB)

    # Channel name (top center)
    try:
        font_ch = ImageFont.truetype(FONT_BOLD, 22)
    except Exception:
        font_ch = ImageFont.load_default()
    ch_text = "THE \u2022 POLITICAL \u2022 LENS"
    ch_bbox = draw.textbbox((0, 0), ch_text, font=font_ch)
    draw.text(((TW - (ch_bbox[2] - ch_bbox[0])) / 2, 28), ch_text, fill=RED_RGB, font=font_ch)

    # Category badge (rounded)
    try:
        font_badge = ImageFont.truetype(FONT_EXTRABOLD, 18)
    except Exception:
        font_badge = ImageFont.load_default()
    cat_text = category.upper()
    cat_bbox = draw.textbbox((0, 0), cat_text, font=font_badge)
    cat_w = cat_bbox[2] - cat_bbox[0]
    cat_h = cat_bbox[3] - cat_bbox[1]
    draw_rounded_rect(draw, (30, 70, 30 + cat_w + 24, 70 + cat_h + 14), radius=6, fill=RED_RGB)
    draw.text((42, 77), cat_text, fill=WHITE, font=font_badge)

    # Big thumbnail text — vertically centered, maximum impact
    try:
        font_thumb = ImageFont.truetype(FONT_EXTRABOLD, 130)
    except Exception:
        font_thumb = ImageFont.load_default()
    lines = wrap_text(draw, thumb_text.upper(), font_thumb, TW - 120)
    # Calculate total text height for vertical centering
    total_h = 0
    line_heights = []
    for line in lines[:3]:
        lb = draw.textbbox((0, 0), line, font=font_thumb)
        lh = lb[3] - lb[1]
        line_heights.append(lh)
        total_h += lh + 5
    ty = (TH - total_h) / 2 + 10  # Slightly below center

    for i, line in enumerate(lines[:3]):
        # Strong drop shadow
        draw.text((47, ty + 5), line, fill=(0, 0, 0), font=font_thumb)
        draw.text((45, ty + 3), line, fill=(20, 0, 0), font=font_thumb)
        draw.text((44, ty), line, fill=WHITE, font=font_thumb)
        ty += line_heights[i] + 5

    # Red divider at bottom
    draw.rectangle([(30, TH - 58), (400, TH - 50)], fill=RED_RGB)
    # Fade out on divider
    for i in range(50):
        alpha = int(255 * (1 - i / 50))
        draw.rectangle([(400 + i, TH - 58), (401 + i, TH - 50)], fill=(204, 0, 0, alpha))

    # CTA text
    try:
        font_cta = ImageFont.truetype(FONT_SEMIBOLD, 18)
    except Exception:
        font_cta = ImageFont.load_default()
    draw.text((30, TH - 42), "WATCH FULL BREAKDOWN \u25B6", fill=LIGHT_GRAY, font=font_cta)

    # Save as RGB JPEG
    img = img.convert("RGB")
    img.save(output_path, "JPEG", quality=95)
    return output_path


# ── Main Video Render ─────────────────────────────────────────────────────────

def render_video(
    headline: str,
    talking_points: list[str],
    category: str,
    bg_video_urls: list[str],
    audio_path: str,
    output_path: str = "output.mp4",
    channel_name: str = "THE POLITICAL LENS",
) -> str:
    """
    Render the full video by:
    1. Downloading background videos
    2. Generating overlay frames with Pillow
    3. Compositing everything with FFmpeg
    """
    import requests

    tmpdir = tempfile.mkdtemp(prefix="politicallens_")
    duration = get_mp3_duration(audio_path)
    total_frames = int(duration * FPS)

    print(f"[renderer] Video duration: {duration:.1f}s ({total_frames} frames)")
    print(f"[renderer] Headline: {headline}")
    print(f"[renderer] Category: {category}")

    # ── Step 1: Download or locate background videos ──
    bg_paths = []
    for i, url_or_path in enumerate(bg_video_urls[:3]):
        bp = os.path.join(tmpdir, f"bg_{i}.mp4")
        try:
            if os.path.isfile(url_or_path):
                # Local file path
                import shutil
                shutil.copy2(url_or_path, bp)
                print(f"[renderer] Using local background {i+1}: {url_or_path}")
            else:
                # URL — download it
                print(f"[renderer] Downloading background {i+1}: {url_or_path[:60]}...")
                resp = requests.get(url_or_path, timeout=60, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; PipelineBot/1.0)"
                })
                resp.raise_for_status()
                with open(bp, "wb") as f:
                    f.write(resp.content)
            # Verify file is a real video (at least 10KB)
            if os.path.exists(bp) and os.path.getsize(bp) > 10240:
                bg_paths.append(bp)
                print(f"[renderer] Background {i+1} OK: {os.path.getsize(bp)} bytes")
            else:
                print(f"[renderer] Background {i+1} too small or missing, skipping")
        except Exception as e:
            print(f"[renderer] Background {i+1} download failed: {e}")

    if not bg_paths:
        # Generate a simple dark gradient background as fallback
        print("[renderer] No backgrounds provided, generating dark fallback...")
        fb = os.path.join(tmpdir, "bg_fallback.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c=0x040412:s={WIDTH}x{HEIGHT}:d={int(duration + 5)}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", fb,
        ], capture_output=True, timeout=60)
        bg_paths.append(fb)

    # ── Step 2: Build the background video with crossfades ──
    # Split duration across segments
    segment_duration = duration / len(bg_paths)
    crossfade = min(2.0, segment_duration / 4)

    bg_concat = os.path.join(tmpdir, "bg_concat.mp4")

    if len(bg_paths) == 1:
        # Single video: just loop/trim
        subprocess.run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", bg_paths[0],
            "-t", str(duration), "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
            "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "23", bg_concat,
        ], capture_output=True, timeout=300)
    else:
        # Multiple videos with crossfade transitions
        # First, trim and scale each segment
        trimmed = []
        for i, bp in enumerate(bg_paths):
            tp = os.path.join(tmpdir, f"bg_trimmed_{i}.mp4")
            seg_len = segment_duration + crossfade  # Extra for crossfade overlap
            subprocess.run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", bp,
                "-t", str(seg_len),
                "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT}",
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "23", tp,
            ], capture_output=True, timeout=120)
            trimmed.append(tp)

        # Concatenate with xfade filter
        if len(trimmed) == 2:
            offset1 = segment_duration - crossfade
            subprocess.run([
                "ffmpeg", "-y", "-i", trimmed[0], "-i", trimmed[1],
                "-filter_complex",
                f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset={offset1},format=yuv420p[v]",
                "-map", "[v]", "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", bg_concat,
            ], capture_output=True, timeout=300)
        elif len(trimmed) >= 3:
            offset1 = segment_duration - crossfade
            offset2 = 2 * segment_duration - 2 * crossfade
            subprocess.run([
                "ffmpeg", "-y", "-i", trimmed[0], "-i", trimmed[1], "-i", trimmed[2],
                "-filter_complex",
                f"[0:v][1:v]xfade=transition=fade:duration={crossfade}:offset={offset1}[v01];"
                f"[v01][2:v]xfade=transition=fade:duration={crossfade}:offset={offset2},format=yuv420p[v]",
                "-map", "[v]", "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23", bg_concat,
            ], capture_output=True, timeout=300)

    if not os.path.exists(bg_concat) or os.path.getsize(bg_concat) < 1024:
        # bg_concat failed — regenerate fallback
        print("[renderer] bg_concat missing or empty, generating fallback background...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"color=c=0x040412:s={WIDTH}x{HEIGHT}:d={int(duration + 5)}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", bg_concat,
        ], capture_output=True, timeout=60)
        if not os.path.exists(bg_concat) or os.path.getsize(bg_concat) < 1024:
            raise RuntimeError("Failed to create background video")

    print(f"[renderer] Background video ready: {os.path.getsize(bg_concat)} bytes")

    # ── Step 3: Generate overlay frames ──
    # Instead of frame-by-frame (too slow), generate key overlay images
    # and use FFmpeg to composite them with fade transitions

    # Calculate when each talking point appears
    point_times = []
    if talking_points:
        # Points appear at roughly equal intervals, starting after 15s
        point_gap = (duration - 25) / max(len(talking_points), 1)
        for i in range(len(talking_points)):
            start = 15 + i * point_gap
            end = start + point_gap - 2  # 2s gap between points
            point_times.append((start, end, talking_points[i], i + 1))

    # Generate overlay images for each state
    overlay_paths = []

    # State 1: Headline only (first 15 seconds)
    overlay_intro = create_overlay_frame(
        headline=headline, talking_point=None, point_number=0,
        channel_name=channel_name, category=category, progress=0.0,
    )
    intro_path = os.path.join(tmpdir, "overlay_intro.png")
    overlay_intro.save(intro_path)
    overlay_paths.append(("intro", intro_path, 0, min(15, duration)))

    # States 2-5: Each talking point
    for start, end, point, num in point_times:
        progress = start / duration
        ov = create_overlay_frame(
            headline=headline, talking_point=point, point_number=num,
            channel_name=channel_name, category=category, progress=progress,
        )
        p = os.path.join(tmpdir, f"overlay_point_{num}.png")
        ov.save(p)
        overlay_paths.append((f"point_{num}", p, start, end))

    # State 6: End CTA (last 5 seconds)
    if duration > 20:
        ov_cta = create_overlay_frame(
            headline=headline, talking_point=None, point_number=0,
            channel_name=channel_name, category=category,
            progress=1.0, show_cta=True,
        )
        cta_path = os.path.join(tmpdir, "overlay_cta.png")
        ov_cta.save(cta_path)
        overlay_paths.append(("cta", cta_path, duration - 5, duration))

    print(f"[renderer] Generated {len(overlay_paths)} overlay states")

    # ── Step 4: Composite overlays onto background video using FFmpeg ──
    # Build complex filter to overlay images at specific times
    inputs = ["-i", bg_concat]
    for name, path, start, end in overlay_paths:
        inputs.extend(["-i", path])

    # Build filter chain: overlay each image at its time range
    filter_parts = []
    current_stream = "0:v"

    for idx, (name, path, start, end) in enumerate(overlay_paths):
        input_idx = idx + 1
        out_label = f"v{idx}"
        enable = f"between(t,{start:.1f},{end:.1f})"
        filter_parts.append(
            f"[{current_stream}][{input_idx}:v]overlay=0:0:enable='{enable}'[{out_label}]"
        )
        current_stream = out_label

    filter_complex = ";".join(filter_parts)

    # Final composite video (no audio yet)
    composite_path = os.path.join(tmpdir, "composite.mp4")
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{current_stream}]",
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-r", str(FPS),
        composite_path,
    ]

    print("[renderer] Compositing overlays...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f"[renderer] FFmpeg error: {result.stderr[-500:]}")
        raise RuntimeError("Overlay compositing failed")

    print(f"[renderer] Composite ready: {os.path.getsize(composite_path)} bytes")

    # ── Step 5: Add audio track ──
    print("[renderer] Adding audio track...")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", composite_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ], capture_output=True, timeout=300)

    if not os.path.exists(output_path):
        raise RuntimeError("Final video creation failed")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"[renderer] Final video: {output_path} ({size_mb:.1f} MB)")

    # ── Cleanup temp files ──
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    return output_path


# ── Quick Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Generate a test thumbnail
    print("Generating test thumbnail...")
    render_thumbnail(
        thumb_text="RATES RISE",
        category="economy",
        output_path="/tmp/test_thumbnail.jpg",
    )
    print("Thumbnail saved to /tmp/test_thumbnail.jpg")
