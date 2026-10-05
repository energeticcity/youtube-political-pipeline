import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import retry_youtube as retry

CLIP = {'id': 'archive-film', 'title': 'Original', 'caption': 'Reviewed source and AI disclosure', 'sha256': 'a' * 64}
ORIGINAL = {'id': 'sp_original', 'external_id': 'creator-clip-archive-film',
            'caption': CLIP['caption'], 'social_accounts': ['youtube-a', 'instagram-b', 'tiktok-c'],
            'media': [{'url': 'https://example.com/checked.mp4'}],
            'platform_configurations': {'youtube': {'title': 'Original', 'contains_synthetic_media': True, 'privacy_status': 'public', 'made_for_kids': False},
                                        'instagram': {'placement': 'reels'}, 'tiktok': {'privacy_status': 'public'}}}
REPORT = {'youtube_results': [{'success': False, 'has_platform_video_reference': False,
          'quota': {'classification': 'youtube_api_project_daily_upload_quota',
                    'failure_stage': 'before_resumable_upload_session'}}],
          'youtube_account': {'id': 'youtube-a', 'user_id': 'channel-reviewed', 'username': 'DadJokeFix', 'platform': 'youtube', 'status': 'connected'},
          'same_reference_post_ids': ['sp_original'], 'recovery_post_ids': [],
          'recovery_reference': 'sp_original-youtube-retry-1'}
ENV = {'GITHUB_REF': 'refs/heads/main', 'CLIP_PUBLISH_ENABLED': 'true', 'CLIP_AUTO_PUBLISH_ENABLED': 'true',
       'CLIP_DESTINATIONS_JSON': '{"youtube":"youtube-a","instagram":"instagram-b","tiktok":"tiktok-c"}',
       'CLIP_PAUSED_DESTINATIONS_JSON': '{}', 'POSTFORME_API_KEY': 'test'}


class YouTubeRetryTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('archive_pipeline.public_feed_reference', return_value=None)
        self.feed = patcher.start()
        self.addCleanup(patcher.stop)
        account = patch('retry_youtube.EXPECTED_ACCOUNT', 'youtube-a')
        account.start(); self.addCleanup(account.stop)
        channel = patch('retry_youtube.EXPECTED_CHANNEL', 'channel-reviewed')
        channel.start(); self.addCleanup(channel.stop)

    @patch('clipping.public_https')
    def test_exact_original_payload_excludes_other_platforms(self, url):
        payload = retry.payload_for_retry(ORIGINAL, 'youtube-a', CLIP)
        self.assertEqual(payload['social_accounts'], ['youtube-a'])
        self.assertEqual(set(payload['platform_configurations']), {'youtube'})
        self.assertEqual(payload['media'], ORIGINAL['media'])
        self.assertEqual(payload['caption'], ORIGINAL['caption'])
        self.assertEqual(payload['external_id'], 'sp_original-youtube-retry-1')
        for change in [{'caption': 'Altered'}, {'external_id': 'unrelated'}, {'media': []}, {'social_accounts': ['other']}]:
            with self.assertRaises(ValueError):
                retry.payload_for_retry({**ORIGINAL, **change}, 'youtube-a', CLIP)

    def test_success_ambiguity_video_reference_and_unknown_failure_block(self):
        retry.terminal_failed(REPORT['youtube_results'])
        for rows in [[], [{'success': None}], [{'success': True}],
                     [{**REPORT['youtube_results'][0], 'has_platform_video_reference': True}],
                     [{**REPORT['youtube_results'][0], 'quota': {'classification': 'other'}}]]:
            with self.assertRaises(ValueError):
                retry.terminal_failed(rows)

    def test_existing99word_video_fails_current_policy_offline(self):
        with self.assertRaisesRegex(ValueError, 'current word-count'):
            retry.current_word_gate({'beats': [{'text': ' '.join(['word'] * 99)}]})

    @patch('clipping.public_https')
    def test_capacity_reset_boolean_stale_or_wrong_identity_cannot_approve(self, urls):
        now = datetime.now(timezone.utc)
        evidence = {'post_id': 'sp_original', 'youtube_account_id': 'youtube-a', 'video_sha256': CLIP['sha256'],
                    'current_policy_digest': 'digest', 'project_number': '823315471809', 'youtube_channel_id': 'channel-reviewed',
                    'verified_at': now.isoformat(), 'available_uploads': 1, 'no_extra_spend': True,
                    'within_existing_cadence_and_budget': True, 'no_manual_channel_duplicate': True,
                    'capacity_evidence_url': 'https://example.com/capacity', 'billing_evidence_url': 'https://example.com/billing',
                    'channel_review_url': 'https://youtube.com/channel/known', 'replacement_failed_run_id': '123'}
        self.assertEqual(retry.validate_attestation(evidence, 'sp_original', 'youtube-a', CLIP, 'digest', now), '123')
        for fields in [{'available_uploads': True}, {'available_uploads': 0}, {'available_uploads': float('nan')},
                       {'verified_at': (now - timedelta(hours=2)).isoformat()}, {'no_extra_spend': False},
                       {'video_sha256': 'b' * 64}, {'replacement_failed_run_id': ''}, {'no_manual_channel_duplicate': False}]:
            with self.assertRaises(ValueError):
                retry.validate_attestation({**evidence, **fields}, 'sp_original', 'youtube-a', CLIP, 'digest', now)

    def setup_execution(self, tmp, submit=True):
        return SimpleNamespace(post_id='sp_original', run_id='100', preview=tmp, output=tmp,
                               submit=submit, evidence_issue='12')

    @patch('retry_youtube.recovery.inspect', return_value=REPORT)
    @patch('clipping.reserved', return_value=False)
    @patch('retry_youtube.revalidate', return_value=(CLIP, {'video_sha256': CLIP['sha256']}))
    @patch('clipping.api_json')
    def test_default_validation_never_submits(self, api, validate, reserved, inspect):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV):
            retry.execute(self.setup_execution(tmp, False))
        api.assert_not_called()

    @patch('retry_youtube.recovery.inspect', return_value=REPORT)
    @patch('clipping.reserved', return_value=False)
    @patch('retry_youtube.revalidate', return_value=(CLIP, {'video_sha256': CLIP['sha256']}))
    @patch('retry_youtube.recovery_evidence', return_value='123')
    @patch('clipping.download')
    @patch('clipping.public_https')
    @patch('clipping.file_hash', return_value=CLIP['sha256'])
    @patch('archive_pipeline.delivery')
    def test_one_post_after_lock_and_ambiguous_post_never_retries(self, delivery, hash_, https, download, evidence, validate, reserved, inspect):
        for ambiguous in (False, True):
            calls = []
            def github(method, endpoint, **kwargs):
                calls.append(('github', method))
                return {'number': 9}
            def api(method, url, token, **kwargs):
                calls.append(('provider', method))
                if method == 'GET':
                    return copy.deepcopy(ORIGINAL)
                self.assertEqual(kwargs['json']['social_accounts'], ['youtube-a'])
                if ambiguous:
                    raise RuntimeError('timeout PRIVATE provider body')
                return {'id': 'sp_recovered'}
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV), patch('clipping.github', side_effect=github), patch('clipping.api_json', side_effect=api):
                if ambiguous:
                    with self.assertRaises(RuntimeError):
                        retry.execute(self.setup_execution(tmp))
                else:
                    retry.execute(self.setup_execution(tmp))
                    self.assertEqual(json.loads(os.environ['CLIP_DESTINATIONS_JSON']), {'youtube': 'youtube-a'})
            self.assertEqual(calls.count(('provider', 'POST')), 1)
            self.assertLess(calls.index(('github', 'POST')), calls.index(('provider', 'POST')))
            if ambiguous:
                self.assertNotIn(('github', 'PATCH'), calls)

    @patch('retry_youtube.recovery.inspect', return_value=REPORT)
    @patch('clipping.reserved', return_value=False)
    @patch('retry_youtube.revalidate', return_value=(CLIP, {'video_sha256': CLIP['sha256']}))
    @patch('retry_youtube.recovery_evidence', return_value='123')
    @patch('clipping.download')
    @patch('clipping.public_https')
    @patch('clipping.file_hash', return_value='b' * 64)
    @patch('clipping.github')
    @patch('clipping.api_json', return_value=ORIGINAL)
    def test_provider_media_hash_mismatch_prevents_reservation_and_submit(self, api, github, hash_, https, download, evidence, validate, reserved, inspect):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV):
            with self.assertRaisesRegex(ValueError, 'provider media differs'):
                retry.execute(self.setup_execution(tmp))
        github.assert_not_called()
        self.assertTrue(all(call.args[0] == 'GET' for call in api.call_args_list))

    @patch('retry_youtube.recovery.inspect')
    def test_disabled_or_paused_switch_blocks_before_provider_access(self, inspect):
        for override in [{'CLIP_PUBLISH_ENABLED': 'false'}, {'CLIP_AUTO_PUBLISH_ENABLED': 'false'},
                         {'CLIP_PAUSED_DESTINATIONS_JSON': '{"youtube":"youtube-a"}'}, {'GITHUB_REF': 'refs/heads/test'}]:
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**ENV, **override}):
                with self.assertRaises(ValueError):
                    retry.execute(self.setup_execution(tmp))
        inspect.assert_not_called()

    @patch('retry_youtube.recovery.inspect', return_value=REPORT)
    @patch('clipping.reserved', return_value=False)
    @patch('retry_youtube.revalidate')
    @patch('clipping.api_json')
    def test_feed_video_blocks_even_if_result_reports_failure(self, api, validate, reserved, inspect):
        self.feed.return_value = {'url': 'https://www.youtube.com/watch?v=already'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV):
            with self.assertRaisesRegex(ValueError, 'individual video exists'):
                retry.execute(self.setup_execution(tmp))
        validate.assert_not_called()
        api.assert_not_called()

    @patch('clipping.github')
    def test_capacity_issue_requires_administrator_author(self, github):
        github.side_effect = [{'title': '[archive-youtube-recovery-evidence] sp_original',
                               'user': {'login': 'someone'}, 'body': '{}'}, {'permission': 'read'}]
        with self.assertRaisesRegex(ValueError, 'authorized repository administrator'):
            retry.recovery_evidence('12', 'sp_original', 'youtube-a', CLIP)
        self.assertTrue(all(c.args[0] == 'GET' for c in github.call_args_list))

    @patch('retry_youtube.all_issues', return_value=[{'body': 'Recovery slot run: `123`'}])
    @patch('retry_youtube.validate_attestation', return_value='123')
    @patch('clipping.github')
    def test_closed_consumed_slot_cannot_be_used_again(self, github, attestation, ledger):
        github.side_effect = [{'title': '[archive-youtube-recovery-evidence] sp_original',
                               'user': {'login': 'administrator'}, 'body': '{}'}, {'permission': 'admin'},
                              {'head_repository': {'full_name': 'owner/repo'}, 'head_branch': 'main',
                               'event': 'schedule', 'path': '.github/workflows/daily-video.yml',
                               'conclusion': 'failure', 'created_at': datetime.now(timezone.utc).isoformat()}]
        with patch.dict(os.environ, {'GITHUB_REPOSITORY': 'owner/repo'}):
            with self.assertRaisesRegex(ValueError, 'already used'):
                retry.recovery_evidence('12', 'sp_original', 'youtube-a', CLIP)
