import copy
from datetime import datetime
import json
import importlib.util
import unittest
import sys
import tempfile
from unittest.mock import MagicMock, patch
import gta6_cloud as g

class CloudPipelineTests(unittest.TestCase):
    def setUp(self):
        self.time=datetime(2026,11,22,13,0,tzinfo=g.TZ)
        self.a={'id':'7709573342407216416','source':'https://www.tiktok.com/@skyxl.cc/video/7709573342407216416','creator':'skyxl.cc','sha256':'a'*64,'status':'ready','priority':1}
        self.b=dict(self.a,id='7710205990817336598',source='https://www.tiktok.com/@ksnv_editz/video/7710205990817336598',creator='ksnv_editz',sha256='b'*64,priority=2)
        self.q={'items':[self.a,self.b]}
    def test_recovery_preserves_published_youtube_and_other_successful_receipts(self):
        row={'delivery':{'tiktok':{'status':'accepted','video_id':'existing'},
             'instagram':{'status':'published','url':'https://www.instagram.com/reel/existing/'},
             'youtube':{'status':'published','url':'https://www.youtube.com/watch?v=existing'}}}
        original=copy.deepcopy(row['delivery'])
        with tempfile.TemporaryDirectory() as folder, patch.object(g,'OUT',g.Path(folder)), patch.object(g,'save_issue'):
            with patch.object(g,'tiktok_cli_upload') as tt, patch.object(g,'instagram_cli_upload') as ig, patch.object(g.cross,'api') as yt:
                g.complete_publication(289,row,{},g.Path('unused'),266,{})
                tt.assert_not_called();ig.assert_not_called();yt.assert_not_called()
        self.assertEqual(row['delivery'],original)
        self.assertEqual(row['status'],'posted')

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
    @unittest.skipUnless(importlib.util.find_spec('autotok'), 'Autotok identity test runs in the GTA6 workflow with its optional dependency')
    def test_upstream_cli_signs_the_endpoint_it_actually_posts_to(self):
        from autotok.accounts import Account
        from autotok.uploader import Client
        from urllib.parse import urlsplit
        import requests
        signer=MagicMock();signer.sign.return_value=MagicMock(x_bogus='test',signature='test')
        client=Client(Account.from_dict({'name':'test','cookies':[{'name':'sessionid','value':'test'}]}),proxy=False,signer=signer)
        session=MagicMock();session.cookies=requests.cookies.RequestsCookieJar()
        response=session.post.return_value;response.status_code=200;response.json.return_value={'status_code':0}
        client._publish(session,{})
        self.assertEqual(urlsplit(signer.sign.call_args.args[0]).path,urlsplit(session.post.call_args.args[0]).path)

    @unittest.skipUnless(importlib.util.find_spec('autotok'), 'Autotok compatibility test uses the installed upstream CLI')
    def test_upstream_cli_retains_only_authorized_tiktok_session_cookie_domains(self):
        from autotok.accounts import Account
        from autotok.uploader import Client
        account=Account.from_dict({'name':'test','cookies':[
            {'name':'sessionid','value':'test','domain':'.tiktok.com'},
            {'name':'tt-target-idc','value':'useast2a','domain':'.tiktok.com'},
            {'name':'passport_csrf_token','value':'approved','domain':'.tiktok.com'},
            {'name':'sid_guard','value':'foreign','domain':'.example.com'}]})
        session=Client(account,proxy=False)._session()
        self.assertEqual(session.cookies.get('passport_csrf_token'),'approved')
        self.assertNotIn('sid_guard',session.cookies.get_dict())
        session.close()

    @unittest.skipUnless(importlib.util.find_spec('autotok'), 'Autotok identity test runs in the GTA6 workflow with its optional dependency')
    @patch('autotok.uploader.Client')
    def test_wrong_tiktok_numeric_id_stops_upload(self, client):
        c=client.return_value;r=c._session.return_value.get.return_value
        r.ok=True;r.json.return_value={'data':{'username':'gtaviclipfix','user_id':'wrong'}}
        with patch.dict(g.os.environ,{'GTA6_TIKTOK_SESSION':json.dumps({'name':'gta6_clips','cookies':[]})}):
            with self.assertRaises(ValueError):g.tiktok_client()
        c.upload.assert_not_called()
    @patch.object(g.subprocess,'run')
    @patch.object(g,'tiktok_client')
    def test_cli_upload_is_public_and_uses_isolated_verified_account(self,identity,run):
        run.return_value=MagicMock(returncode=0,stdout='Published. Video id: v1abc123\n')
        with patch.dict(g.os.environ,{'GTA6_TIKTOK_SESSION':json.dumps({'name':'gta6_clips','cookies':[]})}):
            receipt=g.tiktok_cli_upload('clip.mp4','caption')
        identity.assert_called_once()
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('-u')+1],'gta6_clips')
        self.assertEqual(args[args.index('-vi')+1],'0')
        self.assertIn('AUTOTOK_HOME',run.call_args.kwargs['env'])
        self.assertEqual(receipt['status'],'accepted')
        self.assertIsNone(receipt['url'])
    @patch.object(g.subprocess,'run')
    @patch.object(g,'tiktok_client')
    def test_cli_returns_real_public_item_id_separately_from_storage_reference(self,identity,run):
        run.return_value=MagicMock(returncode=0,stdout='Published. Video id: v1storage\nPublic item id: 7711441476168813844\n')
        with patch.dict(g.os.environ,{'GTA6_TIKTOK_SESSION':json.dumps({'name':'gta6_clips','cookies':[]})}):
            receipt=g.tiktok_cli_upload('clip.mp4','caption')
        self.assertEqual(receipt['video_id'],'v1storage')
        self.assertEqual(receipt['url'],'https://www.tiktok.com/@gtaviclipfix/video/7711441476168813844')
        self.assertEqual(receipt['status'],'accepted')

    @patch.object(g.subprocess,'run')
    @patch.object(g,'tiktok_client',side_effect=ValueError('Wrong identity'))
    def test_cli_never_runs_when_identity_check_fails(self,identity,run):
        with self.assertRaises(ValueError):g.tiktok_cli_upload('clip.mp4','caption')
        run.assert_not_called()
    @patch.object(g.subprocess,'run')
    @patch.object(g,'tiktok_client')
    def test_only_explicit_tiktok_rejection_gets_one_fresh_cli_attempt(self,identity,run):
        run.side_effect=[MagicMock(returncode=1,stdout='',stderr='status_code=5'),
                         MagicMock(returncode=0,stdout='Published. Video id: v1accepted',stderr='')]
        with patch.dict(g.os.environ,{'GTA6_TIKTOK_SESSION':json.dumps({'name':'gta6_clips','cookies':[]})}):
            self.assertEqual(g.tiktok_cli_upload('clip.mp4','caption')['video_id'],'v1accepted')
        self.assertEqual(run.call_count,2)

    @patch.object(g.subprocess,'run')
    @patch.object(g,'tiktok_client')
    def test_cli_failure_or_missing_receipt_is_not_marked_accepted(self,identity,run):
        with patch.dict(g.os.environ,{'GTA6_TIKTOK_SESSION':json.dumps({'name':'gta6_clips','cookies':[]})}):
            for code,stdout in [(1,''),(0,'No upload receipt')]:
                run.return_value=MagicMock(returncode=code,stdout=stdout,stderr='')
                with self.assertRaises(RuntimeError):g.tiktok_cli_upload('clip.mp4','caption')
    def test_wrong_instagram_account_stops_before_cli(self):
        state={'cookies':[{'name':'ds_user_id','value':'28321532959','domain':'.instagram.com'}],
               'origins':[],'gta6_verified_username':'poli.ticallens1'}
        with patch.dict(g.os.environ,{'GTA6_INSTAGRAM_BROWSER_SESSION':json.dumps(state)}):
            with patch.object(g.subprocess,'run') as cli:
                with self.assertRaises(ValueError):g.instagram_cli_upload('clip.mp4','caption')
                cli.assert_not_called()

    def test_instagram_missing_publication_receipt_is_not_success(self):
        with patch.object(g,'instagram_session',return_value=g.Path('/tmp')):
            with patch.object(g.subprocess,'run',return_value=MagicMock(returncode=0)):
                with self.assertRaises(RuntimeError):g.instagram_cli_upload('clip.mp4','caption')

    def test_youtube_session_rejects_other_platform_cookies(self):
        state={'cookies':[{'name':'sessionid','domain':'.instagram.com','value':'x'}]}
        with patch.dict(g.os.environ,{'GTA6_YOUTUBE_BROWSER_SESSION':json.dumps(state)}):
            with self.assertRaises(ValueError):g.youtube_session()

    def test_existing_youtube_title_blocks_another_upload(self):
        verify=MagicMock();verify.receipts.return_value={'existing':{'status':'published'}}
        with patch.dict(sys.modules,{'gta6.sau_youtube_verify':verify}):
            with patch.object(g,'youtube_session',return_value=(g.Path('/tmp'),g.Path('/tmp/account.json'))):
                with patch.object(g.subprocess,'run') as cli:
                    with self.assertRaises(RuntimeError):g.youtube_cli_upload('clip.mp4',{'title':'Existing title'})
                    cli.assert_not_called()

    def test_ineligible_duration_is_remembered_before_next_discovery(self):
        queue={'items':[]}
        with tempfile.TemporaryDirectory() as folder, patch.object(g,'OUT',g.Path(folder)):
            with patch.object(g,'discover_links',return_value=[self.a['source']]), patch.object(g,'model_name',return_value='review-model'):
                with patch.object(g,'save_issue'), patch.object(g,'review') as review:
                    with patch.object(g,'download',return_value=(g.Path('unused'),{'duration':120})):
                        with self.assertRaises(RuntimeError):g.discover(266,queue,[])
                    self.assertIn(self.a['id'],queue['rejected_ids'])
                    with patch.object(g,'download') as download:
                        with self.assertRaises(RuntimeError):g.discover(266,queue,[])
                        download.assert_not_called()
                    review.assert_not_called()

    def test_review_accepts_one_verdict_and_rejects_ambiguous_or_invalid_data(self):
        verdict={'approve':False,'confidence':0.95,'title':'Fan edit','caption':'Caption','reason':'Not relevant'}
        self.assertEqual(g.parse_review(verdict),verdict)
        self.assertEqual(g.parse_review([verdict]),verdict)
        for bad in ([],[verdict,verdict],'approve',dict(verdict,approve='true'),
                    dict(verdict,confidence=True),dict(verdict,confidence=2),dict(verdict,confidence=float('nan'))):
            with self.subTest(value=bad),self.assertRaises(ValueError):g.parse_review(bad)

    @patch.object(g.cross,'gh')
    def test_multiple_queue_records_fail_closed(self,gh):
        with self.assertRaises(ValueError):g.load_queue([{'title':g.QUEUE_TITLE},{'title':g.QUEUE_TITLE}])
        gh.assert_not_called()
if __name__=='__main__':unittest.main()
