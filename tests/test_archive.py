import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import archive_pipeline as archive
import clipping


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.data, self.sources = archive.catalog()
        self.episode = self.data['episodes'][0]
        self.source = self.sources[self.episode['source_id']]

    def test_catalog(self):
        self.assertEqual(len(self.data['episodes']), 2)
        self.assertIn('1956', archive.script(self.episode))

    def test_duplicate_rejected(self):
        data = copy.deepcopy(self.data)
        data['episodes'].append(data['episodes'][0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.json'
            path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                archive.catalog(path)

    def test_public_domain_validation_no_fake_campaign_expiry(self):
        source = archive.publication_source(self.episode, self.source)
        clipping.validate_source(source, publishing=True)
        with self.assertRaises(ValueError):
            clipping.validate_source(source, automatic=True)

    def test_source_change_invalidates_digest(self):
        original = archive.publication_source(self.episode, self.source)
        changed = copy.deepcopy(self.episode)
        changed['beats'][0]['text'] = 'Different narration'
        self.assertNotEqual(clipping.digest(original), clipping.digest(archive.publication_source(changed, self.source)))

    @patch('archive_pipeline.requests.get')
    def test_changed_rights_block(self, get):
        response = Mock()
        response.json.return_value = {'metadata': {'identifier': self.source['archive_id'],
            'collection': 'prelinger', 'licenseurl': 'all rights reserved'}, 'files': [{'name': self.source['filename']}]}
        get.return_value = response
        with self.assertRaises(ValueError):
            archive.check_rights(self.source)

    def test_publish_master_switch(self):
        with patch.dict(os.environ, {'CLIP_PUBLISH_ENABLED': 'false'}):
            with self.assertRaises(ValueError):
                archive.publish(Mock(approved=True))

    def test_explicit_destinations_required(self):
        source = archive.publication_source(self.episode, self.source)
        with self.assertRaises(ValueError):
            clipping.post_payload(source, {'caption': 'test', 'title': 'test'}, {}, 'https://example.com/video')

    def test_ai_narration_disclosed(self):
        source = archive.publication_source(self.episode, self.source)
        payload = clipping.post_payload(source, {'id': 'test', 'caption': 'test', 'title': 'test'},
            {'youtube': 'one', 'tiktok': 'two'}, 'https://example.com/video')
        self.assertTrue(payload['platform_configurations']['youtube']['contains_synthetic_media'])
        self.assertTrue(payload['platform_configurations']['tiktok']['is_ai_generated'])

    def test_captions_escape_commands(self):
        self.assertNotIn('\\', clipping.safe_ass(r'{\pos(0,0)}bad'))

    @patch('clipping.github')
    def test_untrusted_preview_rejected(self, github):
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'energeticcity/youtube-political-pipeline'}):
            github.return_value = {'head_repository': {'full_name': 'someone/fork'}}
            with self.assertRaises(ValueError):
                clipping.verify_run('123')

    @patch('clipping.github')
    def test_closed_publication_issue_still_locks(self, github):
        github.return_value = [{'title': '[clip-publication] test', 'state': 'closed'}]
        self.assertTrue(clipping.reserved('test'))


if __name__ == '__main__':
    unittest.main()
