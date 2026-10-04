import unittest
from archive_private_access import available_groups,POSTS
class PrivateAccessTests(unittest.TestCase):
    def test_real_zero_is_available_missing_nonfinite_boolean_are_not(self):
        row={'platform':'instagram','social_account_id':'a','social_post_id':POSTS[0],
             'metrics':{'views':0,'likes':None,'comments':float('nan'),'shares':False,'ig_reels_avg_watch_time':12.0}}
        self.assertEqual(available_groups([row],'instagram','a'),{'views':True,'engagement':False,'watch':True})
    def test_wrong_account_and_unrelated_posts_are_ignored(self):
        row={'platform':'tiktok','social_account_id':'other','social_post_id':POSTS[0],'metrics':{'view_count':123}}
        self.assertFalse(any(available_groups([row],'tiktok','a').values()))
