import copy
from datetime import datetime
import json
import unittest
from unittest.mock import MagicMock, patch
import gta6_cloud as g

class CloudPipelineTests(unittest.TestCase):
    def setUp(self):
        self.time=datetime(2026,11,22,13,0,tzinfo=g.TZ)
        self.a={'id':'7709573342407216416','source':'https://www.tiktok.com/@skyxl.cc/video/7709573342407216416','creator':'skyxl.cc','sha256':'a'*64,'status':'ready','priority':1}
        self.b=dict(self.a,id='7710205990817336598',source='https://www.tiktok.com/@ksnv_editz/video/7710205990817336598',creator='ksnv_editz',sha256='b'*64,priority=2)
        self.q={'items':[self.a,self.b]}
    def test_selects_prepared_priority(self):
        self.assertEqual(g.select_clip(self.q,[],self.time)[0],self.a)
    def test_no_consecutive_creator(self):
        rows=[{'creator':'skyxl.cc','reserved_at':'2026-11-22T19:00:00Z'}]
        self.assertEqual(g.select_clip(self.q,rows,self.time)[0],self.b)
    def test_uncertain_reservations_count_toward_daily_cap(self):
        rows=[{'local_day':'2026-11-22','status':'reserved','source':str(i)} for i in range(12)]
        self.assertEqual(g.select_clip(self.q,rows,self.time)[1],'daily cap reached')
    def test_slot_cannot_be_reused_even_after_failure(self):
        rows=[{'slot':'2026-11-22T13','status':'failed'}]
        self.assertEqual(g.select_clip(self.q,rows,self.time)[1],'hour already reserved')
    def test_same_media_under_another_url_cannot_repeat(self):
        self.assertEqual(g.select_clip(self.q,[{'sha256':'a'*64}],self.time)[0],self.b)
    def test_creator_limited_to_two_per_day(self):
        rows=[{'local_day':'2026-11-22','creator':'skyxl.cc'} for _ in range(2)]
        self.assertEqual(g.select_clip(self.q,rows,self.time)[0],self.b)
    def test_profile_urls_are_not_publication_proof(self):
        self.assertIsNone(g.public_url('tiktok','https://www.tiktok.com/@gtaviclipfix'))
        self.assertIsNone(g.public_url('instagram','https://example.com/reel/abc'))
        self.assertEqual(g.public_url('instagram','https://www.instagram.com/reel/abc/'),'https://www.instagram.com/reel/abc/')
    @patch('autotok.uploader.Client')
    def test_wrong_tiktok_numeric_id_stops_upload(self, client):
        c=client.return_value;r=c._session.return_value.get.return_value
        r.ok=True;r.json.return_value={'data':{'username':'gtaviclipfix','user_id':'wrong'}}
        with patch.dict(g.os.environ,{'GTA6_TIKTOK_SESSION':json.dumps({'name':'gta6_clips','cookies':[]})}):
            with self.assertRaises(ValueError):g.tiktok_client()
        c.upload.assert_not_called()
    @patch.object(g.cross,'gh')
    def test_multiple_queue_records_fail_closed(self,gh):
        with self.assertRaises(ValueError):g.load_queue([{'title':g.QUEUE_TITLE},{'title':g.QUEUE_TITLE}])
        gh.assert_not_called()
if __name__=='__main__':unittest.main()
