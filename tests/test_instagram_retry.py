import unittest
from unittest.mock import patch
import retry_instagram


class RetryTests(unittest.TestCase):
    @patch('retry_instagram.clipping.public_https')
    def test_only_instagram_receives_retry(self, check):
        original = {'caption': 'Approved caption', 'social_accounts': [{'id': 'ig'}, {'id': 'yt'}],
                    'media': [{'url': 'https://example.com/clip.mp4'}],
                    'platform_configurations': {'youtube': {'title': 'test'}, 'instagram': {'placement': 'reels'}}}
        payload = retry_instagram.payload_for_retry(original, 'ig')
        self.assertEqual(payload['social_accounts'], ['ig'])
        self.assertEqual(set(payload['platform_configurations']), {'instagram'})
        self.assertEqual(payload['caption'], original['caption'])

    def test_unrelated_account_rejected(self):
        with self.assertRaises(ValueError):
            retry_instagram.payload_for_retry({'social_accounts': ['yt'], 'media': [{}]}, 'ig')
