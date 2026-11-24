"""Render a source-cited episode and three narrated Shorts without network calls."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "fonts" / "Montserrat-Bold.ttf"
WHITE, INK, PANEL = "#f7f7fc", "#121320", "#222437"
VOICE = "af_heart"
MUSIC = {
    "title": "Electric Dreams",
    "artist": "Scott Buckley",
    "source": "https://www.scottbuckley.com.au/library/electric-dreams/",
    "license": "https://creativecommons.org/licenses/by/4.0/",
    "credit": "Music: ‘Electric Dreams’ by Scott Buckley (www.scottbuckley.com.au), CC BY 4.0.",
    "changes": "Excerpted, faded, and mixed under the narration",
}


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


def card(chapter, line, line_index, folder, vertical, background):
    width, height = (720, 1280) if vertical else (1280, 720)
    accent = chapter["accent"]
    image = Image.new("RGBA", (width, height), (13, 15, 24, 65) if background else INK)
    draw = ImageDraw.Draw(image)
    if background:
        heading = (27, 65, width - 30, 306) if vertical else (48, 40, 1200, 202)
        caption = (34, 780, 638, 1182) if vertical else (45, 224, 700, 615)
        draw.rounded_rectangle(heading, 28, fill=(12, 15, 23, 195))
        draw.rounded_rectangle(caption, 24, fill=(12, 15, 23, 227))
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
    audio = folder / "speech.wav"
    durations = []
    with wave.open(str(audio), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        for line in chapter["lines"]:
            spoken = line.replace("Grand Theft Auto Six", "GTA six")
            samples, rate = voice.create(spoken, voice=VOICE, speed=1.01, lang="en-us")
            if not durations:
                stream.setframerate(rate)
            elif rate != stream.getframerate():
                raise ValueError("Narration sample rate changed within a chapter")
            gap = int(rate * 0.22)
            pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
            stream.writeframes(pcm.tobytes() + bytes(gap * 2))
            durations.append((len(samples) + gap) / rate)
    return audio, durations


def render_chapter(chapter, audio, times, folder, vertical, background, offset):
    folder.mkdir(parents=True)
    sequence = []
    for index, (line, duration) in enumerate(zip(chapter["lines"], times, strict=True)):
        frame = card(chapter, line, index, folder, vertical, background)
        sequence.extend([f"file '{frame.name}'", f"duration {duration:.6f}"])
    sequence.append(sequence[-2])
    timeline = folder / "slides.txt"
    timeline.write_text("\n".join(sequence) + "\n")
    result = folder / "chapter.mp4"
    args = ["-f", "concat", "-safe", "0", "-i", timeline, "-i", audio]
    if background:
        width, height = (720, 1280) if vertical else (1280, 720)
        args += ["-stream_loop", "-1", "-ss", offset, "-i", background, "-filter_complex_threads", "2",
                 "-filter_complex",
                 f"[2:v]fps=30,scale={width}:{height}:force_original_aspect_ratio=increase,"
                 f"crop={width}:{height},setsar=1[bg];[0:v]fps=30,format=rgba[graphics];"
                 "[bg][graphics]overlay=shortest=1[v]", "-map", "[v]"]
    else:
        args += ["-vf", "fps=30,setsar=1", "-map", "0:v:0"]
    ffmpeg(*args, "-map", "1:a:0", "-af", "highpass=f=78,loudnorm=I=-15:TP=-2:LRA=8",
           "-shortest", "-threads", "2", "-pix_fmt", "yuv420p", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-ar", "48000", "-b:a", "128k", result)
    return result


def add_music(video, music, output):
    seconds = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "csv=p=0", str(video)]))
    mix = (
        "[0:a]aformat=channel_layouts=stereo[voice];"
        "[1:a]lowpass=f=5200,loudnorm=I=-29:TP=-9:LRA=8,"
        f"afade=t=in:d=0.35,afade=t=out:st={seconds - 0.9:.3f}:d=0.8[music];"
        "[voice][music]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.84:level=false[audio]"
    )
    ffmpeg("-i", video, "-stream_loop", "-1", "-ss", "34", "-t", seconds, "-i", music,
           "-filter_complex", mix, "-map", "0:v:0", "-map", "[audio]", "-c:v", "copy",
           "-c:a", "aac", "-ar", "48000", "-b:a", "160k", "-movflags", "+faststart", output)


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


def build(spec, model, voices, music, folder, background, background_source):
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    temp = folder / "work"
    temp.mkdir()
    voice = Kokoro(str(model), str(voices))
    offset = 0
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
        landscape.append(render_chapter(chapter, audio, times, working / "wide", False, background, offset))
        if "short_title" in chapter:
            output = folder / f"short-{len(shorts) + 1}.mp4"
            rendered = render_chapter(chapter, audio, times, working / "vertical", True, background, offset)
            add_music(rendered, music, output)
            shorts.append({"title": chapter["short_title"], **verify(output, (720, 1280), 20, 60)})
        offset += sum(times)
    timeline = temp / "episode.txt"
    timeline.write_text("".join(f"file '{part.relative_to(temp)}'\n" for part in landscape))
    episode = folder / "episode.mp4"
    joined = temp / "episode-no-music.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", timeline, "-c", "copy", joined)
    add_music(joined, music, episode)
    manifest = {"id": spec["id"], "title": spec["title"], "description": spec["description"],
                "episode": verify(episode, (1280, 720), 180, 900), "shorts": shorts,
                "sources": spec["sources"], "visuals": "Original diagrams", "voice": f"Kokoro {VOICE}, synthetic",
                "music": MUSIC, "publication_status": "preview"}
    if background:
        manifest["background"] = {"source": background_source, "audio": "muted", "commercial_rights": "unverified"}
    (folder / "credits.txt").write_text(
        f"{MUSIC['credit']} {MUSIC['changes']}.\n{MUSIC['source']}\n{MUSIC['license']}\n"
        + (f"Gameplay background, private preview: {background_source}\n" if background else "")
    )
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (folder / "script.txt").write_text("\n\n".join(
        chapter["title"] + "\n" + " ".join(chapter["lines"]) for chapter in chapters) + "\n")
    shutil.rmtree(temp)
    print(json.dumps({"episode": manifest["episode"], "shorts": shorts}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--voices", required=True, type=Path)
    parser.add_argument("--music", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--background", type=Path)
    parser.add_argument("--background-source")
    args = parser.parse_args()
    if bool(args.background) != bool(args.background_source):
        parser.error("--background and --background-source must be supplied together")
    build(json.loads(args.spec.read_text()), args.model, args.voices, args.music, args.out,
          args.background, args.background_source)


if __name__ == "__main__":
    main()
