"""Render a source-cited episode and three narrated Shorts without network calls."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import wave

from PIL import Image, ImageDraw, ImageFont
from piper import PiperVoice

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "fonts" / "Montserrat-Bold.ttf"
WHITE, INK, PANEL = "#f7f7fc", "#121320", "#222437"


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *map(str, args)], check=True)


def fit_lines(draw, text, size, width):
    font = ImageFont.truetype(str(FONT), size)
    lines = [""]
    for word in text.split():
        line = (lines[-1] + " " + word).strip()
        if draw.textlength(line, font=font) <= width:
            lines[-1] = line
        else:
            lines.append(word)
    return font, lines


def text_block(draw, text, origin, size, width, color):
    font, lines = fit_lines(draw, text, size, width)
    x, y = origin
    for index, line in enumerate(lines):
        draw.text((x, y + index * (size + 10)), line, font=font, fill=color)


def card(chapter, line, line_index, folder, vertical):
    width, height = (720, 1280) if vertical else (1280, 720)
    accent = chapter["accent"]
    image = Image.new("RGB", (width, height), INK)
    draw = ImageDraw.Draw(image)
    margin = 68 if vertical else 72
    title_y = 158 if vertical else 102
    text_block(draw, "GTA VI CLIP FIX", (margin, 96 if vertical else 56), 24, 360, accent)
    text_block(draw, chapter["title"], (margin, title_y), 60 if vertical else 57, width - 2 * margin, WHITE)
    active = chapter["highlights"][line_index]
    for index, label in enumerate(chapter["labels"]):
        x, y = (margin, 340 + index * 110) if vertical else (734, 236 + index * 89)
        draw.rounded_rectangle((x, y, width - margin, y + (83 if vertical else 67)), 17,
                               fill=accent if index == active else PANEL)
        text_block(draw, label, (x + 24, y + 21 if vertical else y + 15), 30, width - x - margin - 48,
                   INK if index == active else WHITE)
    text_block(draw, line, (margin, 790 if vertical else 250), 42 if vertical else 40,
               width - margin - (135 if vertical else 605), WHITE)
    y = height - (85 if vertical else 61)
    bar = width - 2 * margin
    draw.rounded_rectangle((margin, y, margin + bar, y + 7), 3, fill=PANEL)
    progress = bar * (line_index + 1) / len(chapter["lines"])
    draw.rounded_rectangle((margin, y, margin + progress, y + 7), 3, fill=accent)
    out = folder / f"card-{line_index:02}.png"
    image.save(out)
    return out


def chapter_audio(chapter, voice, folder):
    frames, durations = [], []
    params = None
    for index, line in enumerate(chapter["lines"]):
        part = folder / f"spoken-{index:02}.wav"
        with wave.open(str(part), "wb") as stream:
            voice.synthesize_wav(line, stream)
        with wave.open(str(part), "rb") as stream:
            params = stream.getparams()
            # Leave a short natural gap for each caption change.
            gap = int(params.framerate * 0.22)
            frames.append(stream.readframes(params.nframes) + bytes(gap * params.sampwidth * params.nchannels))
            durations.append((params.nframes + gap) / params.framerate)
    audio = folder / "speech.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams(params)
        for part in frames:
            stream.writeframes(part)
    return audio, durations


def render_chapter(chapter, audio, times, folder, vertical):
    folder.mkdir(parents=True)
    sequence = []
    for index, (line, duration) in enumerate(zip(chapter["lines"], times, strict=True)):
        frame = card(chapter, line, index, folder, vertical)
        sequence.extend([f"file '{frame.name}'", f"duration {duration:.6f}"])
    sequence.append(sequence[-2])
    timeline = folder / "slides.txt"
    timeline.write_text("\n".join(sequence) + "\n")
    result = folder / "chapter.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", timeline, "-i", audio, "-vf", "fps=30,setsar=1",
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-shortest", "-threads", "2", "-pix_fmt", "yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "48000",
           "-b:a", "128k", "-movflags", "+faststart", result)
    return result


def verify(path, dimensions, minimum, maximum):
    result = subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                      "-of", "json", str(path)])
    info = json.loads(result)
    duration = float(info["format"]["duration"])
    video, audio = info["streams"]
    if (video["width"], video["height"]) != dimensions or video["codec_name"] != "h264":
        raise ValueError(f"Invalid video stream in {path.name}")
    if audio["codec_name"] != "aac" or not minimum <= duration <= maximum:
        raise ValueError(f"Invalid audio or duration in {path.name}: {duration:.1f}s")
    ffmpeg("-xerror", "-i", path, "-f", "null", "-")
    with path.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"filename": path.name, "seconds": round(duration, 2), "dimensions": dimensions,
            "sha256": fingerprint}


def build(spec, model, folder):
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    temp = folder / "work"
    temp.mkdir()
    voice = PiperVoice.load(str(model))
    landscape, shorts = [], []
    chapters = spec["chapters"]
    if sum("short_title" in chapter for chapter in chapters) != 3:
        raise ValueError("The batch needs exactly three distinct Short chapters")
    for index, chapter in enumerate(chapters):
        highlights = chapter["highlights"]
        if len(highlights) != len(chapter["lines"]) or not all(
            isinstance(item, int) and 0 <= item < len(chapter["labels"]) for item in highlights
        ):
            raise ValueError(f"Invalid diagram timing in {chapter['title']}")
        working = temp / f"chapter-{index:02}"
        working.mkdir()
        audio, times = chapter_audio(chapter, voice, working)
        landscape.append(render_chapter(chapter, audio, times, working / "wide", False))
        if "short_title" in chapter:
            output = folder / f"short-{len(shorts) + 1}.mp4"
            render_chapter(chapter, audio, times, working / "vertical", True).replace(output)
            shorts.append({"title": chapter["short_title"], **verify(output, (720, 1280), 20, 60)})
    timeline = temp / "episode.txt"
    timeline.write_text("".join(f"file '{part.relative_to(temp)}'\n" for part in landscape))
    episode = folder / "episode.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", timeline, "-c", "copy", "-movflags", "+faststart", episode)
    manifest = {"id": spec["id"], "title": spec["title"], "description": spec["description"],
                "episode": verify(episode, (1280, 720), 180, 900), "shorts": shorts,
                "sources": spec["sources"], "visuals": "Original diagrams", "voice": "Piper, synthetic",
                "publication_status": "preview"}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (folder / "script.txt").write_text("\n\n".join(
        chapter["title"] + "\n" + " ".join(chapter["lines"]) for chapter in chapters) + "\n")
    shutil.rmtree(temp)
    print(json.dumps({"episode": manifest["episode"], "shorts": shorts}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    build(json.loads(args.spec.read_text()), args.model, args.out)


if __name__ == "__main__":
    main()
