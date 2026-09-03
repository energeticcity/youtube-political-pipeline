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
        text = 'Here the camera shows another unusual machine performing a task with surprisingly elaborate moving parts.'
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

    @patch('archive_pipeline.previewed', return_value=True)
    @patch('archive_autofill.prepare', side_effect=ValueError('refill called'))
    def test_empty_queue_refills(self, prepare, previewed):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GH_TOKEN': 'test', 'GEMINI_API_KEY': 'test'}):
            with self.assertRaisesRegex(ValueError, 'refill called'):
                archive.preview(Mock(catalog=archive.CATALOG, episode='', output=tmp, media=None))
            prepare.assert_called_once()

    @patch('archive_pipeline.previewed', return_value=True)
    def test_missing_credentials_fails_scheduled_slot(self, previewed):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'GH_TOKEN': 'test', 'GEMINI_API_KEY': '', 'GITHUB_ACTIONS': 'true'}):
            with self.assertRaisesRegex(ValueError, 'credentials unavailable'):
                archive.preview(Mock(catalog=archive.CATALOG, episode='', output=tmp, media=None))

    @patch('clipping.verify_run', return_value={'head_sha': 'test'})
    @patch('clipping.publish_one')
    def test_generated_policy_mismatch_blocks_post(self, publish, verify):
        data, _ = archive.catalog()
        manifest = {'version': 1, 'commit': 'test', 'catalog_digest': clipping.digest(data),
                    'generated': {'policy_digest': 'wrong'}, 'clips': []}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CLIP_PUBLISH_ENABLED': 'true'}):
            (Path(tmp) / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'policy changed'):
                archive.publish(Mock(catalog=archive.CATALOG, output=tmp, approved=True, automatic=False))
            publish.assert_not_called()
