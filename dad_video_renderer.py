"""
Dad Joke video renderer.

Takes a D-ID avatar MP4 (square, with audio baked in) and produces a 1080x1920
vertical Short. Opens directly on the dad's face (no intro card — first 0.5s
must be the hook on TikTok/IG), overlays setup + punchline captions with the
punchline styled in brand yellow for visual impact, shows a persistent
"JOKE #N" counter in the corner, then a 1.0s follow-prompt outro.
"""

import os
import json
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


SHORT_W, SHORT_H = 1080, 1920
OUTRO_DURATION = 1.0
PAUSE_PADDING = 0.5  # seconds the setup caption stays up after setup audio ends

BG_COLOR = (26, 26, 46)        # dark navy
ACCENT_COLOR = (255, 195, 70)  # warm dad-joke yellow
TEXT_COLOR = (255, 255, 255)

FONTS_DIR = Path(__file__).parent / "fonts"


def log(msg: str):
    print(f"[renderer] {msg}", flush=True)


def find_font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    candidates = [
        FONTS_DIR / f"Montserrat-{weight}.ttf",
        FONTS_DIR / "Montserrat-ExtraBold.ttf",
        FONTS_DIR / "Montserrat-Bold.ttf",
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", video_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def wrap_text(draw: ImageDraw.Draw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_text_block(
    draw: ImageDraw.Draw,
    text: str,
    font: ImageFont.FreeTypeFont,
    box: tuple[int, int, int, int],
    fill: tuple = TEXT_COLOR,
    align: str = "center",
    shadow: bool = True,
) -> int:
    x, y, w, h = box
    lines = wrap_text(draw, text, font, w)

    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    line_spacing = int(font.size * 0.25)
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
    cur_y = y + max(0, (h - total_h) // 2) if h > 0 else y

    for line, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        if align == "center":
            line_x = x + (w - line_w) // 2
        elif align == "right":
            line_x = x + w - line_w
        else:
            line_x = x

        if shadow:
            for off in (3, 4):
                draw.text((line_x + off, cur_y + off), line, font=font, fill=(0, 0, 0))
        draw.text((line_x, cur_y), line, font=font, fill=fill)
        cur_y += lh + line_spacing

    return cur_y


def render_outro_card(output_path: str):
    img = Image.new("RGB", (SHORT_W, SHORT_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = find_font(150, "ExtraBold")
    sub_font = find_font(85, "Bold")
    handle_font = find_font(60, "SemiBold")

    draw_text_block(
        draw, "FOLLOW",
        font=title_font,
        box=(60, SHORT_H // 2 - 320, SHORT_W - 120, 180),
        fill=ACCENT_COLOR,
    )
    draw_text_block(
        draw, "for 2 dad jokes",
        font=sub_font,
        box=(60, SHORT_H // 2 - 100, SHORT_W - 120, 110),
        fill=TEXT_COLOR,
    )
    draw_text_block(
        draw, "every day",
        font=sub_font,
        box=(60, SHORT_H // 2 + 40, SHORT_W - 120, 110),
        fill=TEXT_COLOR,
    )
    draw_text_block(
        draw, "@dadjokefix",
        font=handle_font,
        box=(60, SHORT_H // 2 + 220, SHORT_W - 120, 80),
        fill=ACCENT_COLOR,
    )

    img.save(output_path, "PNG")
    log(f"  Outro card: {output_path}")


def render_caption_overlay(text: str, output_path: str, style: str = "setup"):
    """Transparent PNG with caption text in a colored box at the top of the screen.

    style: 'setup' = black box / white text; 'punchline' = yellow box / black text.
    """
    img = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = find_font(78, "ExtraBold")

    box_x = 50
    box_w = SHORT_W - 100
    inner_pad = 40

    lines = wrap_text(draw, text, font, box_w - inner_pad * 2)
    line_h = font.size + int(font.size * 0.2)
    text_h = line_h * len(lines)
    box_h = text_h + inner_pad * 2

    box_y = 140

    if style == "punchline":
        box_fill = (*ACCENT_COLOR, 250)
        text_fill = (20, 20, 30)
        # subtle glow border for the punchline reveal
        glow_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.rounded_rectangle(
            [box_x - 8, box_y - 8, box_x + box_w + 8, box_y + box_h + 8],
            radius=36, fill=(*ACCENT_COLOR, 80),
        )
        img = Image.alpha_composite(img, glow_layer)
    else:
        box_fill = (0, 0, 0, 210)
        text_fill = TEXT_COLOR

    bg_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    bg_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=30,
        fill=box_fill,
    )
    img = Image.alpha_composite(img, bg_layer)
    draw = ImageDraw.Draw(img)

    draw_text_block(
        draw, text,
        font=font,
        box=(box_x + inner_pad, box_y + inner_pad, box_w - inner_pad * 2, text_h),
        fill=text_fill,
        shadow=False,
    )

    img.save(output_path, "PNG")


def render_episode_counter_overlay(episode: int, output_path: str):
    """Small persistent corner badge: 'JOKE #N'. Burned across the whole video."""
    img = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = find_font(42, "ExtraBold")
    text = f"JOKE #{episode}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 24, 14

    box_w = text_w + pad_x * 2
    box_h = text_h + pad_y * 2
    margin = 40
    box_x = SHORT_W - box_w - margin
    box_y = margin + 60  # leave room for platform top UI

    bg_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    bg_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=18,
        fill=(*ACCENT_COLOR, 235),
    )
    img = Image.alpha_composite(img, bg_layer)
    draw = ImageDraw.Draw(img)
    draw.text((box_x + pad_x, box_y + pad_y - 4), text, font=font, fill=(20, 20, 30))

    img.save(output_path, "PNG")


def estimate_setup_end_time(joke: dict, avatar_duration: float, catchphrase: str = "") -> float:
    """Estimate when the setup audio finishes within the avatar video.

    Audio shape: catchphrase + setup + pause + punchline + cta.
    """
    catchphrase_chars = max(len(catchphrase), 1)
    setup_chars = max(len(joke["setup"]), 1)
    punchline_chars = max(len(joke["punchline"]), 1)
    cta_chars = 40  # "Two dad jokes every day, follow for more!"
    pause_chars = 8  # the "... ... ..." between setup and punchline

    total = catchphrase_chars + setup_chars + pause_chars + punchline_chars + cta_chars
    pre_punchline = catchphrase_chars + setup_chars + pause_chars / 2

    setup_end = avatar_duration * (pre_punchline / total) + PAUSE_PADDING
    return min(max(setup_end, 1.5), avatar_duration - 1.5)


def render_dad_short(
    avatar_path: str,
    joke: dict,
    output_path: str,
    episode: int = 1,
    catchphrase: str = "",
) -> str:
    """Compose avatar + captions + episode badge + outro into a 1080x1920 MP4."""
    log("Rendering dad joke Short...")

    avatar_dur = get_video_duration(avatar_path)
    setup_end = estimate_setup_end_time(joke, avatar_dur, catchphrase)
    log(f"  Avatar duration: {avatar_dur:.2f}s, setup ends at {setup_end:.2f}s, episode #{episode}")

    work_dir = tempfile.mkdtemp(prefix="dadrender_")
    outro_png = os.path.join(work_dir, "outro.png")
    setup_png = os.path.join(work_dir, "setup_caption.png")
    punch_png = os.path.join(work_dir, "punch_caption.png")
    counter_png = os.path.join(work_dir, "counter.png")

    render_outro_card(outro_png)
    render_caption_overlay(joke["setup"], setup_png, style="setup")
    render_caption_overlay(joke["punchline"], punch_png, style="punchline")
    render_episode_counter_overlay(episode, counter_png)

    bg_hex = f"0x{BG_COLOR[0]:02x}{BG_COLOR[1]:02x}{BG_COLOR[2]:02x}"

    # Inputs:
    #  [0] avatar MP4 (with audio)
    #  [1] outro PNG
    #  [2] setup caption PNG
    #  [3] punchline caption PNG
    #  [4] episode counter PNG
    #  [5] silent audio for outro
    filter_complex = (
        f"[0:v]scale={SHORT_W}:{SHORT_H}:force_original_aspect_ratio=decrease,"
        f"pad={SHORT_W}:{SHORT_H}:(ow-iw)/2:(oh-ih)/2:color={bg_hex},"
        f"setsar=1,format=yuv420p[av_padded];"
        f"[av_padded][2:v]overlay=0:0:enable='between(t,0,{setup_end:.3f})'[av1];"
        f"[av1][3:v]overlay=0:0:enable='between(t,{setup_end:.3f},{avatar_dur:.3f})'[av2];"
        f"[av2][4:v]overlay=0:0[av_with_counter];"
        f"[1:v]scale={SHORT_W}:{SHORT_H},setsar=1,format=yuv420p[outro_v];"
        f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo[av_a];"
        f"[av_with_counter][av_a][outro_v][5:a]concat=n=2:v=1:a=1[outv][outa]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", avatar_path,
        "-loop", "1", "-t", str(OUTRO_DURATION), "-i", outro_png,
        "-i", setup_png,
        "-i", punch_png,
        "-i", counter_png,
        "-f", "lavfi", "-t", str(OUTRO_DURATION),
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-r", "30",
        output_path,
    ]

    log(f"  Running ffmpeg ({len(cmd)} args)...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"  ffmpeg stderr (last 2000 chars):\n{result.stderr[-2000:]}")
        raise RuntimeError(f"ffmpeg failed with code {result.returncode}")

    log(f"  Short rendered: {output_path}")
    return output_path


def render_thumbnail(thumb_text: str, joke: dict, output_path: str, episode: int = 1) -> str:
    """1280x720 YouTube thumbnail with the teaser text and episode badge."""
    log("Rendering thumbnail...")
    W, H = 1280, 720
    img = Image.new("RGB", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 14], fill=ACCENT_COLOR)
    draw.rectangle([0, H - 14, W, H], fill=ACCENT_COLOR)

    title_font = find_font(180, "ExtraBold")
    sub_font = find_font(60, "Bold")
    badge_font = find_font(48, "ExtraBold")

    draw_text_block(
        draw, thumb_text or "DAD JOKE",
        font=title_font,
        box=(60, 180, W - 120, 250),
        fill=ACCENT_COLOR,
    )
    draw_text_block(
        draw, "fresh dad joke daily",
        font=sub_font,
        box=(60, 470, W - 120, 80),
        fill=TEXT_COLOR,
    )

    # Episode badge top-right
    badge_text = f"#{episode}"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = bbox[2] - bbox[0] + 40
    badge_h = bbox[3] - bbox[1] + 24
    bx = W - badge_w - 40
    by = 50
    draw.rounded_rectangle([bx, by, bx + badge_w, by + badge_h], radius=14, fill=ACCENT_COLOR)
    draw.text((bx + 20, by + 6), badge_text, font=badge_font, fill=(20, 20, 30))

    img.save(output_path, "JPEG", quality=90)
    log(f"  Thumbnail: {output_path}")
    return output_path
