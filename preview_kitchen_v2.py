"""One branch-only, private test of the checked 1957 kitchen source."""
import json
import os
from pathlib import Path
import shutil

import archive_pipeline as archive
import archive_autofill as fill
import archive_story_style as style
import clipping


def main():
    if os.environ.get('GITHUB_REF') == 'refs/heads/main':
        raise ValueError('This test is private branch-preview only')
    fixture = json.loads(Path('tests/fixtures/kitchen-preview-v2.json').read_text())
    source, episode = fixture['source'], fixture['episode']
    archive.validate_catalog({'version':1,'sources':[source],'episodes':[episode]})
    directory=Path('clip-output').resolve();directory.mkdir(exist_ok=True)
    evidence=archive.check_rights(source)
    media=directory/'source.mp4'
    clipping.download(f"https://archive.org/download/{source['archive_id']}/{source['filename']}",media,max_bytes=262144000)
    if clipping.file_hash(media)!=source['sha256']:raise ValueError('Source fingerprint mismatch')
    model=fill.choose_model(fill.policy())
    selected=sorted({round(b['start']+offset,2) for b in episode['beats'] for offset in [0,4,9,13]})
    review=fill.generate_json(model,fill.policy()['policy']+'''\nIndependently audit this proposed private preview against metadata and actual source frames.
The flying-saucer/orbit language is an explicit metaphor in this promotional dream, not a claim of real flight.
Verify the 1957 date, floor-plan/walking-path diagram, kitchen reveal, swirling cabinets and final planning booklet.
Reject misleading claims or unsuitable footage. Return JSON {pass:boolean,issues:[string]}.''',
        [{'text':json.dumps({'source':evidence,'proposed_story':episode})}]+fill.frames(media,selected,directory))
    if review!={'pass':True,'issues':[]}:raise ValueError('Editorial review rejected private preview')
    # Retain exact character timings, then group natural phrases instead of six-word chunks.
    original=archive.script(episode)
    audio,duration,unused,boundaries=archive.narration(episode,directory)
    alignment=json.loads((directory/'narration-alignment.json').read_text())
    segments=style.phrase_segments(original,alignment['starts'],alignment['ends'])
    shutil.copytree('fonts',directory/'fonts',dirs_exist_ok=True)
    output=style.render(media,episode,source,directory,audio,duration,segments,boundaries)
    metadata={'preview_only':True,'format_version':style.FORMAT_VERSION,'episode':episode,'source':source,
              'rights_live':evidence,'editorial_review':review,'duration':duration,
              'video_sha256':clipping.file_hash(output),'caption_segments':segments,'shot_boundaries':boundaries}
    (directory/'preview-validation.json').write_text(json.dumps(metadata,indent=2))
    (directory/'script.txt').write_text(original+'\n')
    # Raw source/evidence images are not needed in the deliverable artifact.
    media.unlink()
    for p in directory.glob('frame-*.jpg'):p.unlink()
    for p in directory.glob('shot-*.mp4'):p.unlink()
    print(f'Private preview complete: {duration:.2f}s; no publication or production reservation.')


if __name__=='__main__':main()
