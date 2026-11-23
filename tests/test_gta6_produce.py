import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gta6 import produce as p
import gta6_cloud as cloud


def example():
    return {'suitable': True, 'rotation_clockwise': 0, 'title': 'Look at the background',
            'caption': 'A closer look at the crowd in this fan edit.', 'beats': [
        {'start': 0, 'text': 'Look past the main character in this shot and watch what the people in the background are doing.', 'evidence': 'Visible crowd'},
        {'start': 3, 'text': 'Their different movements give the scene a busy feeling, rather than making everyone seem like part of the same animation.', 'evidence': 'Different movements'},
        {'start': 7, 'text': 'That is what catches my eye here. Which small background detail stood out most to you?', 'evidence': 'Background'}]}


class ProductionTests(unittest.TestCase):
    def test_tiktok_rejection_does_not_block_other_destinations_or_repeat_completed_uploads(self):
        clip={'id':'123','title':'Commentary','caption':'Caption'}
        for existing in ({},{'tiktok':{'status':'accepted'},'instagram':{'status':'published','url':'https://www.instagram.com/reel/example/'}}):
            with tempfile.TemporaryDirectory() as folder, patch.object(cloud,'OUT',Path(folder)), \
                 patch.object(cloud,'save_issue'), patch.object(cloud,'youtube_cli_enabled',return_value=True), \
                 patch.object(cloud,'youtube_cli_upload',return_value={'status':'published'}) as youtube, \
                 patch.object(cloud,'instagram_cli_upload',return_value={'status':'published'}) as instagram, \
                 patch.object(cloud,'tiktok_cli_upload',side_effect=RuntimeError('status_code=5')) as tiktok:
                row={'delivery':copy.deepcopy(existing)}
                cloud.complete_publication(282,row,clip,Path('commentary.mp4'),266,{'items':[clip]})
                youtube.assert_called_once()
                if existing:
                    tiktok.assert_not_called();instagram.assert_not_called()
                else:
                    instagram.assert_called_once()
                    self.assertEqual(row['delivery']['tiktok']['status'],'rejected')

    def test_prepared_preview_must_come_from_successful_main_workflow(self):
        import json
        run={'conclusion':'success','head_branch':'untrusted','head_repository':{'full_name':'owner/repo'},'path':'.github/workflows/gta6-cloud.yml'}
        with patch.dict(p.os.environ,{'GITHUB_REPOSITORY':'owner/repo'}), patch.object(p,'command',return_value=json.dumps(run)) as command:
            with self.assertRaises(p.Rejected):p.load_prepared({},'123',Path('unused'))
            self.assertEqual(command.call_count,1)

    def test_invalid_draft_gets_only_one_bounded_correction(self):
        bad=example();bad['beats'][0]['text']='Too short.'
        with tempfile.TemporaryDirectory() as folder, patch.object(p,'generate',side_effect=[bad,example()]) as generate:
            result=p.plan_story(Path('source.mp4'),{'title':'Fan edit','creator':'example'},'test',30,Path(folder))
            self.assertEqual(result,example())
            self.assertEqual(generate.call_count,2)
        with tempfile.TemporaryDirectory() as folder, patch.object(p,'generate',return_value=bad) as generate:
            with self.assertRaises(p.Rejected):
                p.plan_story(Path('source.mp4'),{'title':'Fan edit','creator':'example'},'test',30,Path(folder))
            self.assertEqual(generate.call_count,2)

    def test_commentary_selection_skips_sources_too_short_for_narration(self):
        from datetime import datetime
        short={'status':'ready','source':'short','sha256':'a','creator':'one','priority':1,'duration_seconds':9}
        long=dict(short,source='long',sha256='b',creator='two',priority=2,duration_seconds=30)
        with patch.dict(cloud.os.environ,{'GTA6_COMMENTARY_ENABLED':'true'}):
            selected,_=cloud.select_clip({'items':[short,long]},[],datetime(2026,11,22,17,tzinfo=cloud.TZ))
        self.assertEqual(selected,long)

    def test_plan_requires_source_grounded_three_beat_script_and_real_shot_bounds(self):
        plan = example()
        self.assertGreaterEqual(len(p.validate_plan(plan, 30).split()), 50)
        for change in ({'suitable': False}, {'rotation_clockwise': 45},
                       {'title': '{\\pos(0,0)}'}, {'beats': plan['beats'][:2]}):
            with self.subTest(change=change), self.assertRaises(p.Rejected):
                p.validate_plan(dict(plan, **change), 30)
        bad = copy.deepcopy(plan); bad['beats'][0]['start'] = float('nan')
        with self.assertRaises(p.Rejected): p.validate_plan(bad, 30)
        bad['beats'][0]['start'] = 29
        with self.assertRaises(p.Rejected): p.validate_plan(bad, 30)

    def test_final_review_rejects_sideways_media_and_missing_or_wrong_actual_speech(self):
        script = p.validate_plan(example(), 30)
        verdict = {k: True for k in ('pass','upright','captions_readable','claims_supported','narration_clear_complete')}
        verdict.update(issues=[], heard_text=script)
        p.validate_qa(verdict, script)
        for change in ({'upright': False}, {'issues': ['cut off ending']},
                       {'heard_text': 'Something entirely different'}, {'narration_clear_complete': 'true'}):
            with self.subTest(change=change), self.assertRaises(p.Rejected):
                p.validate_qa(dict(verdict, **change), script)

    def test_caption_times_use_actual_alignment_and_keep_creator_credit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = p.subtitles(example(), {'creator':'example'}, [{'start':1.27,'end':2.89,'text':'Look behind the character'}], 25, Path(folder))
            text = path.read_text()
        self.assertIn('0:00:01.27,0:00:02.89,Caption', text)
        self.assertIn('Footage: @example', text)
        self.assertIn('AI voice', text)

    def test_failed_commentary_never_falls_back_to_raw_repost(self):
        with patch.dict(cloud.os.environ, {'GTA6_COMMENTARY_ENABLED':'true'}), \
             patch.object(cloud,'source_media',return_value=Path('source.mp4')), \
             patch.object(cloud,'model_name',return_value='test'), \
             patch.object(p,'produce',side_effect=p.Rejected('sideways')), \
             patch.object(cloud,'run') as raw_render:
            with self.assertRaises(p.Rejected): cloud.materialize({'id':'123'})
            raw_render.assert_not_called()

    def test_output_metadata_replaces_raw_title_and_records_production_provenance(self):
        clip={'id':'123','title':'Raw repost','caption':'Old'}
        manifest={'title':'Original observation','caption':'New commentary','version':p.VERSION}
        with patch.dict(cloud.os.environ, {'GTA6_COMMENTARY_ENABLED':'true'}), \
             patch.object(cloud,'source_media',return_value=Path('source.mp4')), \
             patch.object(cloud,'model_name',return_value='test'), \
             patch.object(p,'produce',return_value=(Path('commentary.mp4'),manifest)):
            self.assertEqual(cloud.materialize(clip),Path('commentary.mp4'))
        self.assertEqual(clip['title'],manifest['title'])
        self.assertEqual(clip['production'],manifest)


if __name__ == '__main__': unittest.main()
