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
GROAN_PATH = SFX_DIR / "groan.wav"
LAUGH_PATH = SFX_DIR / "laugh.wav"
AMBIENT_PATH = SFX_DIR / "ambient_bed.wav"


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


def render_outro_card(output_path: str, cta_text: str | None = None):
    """Render the 1.0s end card. Auto-wraps long CTAs across 2-3 lines.
    Always shows @dadjokefix below the CTA for brand."""
    img = Image.new("RGB", (SHORT_W, SHORT_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    cta_text = (cta_text or "FOLLOW for daily groans").upper()
    cta_font = find_font(115, "ExtraBold")
    handle_font = find_font(65, "SemiBold")

    # Wrap CTA so long ones (e.g. "RATE THAT JOKE / 1-10") fit cleanly
    inner_w = SHORT_W - 120
    lines = wrap_text(draw, cta_text, cta_font, inner_w)
    line_h = int(cta_font.size * 1.1)
    total_h = line_h * len(lines)

    cur_y = (SHORT_H - total_h) // 2 - 80
    for line in lines:
        draw_text_block(
            draw, line,
            font=cta_font,
            box=(60, cur_y, inner_w, line_h),
            fill=ACCENT_COLOR,
        )
        cur_y += line_h

    draw_text_block(
        draw, "@dadjokefix",
        font=handle_font,
        box=(60, cur_y + 40, inner_w, 80),
        fill=TEXT_COLOR,
    )

    img.save(output_path, "PNG")
    log(f"  Outro card: {output_path}")


def _draw_stroked_text(draw, text, pos, font, fill, stroke_fill, stroke_w):
    """Draw text with a thick outline — TikTok / MrBeast caption style."""
    x, y = pos
    # Pillow 9.2+ has stroke_width; fall back to manual offset stroking otherwise.
    try:
        draw.text(pos, text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=stroke_fill)
    except TypeError:
        for dx in range(-stroke_w, stroke_w + 1):
            for dy in range(-stroke_w, stroke_w + 1):
                if dx or dy:
                    draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
        draw.text(pos, text, font=font, fill=fill)


def render_caption_overlay(text: str, output_path: str, style: str = "setup"):
    """Transparent PNG with TikTok-style stroked text — no boxes, big bold,
    thick black outline so it pops on any background.

    style:
      'setup'     = white text, black stroke (top of frame)
      'punchline' = yellow text, black stroke (top of frame, slightly larger)
    """
    img = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if style == "punchline":
        font_size = 118
        text_fill = ACCENT_COLOR
        stroke_w = 10
    else:
        font_size = 100
        text_fill = TEXT_COLOR
        stroke_w = 9

    font = find_font(font_size, "ExtraBold")
    inner_w = SHORT_W - 80   # leaves 40px margin each side
    lines = wrap_text(draw, text, font, inner_w)

    line_spacing = int(font.size * 0.18)
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + line_spacing * (len(lines) - 1)

    # Anchor near the top of the frame, below the platform UI safe area
    cur_y = 200

    for line, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        line_x = (SHORT_W - line_w) // 2
        _draw_stroked_text(draw, line, (line_x, cur_y), font, text_fill, (0, 0, 0), stroke_w)
        cur_y += lh + line_spacing

    img.save(output_path, "PNG")


HOOK_BANNERS = [
    "WAIT FOR IT",
    "BRACE YOURSELF",
    "DAD JOKE INCOMING",
    "TRY NOT TO GROAN",
    "THIS GOT ME",
    "GET READY",
    "LISTEN UP",
    "HEAR ME OUT",
    "WORTH THE WAIT",
]


def render_hook_banner(output_path: str, text: str | None = None):
    """First-1.2-second attention grabber. Bright pill-shape banner with hook text.
    Picks a random text from HOOK_BANNERS if not specified — variety across runs
    helps the algorithm: same viewers don't see identical openers twice."""
    import random
    img = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    text = text or random.choice(HOOK_BANNERS)
    font = find_font(80, "ExtraBold")
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 50, 26

    box_w = text_w + pad_x * 2
    box_h = text_h + pad_y * 2
    box_x = (SHORT_W - box_w) // 2
    box_y = SHORT_H - box_h - 360   # bottom-third, well above platform UI

    # Yellow pill with a slim navy outline
    bg_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    bg_draw.rounded_rectangle(
        [box_x - 6, box_y - 6, box_x + box_w + 6, box_y + box_h + 6],
        radius=box_h, fill=(*BG_COLOR, 230),
    )
    bg_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=box_h, fill=(*ACCENT_COLOR, 250),
    )
    img = Image.alpha_composite(img, bg_layer)
    draw = ImageDraw.Draw(img)
    draw.text((box_x + pad_x, box_y + pad_y - 6), text, font=font, fill=(20, 20, 30))

    img.save(output_path, "PNG")


def _composite_broll_card(image_path: str, output_path: str):
    """Open the b-roll image, scale + crop to 720x540, frame in a yellow border,
    composite on a transparent canvas at the upper-third position. Drop shadow
    for separation from background."""
    card_w, card_h = 720, 540
    border = 8
    pos_x = (SHORT_W - card_w) // 2
    pos_y = 380   # upper-third — well above Hank's face

    canvas = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    src = Image.open(image_path).convert("RGB")
    # Cover-fit the source into card_w x card_h
    src_ratio = src.width / src.height
    target_ratio = card_w / card_h
    if src_ratio > target_ratio:
        new_h = card_h
        new_w = int(card_h * src_ratio)
    else:
        new_w = card_w
        new_h = int(card_w / src_ratio)
    src = src.resize((new_w, new_h), Image.LANCZOS)
    crop_x = (new_w - card_w) // 2
    crop_y = (new_h - card_h) // 2
    src = src.crop((crop_x, crop_y, crop_x + card_w, crop_y + card_h))

    # Drop shadow
    shadow = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        [pos_x + 12, pos_y + 16, pos_x + card_w + 12, pos_y + card_h + 16],
        radius=20, fill=(0, 0, 0, 140),
    )
    canvas = Image.alpha_composite(canvas, shadow)

    # Yellow border behind the image
    border_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border_layer)
    border_draw.rounded_rectangle(
        [pos_x - border, pos_y - border, pos_x + card_w + border, pos_y + card_h + border],
        radius=22, fill=(*ACCENT_COLOR, 255),
    )
    canvas = Image.alpha_composite(canvas, border_layer)

    # Paste image
    canvas.paste(src, (pos_x, pos_y))
    canvas.save(output_path, "PNG")


def render_handle_watermark(output_path: str):
    """Small persistent @dadjokefix handle bottom-left — brand watermark that
    travels with screenshots and re-uploads."""
    img = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    handle = "@dadjokefix"
    font = find_font(38, "ExtraBold")
    bbox = draw.textbbox((0, 0), handle, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 18, 10

    box_x = 36
    box_y = SHORT_H - 36 - text_h - pad_y * 2 - 40   # 40px above bottom platform UI

    bg_layer = Image.new("RGBA", (SHORT_W, SHORT_H), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg_layer)
    bg_draw.rounded_rectangle(
        [box_x, box_y, box_x + text_w + pad_x * 2, box_y + text_h + pad_y * 2],
        radius=12, fill=(0, 0, 0, 165),
    )
    img = Image.alpha_composite(img, bg_layer)
    draw = ImageDraw.Draw(img)
    draw.text((box_x + pad_x, box_y + pad_y - 4), handle, font=font, fill=ACCENT_COLOR)

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
    outro_text: str | None = None,
    broll_image_path: str | None = None,
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
    hook_png = os.path.join(work_dir, "hook_banner.png")
    handle_png = os.path.join(work_dir, "handle_watermark.png")

    render_outro_card(outro_png, cta_text=outro_text)
    render_caption_overlay(joke["setup"], setup_png, style="setup")
    render_caption_overlay(joke["punchline"], punch_png, style="punchline")
    render_episode_counter_overlay(episode, counter_png)
    render_hook_banner(hook_png)
    render_handle_watermark(handle_png)
    # Punchline flash overlay — full-screen yellow tint at 25% alpha for 150ms
    flash_png = os.path.join(work_dir, "punch_flash.png")
    flash_img = Image.new("RGBA", (SHORT_W, SHORT_H), (*ACCENT_COLOR, 64))
    flash_img.save(flash_png, "PNG")

    # B-roll image — placed in the upper third with a yellow border + drop shadow,
    # shown for ~1.5s in the middle of the setup. Visual breakup of the talking
    # head, helps short-form retention.
    have_broll = broll_image_path and Path(broll_image_path).exists()
    broll_card = None
    if have_broll:
        broll_card = os.path.join(work_dir, "broll_card.png")
        _composite_broll_card(broll_image_path, broll_card)

    # Caption windows
    setup_show_until = setup_end + 0.1            # tiny overlap into pause for readability
    punch_show_from = punchline_start

    # Rim-shot fires right as the punchline lands (small offset for comedic timing).
    # Groan + laugh layer in 0.3s after the rim shot — perceived professionalism jump.
    rimshot_at_ms = int(max(0, punchline_end - 0.05) * 1000)
    groan_at_ms = rimshot_at_ms + 300
    laugh_at_ms = rimshot_at_ms + 400   # overlaps slightly with groan — feels like a real audience

    have_rimshot = RIMSHOT_PATH.exists()
    have_groan = GROAN_PATH.exists()
    have_laugh = LAUGH_PATH.exists()
    have_ambient = AMBIENT_PATH.exists()
    if not have_rimshot:
        log(f"  WARNING: rim-shot SFX not found at {RIMSHOT_PATH}, skipping")

    # Inputs:
    #  [0] avatar MP4 (with audio)
    #  [1] outro PNG
    #  [2] setup caption PNG
    #  [3] punchline caption PNG
    #  [4] episode counter PNG
    #  [5] silent audio for outro
    #  [6] hook banner PNG (first ~1.2s)
    #  [7] handle watermark PNG (persistent)
    #  [8] punchline flash PNG (yellow tint, 150ms at punchline reveal)
    #  [9+] reaction SFX (rim/groan/laugh/ambient) — indices shift based on what exists
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
        # Punchline yellow flash — 150ms at the moment the joke lands.
        # Goes BEHIND the punchline caption so the text reads cleanly.
        f"[av1][8:v]overlay=0:0:enable='between(t,{punch_show_from:.3f},{punch_show_from + 0.15:.3f})'[av_flash];"
        f"[av_flash][3:v]overlay=0:0:enable='between(t,{punch_show_from:.3f},{avatar_dur:.3f})'[av2];"
        f"[av2][4:v]overlay=0:0[av_with_counter];"
        # Hook banner — first 1.4s only, kicks the FYP scroll
        f"[av_with_counter][6:v]overlay=0:0:enable='between(t,0.15,1.4)'[av_with_hook];"
        # Persistent @dadjokefix watermark for the entire video
        f"[av_with_hook][7:v]overlay=0:0[av_with_brand];"
    )

    # B-roll card overlay (input [9]) during the middle of the setup.
    # Window: from (setup_end - 2.0) to (setup_end - 0.3) — plays for ~1.7s
    # right before the punchline pause. Visual breakup of the talking head.
    if have_broll:
        broll_start = max(1.5, setup_end - 2.0)
        broll_end = max(broll_start + 1.0, setup_end - 0.3)
        filter_video += (
            f"[av_with_brand][9:v]overlay=0:0"
            f":enable='between(t,{broll_start:.3f},{broll_end:.3f})'[av_with_brand2];"
        )
        final_video_label = "av_with_brand2"
    else:
        final_video_label = "av_with_brand"

    filter_video += (
        f"[1:v]scale={SHORT_W}:{SHORT_H},setsar=1,format=yuv420p[outro_v];"
    )

    # Audio mix: layer reaction SFX on top of the HeyGen voice track.
    # Each SFX sits well under the voice so the joke never gets drowned out.
    # Indexing of SFX inputs is dynamic based on which files exist:
    #   base inputs end at [5] (silent audio for outro)
    #   [6] = rim shot (if present)
    #   [7] = groan     (if rim shot + groan both present)
    #   [8] = laugh     (if all three present; otherwise index shifts)
    audio_layers = []
    # 0=avatar, 1=outro, 2=setup, 3=punch, 4=counter, 5=silent, 6=hook,
    # 7=handle, 8=flash, [9=broll if present], audio inputs start after.
    next_input = 10 if have_broll else 9
    if have_rimshot:
        audio_layers.append((next_input, rimshot_at_ms, 0.45, "rim"))
        next_input += 1
    if have_groan:
        audio_layers.append((next_input, groan_at_ms, 0.22, "grn"))
        next_input += 1
    if have_laugh:
        audio_layers.append((next_input, laugh_at_ms, 0.18, "lgh"))
        next_input += 1
    if have_ambient:
        # Ambient pad starts at t=0, low volume — pure atmosphere under the voice.
        audio_layers.append((next_input, 0, 0.16, "amb"))
        next_input += 1

    if audio_layers:
        parts = []
        mix_inputs = ["0:a"]
        for idx, delay_ms, vol, tag in audio_layers:
            parts.append(
                f"[{idx}:a]adelay={delay_ms}|{delay_ms},"
                f"aformat=sample_rates=44100:channel_layouts=stereo,volume={vol}[{tag}_d];"
            )
            mix_inputs.append(f"{tag}_d")
        amix_str = "".join(f"[{m}]" for m in mix_inputs)
        filter_audio = (
            "".join(parts)
            + f"{amix_str}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0:normalize=0,"
            + "alimiter=limit=0.95:attack=3:release=50,"
            + "aformat=sample_rates=44100:channel_layouts=stereo[av_a];"
        )
    else:
        filter_audio = "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[av_a];"

    filter_complex = (
        filter_video
        + filter_audio
        + f"[{final_video_label}][av_a][outro_v][5:a]concat=n=2:v=1:a=1[outv][outa]"
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
        "-i", hook_png,        # [6]
        "-i", handle_png,      # [7]
        "-i", flash_png,       # [8]
    ]
    if have_broll:
        cmd += ["-i", broll_card]   # [9]
    if have_rimshot:
        cmd += ["-i", str(RIMSHOT_PATH)]
    if have_groan:
        cmd += ["-i", str(GROAN_PATH)]
    if have_laugh:
        cmd += ["-i", str(LAUGH_PATH)]
    if have_ambient:
        cmd += ["-i", str(AMBIENT_PATH)]
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
