import json
import os
from pathlib import Path
import tempfile
import unittest
import requests
from unittest.mock import Mock, patch

import archive_pipeline as archive


class PreparationDiagnosticsTests(unittest.TestCase):
    def test_live_rights_json_failure_holds_before_narration(self):
        data, sources = archive.catalog()
        episode = next(e for e in data['episodes'] if e['enabled'])
        response = Mock()
        response.json.side_effect = json.JSONDecodeError('PRIVATE_BODY', 'PRIVATE_BODY', 0)
        with tempfile.TemporaryDirectory() as tmp, patch('archive_slots.require_generation', return_value=None), patch('archive_pipeline.requests.get', return_value=response), patch('archive_pipeline.narration') as voice:
            with self.assertRaisesRegex(ValueError, 'at rights: invalid JSON'):
                archive.build_preview(Mock(catalog=archive.CATALOG, episode=episode['id'], output=tmp, media=None), Path(tmp))
            voice.assert_not_called()
            marker = json.loads((Path(tmp) / 'preparation-diagnostics.json').read_text())
        self.assertEqual(marker, {'version': 1, 'stage': 'rights', 'status': 'failed', 'error': 'invalid_json'})
        self.assertNotIn('PRIVATE_BODY', json.dumps(marker))

    def test_narration_invalid_json_never_repeats_paid_post(self):
        data, _ = archive.catalog()
        response = Mock(ok=True)
        response.json.side_effect = requests.exceptions.JSONDecodeError('PRIVATE', 'PRIVATE', 0)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'ELEVENLABS_VOICE_ID': 'voice', 'ELEVENLABS_API_KEY': 'PRIVATE_KEY'}), patch('archive_pipeline.requests.post', return_value=response) as post:
            with self.assertRaisesRegex(ValueError, 'at narration: invalid JSON') as caught:
                archive.preparation_step(tmp, 'narration', archive.narration, data['episodes'][0], Path(tmp))
            self.assertEqual(post.call_count, 1)
            marker = (Path(tmp) / 'preparation-diagnostics.json').read_text()
        self.assertNotIn('PRIVATE', marker + str(caught.exception))
        self.assertEqual(json.loads(marker)['stage'], 'narration')

    def test_unknown_error_marks_failure_without_recording_payload_or_retry(self):
        operation = Mock(side_effect=RuntimeError('PRIVATE_PAYLOAD'))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                archive.preparation_step(tmp, 'render', operation)
            marker = (Path(tmp) / 'preparation-diagnostics.json').read_text()
        operation.assert_called_once_with()
        self.assertNotIn('PRIVATE_PAYLOAD', marker)
        self.assertEqual(json.loads(marker)['error'], 'preparation_error')

    def test_success_does_not_export_returned_provider_data(self):
        operation = Mock(return_value={'PRIVATE': 'PROVIDER_PAYLOAD'})
        with tempfile.TemporaryDirectory() as tmp:
            result = archive.preparation_step(tmp, 'audio_review', operation)
            marker = json.loads((Path(tmp) / 'preparation-diagnostics.json').read_text())
        self.assertEqual(result, {'PRIVATE': 'PROVIDER_PAYLOAD'})
        self.assertEqual(marker, {'version': 1, 'stage': 'audio_review', 'status': 'completed'})
        operation.assert_called_once_with()

    def test_untrusted_stage_cannot_call_operation(self):
        operation = Mock()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'Unknown preparation stage'):
                archive.preparation_step(tmp, 'PRIVATE_STAGE', operation)
            self.assertFalse((Path(tmp) / 'preparation-diagnostics.json').exists())
        operation.assert_not_called()
