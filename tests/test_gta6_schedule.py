from datetime import datetime
import json
import unittest
from gta6.schedule import decision, TZ


class HourlyScheduleTests(unittest.TestCase):
    def rows(self,queue=None,posts=()):
        return [{'title':'[gta6-cloud-queue] Active queue','body':json.dumps(queue or {'items':[]})}]+[
            {'title':'[gta6-cloud-post] '+post['slot'],'body':json.dumps(post)} for post in posts]

    def time(self,hour,minute=2):return datetime(2026,11,23,hour,minute,tzinfo=TZ)

    def test_quiet_hours_do_not_start_browser_or_media_jobs(self):
        for hour in (0,6,20,23):self.assertFalse(decision(self.rows(),self.time(hour))['required'])

    def test_morning_discovery_runs_once_before_first_post(self):
        result=decision(self.rows(),self.time(7))
        self.assertTrue(result['discovery_due']);self.assertFalse(result['publication_due'])
        queue={'items':[],'discovery_windows':{'2026-11-23-am':'attempted'}}
        self.assertFalse(decision(self.rows(queue),self.time(7,17))['required'])

    def test_repeated_checks_do_not_repeat_a_reserved_or_uncertain_batch(self):
        queue={'items':[],'discovery_windows':{'2026-11-23-am':'attempted'}}
        for status in ('reserved','accepted','failed','posted'):
            posts=[{'slot':'2026-11-23T11','local_day':'2026-11-23','status':status}]
            self.assertFalse(decision(self.rows(queue,posts),self.time(11,22))['required'])

    def test_delayed_wakeup_targets_current_hour_without_bursting_missed_slots(self):
        result=decision(self.rows(),self.time(11,42))
        self.assertTrue(result['publication_due']);self.assertEqual(result['slot'],'2026-11-23T11')

    def test_afternoon_discovery_is_independent_of_morning(self):
        queue={'items':[],'discovery_windows':{'2026-11-23-am':'attempted'}}
        self.assertTrue(decision(self.rows(queue),self.time(15))['discovery_due'])

    def test_existing_discovery_timestamp_is_respected_during_migration(self):
        queue={'items':[],'last_discovery':{'time':'2026-11-23T14:05:00+00:00'}}
        self.assertFalse(decision(self.rows(queue),self.time(11))['discovery_due'])

    def test_daily_cap_includes_uncertain_reservations(self):
        posts=[{'slot':f'2026-11-23T{i:02}','local_day':'2026-11-23','status':'reserved'} for i in range(12)]
        result=decision(self.rows(posts=posts),self.time(19))
        self.assertFalse(result['publication_due'])

    def test_queue_ambiguity_fails_closed(self):
        with self.assertRaises(ValueError):decision([],self.time(11))
        with self.assertRaises(ValueError):decision(self.rows()*2,self.time(11))


if __name__=='__main__':unittest.main()
