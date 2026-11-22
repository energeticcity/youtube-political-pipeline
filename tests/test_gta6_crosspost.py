import unittest
from unittest.mock import patch
import gta6_crosspost as g

class Gta6CrosspostTests(unittest.TestCase):
    def clip(self):
        return {'id':'7709573342407216416','source':'https://www.tiktok.com/@skyxl.cc/video/7709573342407216416',
            'sha256':'a'*64,'title':'Vice City montage','caption':'Edit: @skyxl.cc #GTA6'}

    def test_rejects_wrong_accounts_even_with_expected_status(self):
        for platform, identity in g.DESTINATIONS.items():
            a=dict(identity, platform=platform, status='connected')
            self.assertEqual(g.validate_account(platform,a)['id'],identity['id'])
            a['user_id']='wrong-user'
            with self.assertRaises(ValueError):g.validate_account(platform,a)

    def test_payload_never_targets_tiktok_or_news_accounts(self):
        p=g.payload(self.clip(),'https://media.example/clip.mp4')
        self.assertEqual(set(p['platform_configurations']),{'instagram','youtube'})
        self.assertEqual(set(p['social_accounts']),{'spc_gu1jpig48SRDfABsgU24','spc_XzVCHOliiqyX9TJ6FMWfr'})
        self.assertEqual(p['platform_configurations']['youtube']['privacy_status'],'public')
        self.assertFalse(p['platform_configurations']['youtube']['made_for_kids'])

    def test_requires_exact_source_and_fingerprint(self):
        g.validate_clip(self.clip())
        for k,v in [('source','https://example.com/video.mp4'),('sha256',''),('id','../escape')]:
            c=self.clip();c[k]=v
            with self.assertRaises(ValueError):g.validate_clip(c)

    @patch.object(g,'gh')
    def test_closed_reservation_still_blocks_duplicates(self, gh):
        gh.return_value=[{'title':'[gta6-crosspost] 7709573342407216416','number':1,'state':'closed'}]
        self.assertEqual(g.reservation('7709573342407216416')['number'],1)

if __name__=='__main__':unittest.main()
