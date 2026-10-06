from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import archive_preparation_recovery as recovery

TEXT = 'A grounded existing narration.'
RUN = {'created_at': '2026-10-06T14:37:53Z', 'updated_at': '2026-10-06T14:39:45Z'}
ITEM = {'history_item_id': 'history1', 'voice_id': 'voice1', 'text': TEXT,
        'model_id': 'eleven_multilingual_v2', 'source': 'TTS',
        'date_unix': datetime(2026, 10, 6, 14, 39, tzinfo=timezone.utc).timestamp()}


class PreparationRecoveryTests(unittest.TestCase):
    def test_history_identity_requires_exact_voice_text_model_and_original_time(self):
        self.assertEqual(recovery.history_matches([ITEM], 'voice1', TEXT, RUN), [ITEM])
        for changes in ({'voice_id': 'other'}, {'text': TEXT + ' changed'}, {'model_id': 'other'},
                        {'source': 'STS'}, {'date_unix': 0}):
            self.assertEqual(recovery.history_matches([{**ITEM, **changes}], 'voice1', TEXT, RUN), [])

    def test_alignment_requires_exact_characters_and_finite_monotonic_times(self):
        starts = [i * .05 for i in range(len(TEXT))]; ends = [v + .04 for v in starts]
        align = {'characters': list(TEXT), 'character_start_times_seconds': starts, 'character_end_times_seconds': ends}
        self.assertIsNotNone(recovery.exact_alignment({'alignments': {'normalized': align}}, TEXT))
        for changes in ({'characters': list('wrong')}, {'character_end_times_seconds': []},
                        {'character_start_times_seconds': [float('nan')] * len(TEXT)},
                        {'character_start_times_seconds': list(reversed(starts))}):
            self.assertIsNone(recovery.exact_alignment({'alignments': {**align, **changes}}, TEXT))

    @patch('archive_preparation_recovery.failed_context', return_value=({'slot': '2026-10-06T14:07:00Z', 'owner_run_id': '100'}, RUN, 'film', TEXT))
    @patch('archive_preparation_recovery.pages')
    @patch('clipping.api_json')
    @patch('archive_preparation_recovery.requests.get')
    def test_any_provider_request_holds_before_narration_read(self, get, api, pages, context):
        accounts = {'youtube': 'yt', 'instagram': 'ig', 'tiktok': 'tt'}
        api.side_effect = [{'id': v, 'platform': k, 'status': 'connected'} for k, v in accounts.items()]
        pages.return_value = [{'id': 'pending1', 'external_id': 'creator-clip-' + recovery.fill.source_key('film'), 'status': 'pending'}]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'CLIP_DESTINATIONS_JSON': json.dumps(accounts), 'POSTFORME_API_KEY': 'test'}):
            report = recovery.inspect(248, 249, tmp)
            self.assertEqual(report['existing_provider_post_ids'], ['pending1'])
        get.assert_not_called()
        self.assertTrue(all(c.args[0] == 'GET' for c in api.call_args_list))

    @patch('archive_preparation_recovery.failed_context', return_value=({'slot': '2026-10-06T14:07:00Z', 'owner_run_id': '100'}, RUN, 'film', TEXT))
    @patch('archive_preparation_recovery.pages', return_value=[])
    @patch('clipping.api_json')
    @patch('archive_preparation_recovery.requests.get')
    def test_exact_existing_history_read_never_exports_audio_text_or_history_identifier(self, get, api, pages, context):
        accounts = {'youtube': 'yt', 'instagram': 'ig', 'tiktok': 'tt'}
        api.side_effect = [{'id': v, 'platform': k, 'status': 'connected'} for k, v in accounts.items()]
        starts = [i * .05 for i in range(len(TEXT))]
        item = {**ITEM, 'alignments': {'original': {'characters': list(TEXT),
                'character_start_times_seconds': starts, 'character_end_times_seconds': [v + .04 for v in starts]}}}
        audio = Mock(ok=True, headers={'content-type': 'audio/mpeg'})
        audio.iter_content.return_value = [b'private-audio-bytes']
        get.side_effect = [Mock(ok=True, json=lambda: {'history': [ITEM], 'has_more': False}),
                           Mock(ok=True, json=lambda: item), audio]
        env = {'CLIP_DESTINATIONS_JSON': json.dumps(accounts), 'POSTFORME_API_KEY': 'test',
               'ELEVENLABS_VOICE_ID': 'voice1', 'ELEVENLABS_API_KEY': 'PRIVATE_KEY'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, env):
            report = recovery.inspect(248, 249, tmp)
            serialized = (Path(tmp) / 'preparation-recovery-check.json').read_text()
        self.assertTrue(report['alignment_available'])
        self.assertTrue(report['audio_available'])
        for private in (TEXT, 'PRIVATE_KEY', 'private-audio-bytes', 'history1', 'character_start_times_seconds'):
            self.assertNotIn(private, serialized)
        params = get.call_args_list[0].kwargs['params']
        self.assertEqual(params['source'], 'TTS')
        self.assertIn('date_after_unix', params)
        self.assertIn('date_before_unix', params)
        self.assertEqual(get.call_count, 3)

    @patch('archive_slots.issues')
    @patch('clipping.github')
    def test_consumed_or_already_recovered_slot_never_becomes_recoverable(self, github, issues):
        for fields in ({'phase': 'publishing'}, {'phase': 'submission_attempt_finished'},
                       {'phase': 'preparation_failed', 'recovery': {'used': True}},
                       {'phase': 'preparation_failed', 'publishing_run_id': '200'}):
            github.return_value = {'title': '[archive-slot] 2026-10-06T14:07:00Z', 'body': json.dumps({'version': 1, 'slot': '2026-10-06T14:07:00Z', **fields})}
            with self.assertRaises(ValueError): recovery.failed_context(248, 249)
        issues.assert_not_called()
