"""Previewable archival story format v2: grounded shots and phrase captions."""
import math
from pathlib import Path
import re
import subprocess

import clipping

FORMAT_VERSION = 'archive-story-v2'
SAFE_LEFT, SAFE_RIGHT, SAFE_TOP, SAFE_BOTTOM = 96, 888, 160, 1580


def phrase_segments(text, starts, ends):
    if len(starts) != len(text) or len(ends) != len(text):
        raise ValueError('Caption alignment length mismatch')
    words = list(re.finditer(r'\S+', text))
    segments, group = [], []
    for word in words:
        candidate = group + [word]
        value = text[candidate[0].start():candidate[-1].end()]
        # A character count alone cannot guarantee that whole words pack into two rows.
        try:
            caption_lines(value)
            fits = True
        except ValueError:
            fits = False
        if group and (not fits or len(value) > 52 or starts[word.start()] - ends[group[-1].end()-1] > .35):
            segments.append(make_segment(text, group, starts, ends))
            group = []
        if not group:
            caption_lines(word.group())  # Oversized individual words still fail closed.
        group.append(word)
        if re.search(r'[.!?,;:]$|[—–]$', word.group()):
            segments.append(make_segment(text, group, starts, ends))
            group = []
    if group:
        segments.append(make_segment(text, group, starts, ends))
    balanced = []
    for segment in segments:
        if balanced and len(segment['text'].split()) == 1 and segment['start']-balanced[-1]['end'] < .35 and not re.search(r'[.!?,;:]$', balanced[-1]['text']):
            combined = balanced[-1]['text'] + ' ' + segment['text']
            try:
                caption_lines(combined)
            except ValueError:
                previous = [w for w in words if starts[w.start()] >= balanced[-1]['start'] and ends[w.end()-1] <= balanced[-1]['end']]
                current = [w for w in words if starts[w.start()] == segment['start']]
                if len(previous) > 3 and current:
                    shortened = make_segment(text, previous[:-2], starts, ends)
                    tail = make_segment(text, previous[-2:] + current, starts, ends)
                    try:
                        caption_lines(shortened['text'])
                        caption_lines(tail['text'])
                    except ValueError:
                        pass  # Keep the valid single-word tail rather than overflow a row.
                    else:
                        balanced[-1], segment = shortened, tail
            else:
                balanced[-1].update(text=combined, end=segment['end'])
                continue
        balanced.append(segment)
    return balanced


def make_segment(text, group, starts, ends):
    start, end = starts[group[0].start()], ends[group[-1].end()-1]
    if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end:
        raise ValueError('Invalid phrase caption time')
    return {'start': start, 'end': end, 'text': text[group[0].start():group[-1].end()]}


def caption_lines(text, max_chars=29):
    words = text.split()
    if any(len(word) > max_chars for word in words):
        raise ValueError('Caption word exceeds safe width')
    lines, current = [], ''
    for word in words:
        if current and len(current + ' ' + word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = (current + ' ' + word).strip()
    if current:
        lines.append(current)
    if len(lines) > 2:
        # Balance two rows without splitting a word; grouping is bounded upstream.
        possibilities = [(' '.join(words[:i]), ' '.join(words[i:])) for i in range(1, len(words))]
        possibilities = [p for p in possibilities if max(map(len, p)) <= max_chars]
        if not possibilities:
            raise ValueError('Caption phrase exceeds two safe lines')
        lines = list(min(possibilities, key=lambda p: abs(len(p[0])-len(p[1]))))
    return lines


def shot_filter(width, height, reframe=None):
    reframe = reframe or {'zoom': 1, 'x': .5}
    if not isinstance(reframe,dict) or set(reframe)-{'zoom','x'}:
        raise ValueError('Invalid framing settings')
    zoom, center = reframe.get('zoom', 1), reframe.get('x', .5)
    if isinstance(zoom,bool) or isinstance(center,bool) or not isinstance(zoom,(int,float)) or not isinstance(center,(int,float)):
        raise ValueError('Framing must use finite numeric values')
    if not math.isfinite(zoom) or not 1 <= zoom <= 1.2 or not 0 <= center <= 1:
        raise ValueError('Only reviewed modest horizontal reframing allowed')
    crop_width = int(width / zoom) // 2 * 2
    x = int((width - crop_width) * center) // 2 * 2
    return (f'crop={crop_width}:{height}:{x}:0,'
            'scale=1080:1000:force_original_aspect_ratio=decrease:force_divisible_by=2,'
            'pad=1080:1920:(ow-iw)/2:340:color=0x101826,setsar=1')


def write_captions(path, segments, duration, source, headline="WHY ARE THE\nCABINETS FLYING?"):
    header = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,96,192,490,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines = []
    last = 0
    for segment in segments:
        if not last <= segment['start'] < segment['end'] <= duration + .1:
            raise ValueError('Overlapping/out-of-range phrase captions')
        last = segment['end']
        text = r'\N'.join(clipping.safe_ass(v) for v in caption_lines(segment['text']))
        lines.append(f"Dialogue: 0,{clipping.ass_time(segment['start'])},{clipping.ass_time(segment['end'])},Default,,0,0,0,,{text}")
    for y, size, label in [
            (1482, 21, f"{source['title']} · {source['year']}"),
            (1516, 19, f"{source['creator']} / Prelinger Archives"),
            (1550, 19, 'Original commentary · AI-generated narration')]:
        lines.append(f'Dialogue: 1,0:00:00.00,{clipping.ass_time(duration)},Default,,0,0,0,,{{\\an8\\pos(492,{y})\\fs{size}}}{clipping.safe_ass(label)}')
    hook = r'\N'.join(clipping.safe_ass(line) for line in headline.splitlines())
    lines.append(f'Dialogue: 1,0:00:00.00,0:00:03.00,Default,,0,0,0,,{{\\an8\\pos(492,190)\\fs48}}{hook}')
    Path(path).write_text(header+'\n'.join(lines)+'\n')


def render(source_file, episode, source, directory, audio, duration, segments, boundaries):
    info, source_duration = clipping.probe(source_file)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    directory.mkdir(parents=True, exist_ok=True)
    write_captions(directory/'captions.ass', segments, duration, source, episode['headline'])
    shots = []
    planned = []
    for i, beat in enumerate(episode['beats']):
        remaining = boundaries[i+1]-boundaries[i]
        for cut in beat.get('visual_cuts', [beat]):
            length = cut.get('length', remaining)
            if not 0 < length <= remaining + 1e-6:
                raise ValueError('Visual cut exceeds narration beat')
            planned.append((dict(beat, **cut), length))
            remaining -= length
        if abs(remaining) > .001:
            raise ValueError('Visual cuts do not cover narration beat')
    for i, (beat, length) in enumerate(planned):
        if not 0 < length <= 14 or beat['start']+length > source_duration:
            raise ValueError('Shot exceeds verified source interval')
        name = f'shot-{i}.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(beat['start']),
            '-i',str(Path(source_file).resolve()),'-t',str(length),'-an','-vf',
            shot_filter(video['width'],video['height'],beat.get('reframe')),
            '-r','30','-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p',name],
            cwd=directory,check=True,timeout=300)
        shots.append(f"file '{name}'")
    (directory/'shots.txt').write_text('\n'.join(shots))
    output=directory/'clip.mp4'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','1',
        '-i','shots.txt','-i',str(audio.resolve()),'-map','0:v:0','-map','1:a:0','-t',str(duration),
        '-vf','ass=captions.ass:fontsdir=fonts','-af','loudnorm=I=-16:TP=-1.5:LRA=11',
        '-c:v','libx264','-preset','fast','-crf','21','-pix_fmt','yuv420p','-c:a','aac','-ar','48000','-b:a','160k',
        '-movflags','+faststart',str(output.resolve())],cwd=directory,check=True,timeout=600)
    data,actual=clipping.probe(output)
    final=next(s for s in data['streams'] if s['codec_type']=='video')
    if (final['width'],final['height'])!=(1080,1920) or abs(actual-duration)>.3:
        raise ValueError('Preview output verification failed')
    return output
