import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive_recovery_check as recovery

QUOTA = ('Failed to start YouTube resumable upload session: 429 Too Many Requests. '
         'Quota exceeded for quota metric Video Uploads and limit Video Uploads per day '
         'of service youtube.googleapis.com for consumer project_number:823315471809. '
         'rateLimitExceeded RESOURCE_EXHAUSTED')


class RecoveryCheckTests(unittest.TestCase):
    def test_project_quota_is_distinct_from_channel_limit(self):
        evidence = recovery.quota_evidence({'message': QUOTA})
        self.assertEqual(evidence['classification'], 'youtube_api_project_daily_upload_quota')
        self.assertEqual(evidence['consumer'], 'project_number:823315471809')
        self.assertEqual(evidence['http_status'], 429)
        self.assertEqual(evidence['failure_stage'], 'before_resumable_upload_session')
        channel = recovery.quota_evidence({'message': 'uploadLimitExceeded'})
        self.assertNotEqual(channel['classification'], evidence['classification'])

    def test_transport_and_private_data_not_exported(self):
        evidence = recovery.quota_evidence({'config': {'message': 'secret-token ' + QUOTA},
                                           'message': 'private-error-body'})
        self.assertEqual(evidence, {'classification': 'unclassified; hold recovery'})

    @patch('clipping.api_json')
    def test_pagination_checks_results_beyond_first_page(self, api):
        api.side_effect = [{'data': [{'id': f'r{i}'} for i in range(100)]},
                           {'data': [{'id': 'late-success', 'success': True}]}]
        with patch.dict(os.environ, {'POSTFORME_API_KEY': 'test'}):
            rows = recovery.pages('social-post-results', post_id='sp_test')
        self.assertEqual(rows[-1]['id'], 'late-success')
        self.assertEqual(api.call_args_list[-1].kwargs['params']['offset'], 100)
        self.assertTrue(all(c.args[0] == 'GET' for c in api.call_args_list))

    @patch('clipping.api_json')
    def test_inspection_holds_and_never_submits(self, api):
        api.side_effect = [
            {'id': 'sp_test', 'external_id': 'creator-clip-film', 'status': 'processed',
             'social_accounts': ['youtube-a', 'instagram-b'], 'caption': 'private-caption',
             'media': [{'url': 'https://secret-signed-url'}]},
            {'id': 'youtube-a', 'platform': 'youtube', 'username': 'DadJokeFix',
             'status': 'connected', 'access_token': 'private-token'},
            {'data': [{'id': 'result-a', 'post_id': 'sp_test', 'social_account_id': 'youtube-a',
                       'success': False, 'error': {'message': QUOTA}}]},
            {'data': [{'id': 'sp_test', 'external_id': 'creator-clip-film'}]},
            {'data': [{'id': 'existing_retry', 'external_id': 'sp_test-youtube-retry-1'}]},
        ]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'POSTFORME_API_KEY': 'test', 'CLIP_DESTINATIONS_JSON': '{"youtube":"youtube-a"}'}):
            report = recovery.inspect('sp_test', tmp)
            exported = (Path(tmp) / 'recovery-check.json').read_text()
        self.assertEqual(report['recovery_post_ids'], ['existing_retry'])
        self.assertEqual(report['action'], 'hold; no post or retry submitted')
        for secret in ['private-caption', 'private-token', 'secret-signed-url']:
            self.assertNotIn(secret, exported)
        self.assertTrue(all(c.args[0] == 'GET' for c in api.call_args_list))

    @patch('clipping.api_json')
    def test_wrong_destination_blocks_inspection(self, api):
        api.return_value = {'id': 'sp_test', 'social_accounts': ['other-account']}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
                'POSTFORME_API_KEY': 'test', 'CLIP_DESTINATIONS_JSON': '{"youtube":"youtube-a"}'}):
            with self.assertRaisesRegex(ValueError, 'configured YouTube'):
                recovery.inspect('sp_test', tmp)
        self.assertEqual(api.call_count, 1)
