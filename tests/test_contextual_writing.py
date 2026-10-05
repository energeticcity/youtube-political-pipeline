import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive_autofill as fill
import clipping


class ContextualWritingTests(unittest.TestCase):
    def source(self):
        return {'id':'archive-example','title':'A machine demonstration','creator':'Factory studio','year':'1937',
                'description':'Factory footage','subjects':['Industry'],'sha256':'a'*64}

    def story(self):
        starts=fill.contextual_shots(180,30)
        texts=['Why does this machine need so many moving parts to perform a task that looks surprisingly ordinary at first?',
               'The camera follows workers through the process, showing separate stages rather than a single magic device doing everything alone.',
               'Those moving parts connect the stages together, turning the opening spectacle into a practical demonstration of how this factory works.']
        return {'suitable':True,'title':'A surprisingly complicated machine','headline':'WHY SO MANY PARTS?',
                'beats':[{'start':s,'text':t,'evidence':'The camera visibly shows these workers and machine parts.'} for s,t in zip(starts,texts)]}

    def test_temporal_source_frames_stay_bounded_and_offer_three_distinct_options(self):
        for duration in (90,180,1800):
            starts=fill.contextual_shots(duration,30)
            self.assertGreaterEqual(len(starts),3)
            self.assertLessEqual(len(starts)*len(fill.SHOT_OFFSETS),30)
            self.assertEqual(len(starts),len(set(starts)))
            self.assertTrue(all(0<=s<=duration-14 for s in starts))
            self.assertTrue(all(s+13<duration for s in starts))
        with self.assertRaises(ValueError):fill.contextual_shots(180,8)

    @patch('clipping.probe',return_value=({},180))
    @patch('archive_autofill.generate_json')
    @patch('archive_autofill.frames')
    def test_writer_sees_later_shot_context_before_draft_without_extra_model_call(self,frames,generate,probe):
        frames.side_effect=lambda media,times,directory,*args:[{'text':f'actual frame {time}'} for time in times]
        generate.side_effect=[self.story(),{'pass':True,'issues':[],'reason_codes':[]}]
        with tempfile.TemporaryDirectory() as tmp:
            episode,checks=fill.make_story(self.source(),Path(tmp)/'source.mp4',fill.policy(),'test',Path(tmp),[])
        parts=generate.call_args_list[0].args[2]
        self.assertIn({'text':'actual frame 9.0'},parts)
        self.assertIn({'text':'actual frame 18.0'},parts)
        writer_batches=frames.call_args_list[:7]
        self.assertEqual(sum(len(c.args[1]) for c in writer_batches),28)
        self.assertEqual(generate.call_count,2)
        # Extra diagnostic schema cannot invalidate the strict existing publisher proof.
        self.assertEqual(checks['review'],{'pass':True,'issues':[]})
        self.assertEqual(checks['sampling_version'],'temporal-context-v1')
        self.assertEqual(episode['beats'][0]['start'],5)

    def test_rejection_audit_contains_only_static_codes_and_fingerprints(self):
        episode=self.story()
        review={'pass':False,'issues':['PRIVATE_NOTES https://private.example?token=SECRET'],
                'reason_codes':['unsupported_claim','unsupported_claim','SECRET','lost_visual_context']}
        error=fill.EditorialRejected(review,self.source(),episode,[5,30.83,56.67])
        audit=error.audit;serialized=json.dumps(audit)
        self.assertEqual(audit['reason_codes'],['lost_visual_context','unsupported_claim'])
        self.assertEqual(audit['candidate_digest'],clipping.digest(episode))
        self.assertEqual(audit['source_sha256'],'a'*64)
        for value in ['PRIVATE_NOTES','SECRET','https://private.example','beats','script','issues']:
            self.assertNotIn(value,serialized)
        self.assertEqual(fill.safe_rejection_reason(error),'Independent automated editorial check rejected the story')

    def test_missing_invalid_or_contradictory_codes_remain_rejections(self):
        self.assertEqual(fill.editorial_codes({'pass':False,'issues':['private']}),['unclassified_editorial_rejection'])
        self.assertIn('invalid_review_response',fill.editorial_codes({'pass':'true','issues':None}))
        self.assertIn('inconsistent_review',fill.editorial_codes({'pass':True,'issues':[], 'reason_codes':['unclear_hook']}))
