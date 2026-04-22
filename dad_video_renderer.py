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

BG_COLOR = (26, 26, 46)        # dark navy
ACCENT_COLOR = (255, 195, 70)  # warm dad-joke yellow
TEXT_COLOR = (255, 255, 255)

FONTS_DIR = Path(__file__).parent / "fonts"
SFX_DIR = Path(__file__).parent / "sfx"
RIMSHOT_PATH = SFX_DIR / "rimshot.wav"


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
    """Transparent PNG with caption text in a styled box.

    style:
      'setup'     = top, black box / white text
      'punchline' = top, yellow box / black text + glow
      'bait'      = middle, yellow text on dark navy box (comment-bait during pause)
    """
    img = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font_size = 92 if style == "bait" else 78
    font = find_font(font_size, "ExtraBold")

    box_x = 50
    box_w = SHORT_W - 100
    inner_pad = 40

    lines = wrap_text(draw, text, font, box_w - inner_pad * 2)
    line_h = font.size + int(font.size * 0.2)
    text_h = line_h * len(lines)
    box_h = text_h + inner_pad * 2

    if style == "bait":
        box_y = (SHORT_H - box_h) // 2
        box_fill = (*BG_COLOR, 235)
        text_fill = ACCENT_COLOR
    elif style == "punchline":
        box_y = 140
        box_fill = (*ACCENT_COLOR, 250)
        text_fill = (20, 20, 30)
        glow_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_layer)
        glow_draw.rounded_rectangle(
            [box_x - 8, box_y - 8, box_x + box_w + 8, box_y + box_h + 8],
            radius=36, fill=(*ACCENT_COLOR, 80),
        )
        img = Image.alpha_composite(img, glow_layer)
    else:
        box_y = 140
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


def estimate_timeline(joke: dict, avatar_duration: float, catchphrase: str = "") -> dict:
    """Estimate spoken-section timestamps within the avatar video.

    Audio shape: catchphrase + setup + pause + punchline + cta.
    Returns: {setup_end, punchline_start, punchline_end} in seconds.
    """
    catchphrase_chars = max(len(catchphrase), 1)
    setup_chars = max(len(joke["setup"]), 1)
    pause_chars = 5           # "... .." beat between setup and punchline
    punchline_chars = max(len(joke["punchline"]), 1)
    post_punchline_pause = 3  # "..." gap before CTA (lets rim shot play)
    cta_chars = 18            # "Follow for more!"

    total = catchphrase_chars + setup_chars + pause_chars + punchline_chars + post_punchline_pause + cta_chars

    setup_end = avatar_duration * (catchphrase_chars + setup_chars) / total
    punchline_start = avatar_duration * (catchphrase_chars + setup_chars + pause_chars) / total
    punchline_end = avatar_duration * (catchphrase_chars + setup_chars + pause_chars + punchline_chars) / total

    return {
        "setup_end": setup_end,
        "punchline_start": punchline_start,
        "punchline_end": punchline_end,
    }


def render_dad_short(
    avatar_path: str,
    joke: dict,
    output_path: str,
    episode: int = 1,
    catchphrase: str = "",
) -> str:
    """Compose avatar + captions + episode badge + comment-bait + rim-shot SFX + outro."""
    log("Rendering dad joke Short...")

    avatar_dur = get_video_duration(avatar_path)
    timeline = estimate_timeline(joke, avatar_dur, catchphrase)
    setup_end = timeline["setup_end"]
    punchline_start = timeline["punchline_start"]
    punchline_end = timeline["punchline_end"]
    log(
        f"  Avatar {avatar_dur:.2f}s | setup ends {setup_end:.2f}s | "
        f"punchline {punchline_start:.2f}s-{punchline_end:.2f}s | episode #{episode}"
    )

    work_dir = tempfile.mkdtemp(prefix="dadrender_")
    outro_png = os.path.join(work_dir, "outro.png")
    setup_png = os.path.join(work_dir, "setup_caption.png")
    punch_png = os.path.join(work_dir, "punch_caption.png")
    counter_png = os.path.join(work_dir, "counter.png")

    render_outro_card(outro_png)
    render_caption_overlay(joke["setup"], setup_png, style="setup")
    render_caption_overlay(joke["punchline"], punch_png, style="punchline")
    render_episode_counter_overlay(episode, counter_png)

    # Caption windows
    setup_show_until = setup_end + 0.1            # tiny overlap into pause for readability
    punch_show_from = punchline_start

    # Rim-shot fires right as the punchline lands (small offset for comedic timing)
    rimshot_at_ms = int(max(0, punchline_end - 0.05) * 1000)

    have_rimshot = RIMSHOT_PATH.exists()
    if not have_rimshot:
        log(f"  WARNING: rim-shot SFX not found at {RIMSHOT_PATH}, skipping")

    # Inputs:
    #  [0] avatar MP4 (with audio)
    #  [1] outro PNG
    #  [2] setup caption PNG
    #  [3] punchline caption PNG
    #  [4] episode counter PNG
    #  [5] silent audio for outro
    #  [6] rim shot WAV (only if exists)
    #
    # Full-screen avatar: HeyGen returns a square ~1024x1024 video. Scale to
    # 1920 height (becomes 1920x1920 since aspect-preserved), then crop the
    # sides to land at 1080x1920. Hank now fills the entire 9:16 frame.
    #
    # Ken Burns zoom: a gentle 1.0 → ~1.05 zoom over the duration adds motion
    # without distracting from the joke. Implemented via scale with a time
    # expression then a re-center crop.
    #
    # Punchline emphasis: an extra 4% zoom snap kicks in at punchline_start
    # and holds, drawing the eye when the joke lands.
    filter_video = (
        # Step 1: crop the square HeyGen output to fill 9:16
        f"[0:v]scale=-2:{SHORT_H},crop={SHORT_W}:{SHORT_H},setsar=1[av_full];"
        # Step 2: slow Ken Burns + punchline zoom snap, then crop back to fixed size
        f"[av_full]scale="
        f"w='{SHORT_W}*(1+t*0.004+if(gte(t\\,{punch_show_from:.3f})\\,0.04\\,0))'"
        f":h=-2:eval=frame,"
        f"crop={SHORT_W}:{SHORT_H},setsar=1,format=yuv420p[av_kb];"
        f"[av_kb][2:v]overlay=0:0:enable='between(t,0,{setup_show_until:.3f})'[av1];"
        f"[av1][3:v]overlay=0:0:enable='between(t,{punch_show_from:.3f},{avatar_dur:.3f})'[av2];"
        f"[av2][4:v]overlay=0:0[av_with_counter];"
        f"[1:v]scale={SHORT_W}:{SHORT_H},setsar=1,format=yuv420p[outro_v];"
    )

    if have_rimshot:
        # Voice stays at unity gain, rim shot sits under it at ~0.45, then a soft
        # limiter after the mix prevents any clipping when the two signals combine.
        # Input [6] = rim shot.
        filter_audio = (
            f"[6:a]adelay={rimshot_at_ms}|{rimshot_at_ms},"
            f"aformat=sample_rates=44100:channel_layouts=stereo,volume=0.45[rim_d];"
            f"[0:a][rim_d]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            f"alimiter=limit=0.95:attack=3:release=50,"
            f"aformat=sample_rates=44100:channel_layouts=stereo[av_a];"
        )
    else:
        filter_audio = "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[av_a];"

    filter_complex = (
        filter_video
        + filter_audio
        + "[av_with_counter][av_a][outro_v][5:a]concat=n=2:v=1:a=1[outv][outa]"
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
    ]
    if have_rimshot:
        cmd += ["-i", str(RIMSHOT_PATH)]
    cmd += [
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
