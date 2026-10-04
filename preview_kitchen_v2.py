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
    is_bart=os.environ.get('EPISODE')=='bart-private-test'
    fixture = json.loads(Path('tests/fixtures/bart-private.json' if is_bart else 'tests/fixtures/kitchen-preview-v2.json').read_text())
    source, episode = fixture['source'], fixture['episode']
    archive.validate_catalog({'version':1,'sources':[source],'episodes':[episode]})
    directory=Path('clip-output').resolve();directory.mkdir(exist_ok=True)
    evidence=archive.check_rights(source)
    media=directory/'source.mp4'
    clipping.download(f"https://archive.org/download/{source['archive_id']}/{source['filename']}",media,max_bytes=262144000)
    if clipping.file_hash(media)!=source['sha256']:raise ValueError('Source fingerprint mismatch')
    model=fill.choose_model(fill.policy())
    shot_starts={b['start'] for b in episode['beats']} | {cut['start'] for b in episode['beats'] for cut in b.get('visual_cuts',[])}
    selected=sorted({round(start+offset,2) for start in shot_starts for offset in [0,2,4,9,13]})
    if len(selected)>fill.policy()['scan_frames']:raise ValueError('Private review exceeds existing frame budget')
    context = ('Verify the 1967 date and BART identity from metadata. Actual source shows a Transbay tube section sliding into water, floating with two circular ends, a tug and bay construction. The original source transcript describes building sections on land, launching, towing and lowering them to form a link between Oakland and San Francisco. This short describes the film’s construction plan, not completed 1967 train service. Reject any unsupported claim or unsuitable content. ' if is_bart else 'The space/orbit language is an explicit metaphor for the swirling dream animation, not a claim of real flight. Verify the 1957 date, diagram, kitchen reveal, visible stove, swirling cabinets and final booklet. Full source runtime is 797.16 seconds; thirteen minutes refers to the source. ')
    review=fill.generate_json(model,fill.policy()['policy']+'\nIndependently audit this private preview against metadata, script and actual source frames. '+context+' Return JSON {pass:boolean,issues:[string]}.',
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
