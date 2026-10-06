import json
import unittest
import archive_autofill as autofill

class RejectionDiagnosticsTests(unittest.TestCase):
    def test_code_owned_validation_reason_is_visible(self):
        self.assertEqual(autofill.safe_rejection_reason(ValueError('Narration must be 50–85 words')), 'Narration must be 50–85 words')

    def test_provider_payload_and_unknown_error_are_redacted(self):
        for error in [ValueError('Bearer PRIVATE_TOKEN https://private-upload.example?signature=PRIVATE'), RuntimeError('PRIVATE'), KeyError('PRIVATE'), TypeError('PRIVATE')]:
            self.assertEqual(autofill.safe_rejection_reason(error), 'Unclassified preparation failure')
        error=json.JSONDecodeError('PRIVATE', 'PRIVATE', 0)
        self.assertEqual(autofill.safe_rejection_reason(error), 'Invalid structured JSON response')

    def test_metadata_reasons_are_fixed_and_unknown_payloads_stay_private(self):
        expected = {
            'No matching explicit Prelinger public-domain label': 'rights_label',
            'No reliable archive year': 'archive_year',
            'No bounded MP4 source': 'bounded_mp4',
            'Missing title or creator credit': 'source_credit',
        }
        for message, reason in expected.items():
            self.assertEqual(autofill.metadata_rejection_reason(ValueError(message)), reason)
        for error in [ValueError('Bearer PRIVATE'), KeyError('PRIVATE'), TypeError('PRIVATE')]:
            self.assertEqual(autofill.metadata_rejection_reason(error), 'invalid_metadata')
