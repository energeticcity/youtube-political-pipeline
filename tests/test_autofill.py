import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import archive_autofill as fill
import archive_pipeline as archive
import clipping


class AutofillTests(unittest.TestCase):
    def setUp(self):
        self.settings = fill.policy()
        self.document = {'metadata': {'identifier': 'film', 'collection': ['prelinger'],
            'mediatype': 'movies', 'licenseurl': fill.PD, 'date': '1937',
            'title': 'Old technology', 'creator': 'Film studio'},
            'files': [{'name': 'film.mp4', 'size': '50000'}]}

    @patch('archive_autofill.requests.get')
    def test_rotating_pages_reach_metadata_budget(self, get):
        popular = [{'identifier': f'popular{i}'} for i in range(50)]
        rotating = [{'identifier': f'rotating{i}'} for i in range(50)]
        get.side_effect = [Mock(json=lambda: {'response': {'numFound': 1000, 'docs': popular}}),
                           Mock(json=lambda: {'response': {'docs': rotating}}),
                           Mock(json=lambda: {'response': {'docs': rotating}})]
        settings = dict(self.settings, preferred_candidates=[])
        pool = list(fill.candidates(settings, set()))
        self.assertTrue(all(i.startswith('rotating') for i in pool[:30]))
        self.assertEqual(len(pool), len(set(pool)))

    @patch('archive_autofill.requests.get')
    def test_discovery_intersects_topics_with_exact_existing_licence(self, get):
        from datetime import datetime, timezone
        get.side_effect = [Mock(json=lambda: {'response': {'numFound': 1000, 'docs': []}}),
                           Mock(json=lambda: {'response': {'docs': []}}),
                           Mock(json=lambda: {'response': {'docs': []}})]
        with patch('archive_autofill.datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 6, 18, tzinfo=timezone.utc)
            list(fill.candidates(self.settings, set()))
        self.assertEqual(get.call_count, 3)
        expected = '(' + self.settings['query'] + ') AND licenseurl:"' + fill.PD + '"'
        for call in get.call_args_list:
            self.assertEqual(call.kwargs['params']['q'], expected)
        # An indexed label cannot substitute for the original item-level gate.
        bad = copy.deepcopy(self.document)
        bad['metadata']['licenseurl'] = 'https://creativecommons.org/publicdomain/zero/1.0/'
        with self.assertRaisesRegex(ValueError, 'explicit Prelinger'):
            fill.source_from_metadata('film', bad, self.settings)

    @patch('archive_autofill.requests.get')
    def test_single_page_rotates_and_excludes_reserved_sources(self, get):
        from datetime import datetime, timezone
        docs = [{'identifier': f'film{i}'} for i in range(50)]
        get.return_value.json.return_value = {'response': {'numFound': 50, 'docs': docs}}
        settings = dict(self.settings, preferred_candidates=['film0', 'invalid/id'])
        used = {fill.source_key('film0')}
        with patch('archive_autofill.datetime') as clock:
            clock.now.return_value = datetime(2026, 10, 4, 14, tzinfo=timezone.utc)
            first = list(fill.candidates(settings, used))
            clock.now.return_value = datetime(2026, 10, 4, 18, tzinfo=timezone.utc)
            second = list(fill.candidates(settings, used))
        self.assertNotEqual(first[:30], second[:30])
        self.assertNotIn('film0', first)
        self.assertNotIn('invalid/id', first)

    @patch('archive_autofill.choose_model', return_value='test')
    @patch('archive_autofill.ledger', return_value=[])
    @patch('archive_autofill.candidates', return_value=[f'film{i}' for i in range(40)])
    @patch('archive_autofill.requests.get')
    def test_metadata_exhaustion_is_bounded_and_diagnosable(self, get, candidates, ledger, model):
        get.return_value.json.return_value = {}
        with tempfile.TemporaryDirectory() as tmp:
            diagnostic = Path(tmp) / 'diagnostics.json'
            with self.assertRaisesRegex(ValueError, 'bounded checks'):
                fill.prepare({'sources': [], 'episodes': []}, Path(tmp), diagnostics_path=diagnostic)
            report = json.loads(diagnostic.read_text())
        self.assertEqual(get.call_count, 30)
        self.assertEqual(report['metadata_gate_rejections'], 30)
        self.assertEqual(report['metadata_rejection_reasons'], {'rights_label': 30})
        self.assertEqual(report['generation_attempts'], 0)
        self.assertEqual(report['outcome'], 'exhausted')

    @patch('archive_autofill.choose_model', return_value='test')
    @patch('archive_autofill.ledger', return_value=[])
    @patch('archive_autofill.candidates', return_value=[f'film{i}' for i in range(40)])
    @patch('archive_autofill.requests.get')
    @patch('archive_autofill.source_from_metadata')
    @patch('clipping.download')
    @patch('clipping.file_hash', return_value='test')
    @patch('archive_autofill.make_story', side_effect=ValueError('secret-error-body'))
    def test_generation_budget_and_private_errors(self, story, file_hash, download, source, get, candidates, ledger, model):
        source.side_effect = lambda identifier, *args: {'id': fill.source_key(identifier), 'filename': 'film.mp4'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GITHUB_REF': 'refs/heads/test'}):
            diagnostic = Path(tmp) / 'diagnostics.json'
            with self.assertRaisesRegex(ValueError, 'bounded checks'):
                fill.prepare({'sources': [], 'episodes': []}, Path(tmp), diagnostics_path=diagnostic)
            report = json.loads(diagnostic.read_text())
        self.assertEqual(story.call_count, self.settings['max_candidates_per_run'])
        self.assertEqual(report['generation_attempts'], 3)
        self.assertEqual(report['generation_rejections'], 3)
        self.assertNotIn('secret-error-body', json.dumps(report))

    def test_explicit_rights_and_size_required(self):
        source = fill.source_from_metadata('film', self.document, self.settings)
        self.assertEqual(source['year'], '1937')
        for field, value in [('licenseurl', ''), ('collection', ['other']), ('identifier', 'wrong')]:
            bad = copy.deepcopy(self.document)
            bad['metadata'][field] = value
            with self.assertRaises(ValueError):
                fill.source_from_metadata('film', bad, self.settings)
        self.document['files'][0]['size'] = str(self.settings['max_source_bytes'] + 1)
        with self.assertRaises(ValueError):
            fill.source_from_metadata('film', self.document, self.settings)

    def test_story_bounds_and_duplicates(self):
        text = 'Here the camera shows a machine performing a task with elaborate moving parts.'
        story = {'suitable': True, 'title': 'Yesterday imagined tomorrow', 'headline': 'A VERY ODD FUTURE',
                 'beats': [{'start': i * 20, 'text': text, 'evidence': 'Visible machine in the source frame.'} for i in range(6)]}
        source = {'id': 'archive-example'}
        times = list(range(0, 120, 20))
        fill.validate_story(story, source, times, 180, [])
        with self.assertRaises(ValueError):
            fill.validate_story(story, source, times, 180, [text])
        story['beats'][0]['start'] = 1
        with self.assertRaises(ValueError):
            fill.validate_story(story, source, times, 180, [])

    def test_flexible_story_keeps_grounding_and_rejects_padding_or_uninspected_cuts(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/bart-private.json').read_text())
        story = dict(fixture['episode'], suitable=True)
        for beat in story['beats']:
            beat.pop('reframe',None);beat.pop('visual_cuts',None)
            beat['evidence']='Source footage and narration identify the tunnel construction.'
        times=[b['start'] for b in story['beats']]
        fill.validate_story(story,fixture['source'],times,821,[])
        bad=copy.deepcopy(story);bad['beats'][0]['visual_cuts']=[{'start':999}]
        with self.assertRaisesRegex(ValueError,'uninspected'):
            fill.validate_story(bad,fixture['source'],times,821,[])
        bad=copy.deepcopy(story);bad['beats'][0]['reframe']={'zoom':1.5}
        with self.assertRaises(ValueError):
            fill.validate_story(bad,fixture['source'],times,821,[])
        bad=copy.deepcopy(story);bad['beats']*=2
        with self.assertRaisesRegex(ValueError,'Three to six'):
            fill.validate_story(bad,fixture['source'],times,821,[])
        bad=copy.deepcopy(story)
        for beat in bad['beats']:beat['start']=times[0]
        with self.assertRaisesRegex(ValueError,'visual variety'):
            fill.validate_story(bad,fixture['source'],times,821,[])

    @patch('archive_pipeline.previewed', return_value=True)
    @patch('archive_autofill.prepare', side_effect=ValueError('refill called'))
    def test_empty_queue_refills(self, prepare, previewed):
        self.enterContext(patch('archive_slots.require_generation', return_value=None))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GH_TOKEN': 'test', 'GEMINI_API_KEY': 'test'}):
            with self.assertRaisesRegex(ValueError, 'refill called'):
                archive.preview(Mock(catalog=archive.CATALOG, episode='', output=tmp, media=None))
            prepare.assert_called_once()

    @patch('archive_pipeline.previewed', return_value=True)
    def test_missing_credentials_fails_scheduled_slot(self, previewed):
        self.enterContext(patch('archive_slots.require_generation', return_value=None))
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GH_TOKEN': 'test', 'GEMINI_API_KEY': '', 'GITHUB_ACTIONS': 'true'}):
            with self.assertRaisesRegex(ValueError, 'credentials unavailable'):
                archive.preview(Mock(catalog=archive.CATALOG, episode='', output=tmp, media=None))

    @patch('clipping.verify_run', return_value={'head_sha': 'test'})
    @patch('clipping.publish_one')
    def test_generated_policy_mismatch_blocks_post(self, publish, verify):
        self.enterContext(patch('archive_slots.verify_publication'))
        self.enterContext(patch('archive_slots.begin_publication'))
        self.enterContext(patch('archive_slots.finish_publication'))
        data, _ = archive.catalog()
        manifest = {'version': 1, 'commit': 'test', 'catalog_digest': clipping.digest(data),
                    'generated': {'policy_digest': 'wrong'}, 'clips': []}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CLIP_PUBLISH_ENABLED': 'true'}):
            (Path(tmp) / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'policy changed'):
                archive.publish(Mock(catalog=archive.CATALOG, output=tmp, approved=True, automatic=False))
            publish.assert_not_called()

    @patch('clipping.verify_run', return_value={'head_sha': 'test'})
    @patch('archive_pipeline.check_rights')
    @patch('clipping.publish_one')
    def test_generated_story_reaches_checked_publisher(self, publish, rights, verify):
        self.enterContext(patch('archive_slots.verify_publication'))
        self.enterContext(patch('archive_slots.begin_publication'))
        self.enterContext(patch('archive_slots.finish_publication'))
        data, _ = archive.catalog()
        source = copy.deepcopy(data['sources'][0])
        episode = copy.deepcopy(data['episodes'][0])
        source['id'] = fill.source_key(source['archive_id'])
        episode['id'] = episode['source_id'] = source['id']
        manifest = {'version': 1, 'commit': 'test', 'catalog_digest': clipping.digest(data),
            'generated': {'policy_digest': clipping.digest(fill.policy()), 'episode': episode,
                          'source': source, 'checks': {'review': {'pass': True, 'issues': []}}},
            'clips': [{'id': episode['id']}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CLIP_PUBLISH_ENABLED': 'true'}):
            (Path(tmp) / 'manifest.json').write_text(json.dumps(manifest))
            archive.publish(Mock(catalog=archive.CATALOG, output=tmp, approved=True, automatic=False, episode=''))
            rights.assert_called_once_with(source)
            publish.assert_called_once()

    @patch('archive_autofill.frames', return_value=[])
    @patch('clipping.probe', return_value=({}, 180))
    @patch('archive_autofill.validate_story', return_value={'beats': [{'start': 5}]})
    @patch('archive_autofill.generate_json', side_effect=[{}, {'pass': False, 'issues': ['unsupported claim']}])
    def test_editorial_rejection_blocks_story(self, generate, validate, probe, frames):
        source = fill.source_from_metadata('film', self.document, self.settings)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'editorial check rejected'):
                fill.make_story(source, Path(tmp) / 'source.mp4', self.settings, 'test', Path(tmp), [])
