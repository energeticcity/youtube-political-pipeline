from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import archive_slots as slots
import archive_pipeline as archive
import clipping

NOW = datetime(2026, 10, 5, 15, 30, tzinfo=timezone.utc)
SLOT = '2026-10-05T14:07:00Z'
ENV = {'GITHUB_REF': 'refs/heads/main', 'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'owner/repo',
       'CLIP_PUBLISH_ENABLED': 'true', 'CLIP_AUTO_PUBLISH_ENABLED': 'true', 'GITHUB_RUN_ID': '100', 'GITHUB_RUN_ATTEMPT': '1', 'ARCHIVE_SLOT_REQUEST': SLOT}


class SlotTests(unittest.TestCase):
    def test_cron_identity_event_admission_time_and_delayed_job_are_distinct(self):
        created = NOW.replace(hour=14, minute=9)
        slot, reason = slots.resolve('schedule', '7 14 * * *', '', created, NOW)
        self.assertEqual(slots.slot_name(slot), SLOT)
        self.assertIsNone(reason)
        for cron, creation in [('7 14,18,22 * * *', created), ('7 14 * * *', NOW),
                               ('7 14 * * *', created + timedelta(days=1)), ('7 99 * * *', created)]:
            slot, reason = slots.resolve('schedule', cron, '', creation, NOW)
            self.assertIsNone(slot)
            self.assertIsNotNone(reason)

    def test_explicit_manual_recovery_is_same_day_due_and_bounded(self):
        self.assertEqual(slots.slot_name(slots.resolve('workflow_dispatch', '', SLOT, NOW, NOW)[0]), SLOT)
        for requested in ['', '2026-10-05T18:07:00Z', '2026-10-04T22:07:00Z']:
            self.assertIsNone(slots.resolve('workflow_dispatch', '', requested, NOW, NOW)[0])
        self.assertIsNone(slots.resolve('workflow_dispatch', '', SLOT, NOW, NOW.replace(hour=17, minute=38))[0])
        for requested in ['2026-10-05T14:08:00Z', '2026-10-05T14:07:00-07:00', '2026-10-05T14:07:00']:
            with self.assertRaises(ValueError):
                slots.resolve('workflow_dispatch', '', requested, NOW, NOW)

    def admission_fixture(self, event='workflow_dispatch'):
        return {'id': 100, 'event': event, 'created_at': '2026-10-05T14:09:00Z', 'head_sha': 'trusted'}

    def test_manual_and_schedule_compete_for_same_durable_slot_in_either_order(self):
        for first_event, second_event in [('workflow_dispatch', 'schedule'), ('schedule', 'workflow_dispatch')]:
            ledger = []
            def github(method, endpoint, **kwargs):
                if method == 'POST':
                    issue = {**kwargs['json'], 'number': 7, 'state': 'open'}
                    ledger.append(issue)
                    return issue
                return ledger
            with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV), patch('archive_slots.utc_now', return_value=NOW), patch('archive_slots.issues', side_effect=lambda: ledger), patch('clipping.github', side_effect=github), patch('archive_slots.trusted_live_run') as run:
                eventfile = Path(tmp) / 'event.json';os.environ['GITHUB_EVENT_PATH'] = str(eventfile)
                eventfile.write_text(json.dumps({'schedule': '7 14 * * *'}))
                run.return_value = self.admission_fixture(first_event)
                proof, _ = slots.admit(tmp)
                self.assertEqual(proof['owner_run_id'], '100')
                run.return_value = {**self.admission_fixture(second_event), 'id': 101}
                os.environ['GITHUB_RUN_ID'] = '101'
                second, reason = slots.admit(tmp)
                self.assertIsNone(second)
                self.assertIn('occupied', reason)
                self.assertEqual(len(ledger), 1)
                # A crash or closed failed reservation never buys another generation.
                ledger[0]['state'] = 'closed'
                d=json.loads(ledger[0]['body']);d['phase']='preparation_failed';ledger[0]['body']=json.dumps(d)
                self.assertIsNone(slots.admit(tmp)[0])

    @patch('archive_pipeline.narration')
    @patch('archive_autofill.prepare')
    def test_legacy_workflow_without_claim_fails_before_any_paid_work(self, prepare, narration):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV):
            args = Mock(output=tmp, catalog=archive.CATALOG, episode='', media=None)
            with self.assertRaisesRegex(ValueError, 'before paid work'):
                archive.preview(args)
        prepare.assert_not_called();narration.assert_not_called()

    def test_rerun_attempt_cannot_reuse_receipt_for_paid_generation(self):
        proof={'issue':7,'version':1,'slot':SLOT,'owner_run_id':'100','owner_attempt':'1','nonce':'original'}
        data={**proof,'phase':'claimed'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**ENV,'GITHUB_RUN_ATTEMPT':'2'}), patch('archive_slots.get_claim', return_value=({},data)):
            (Path(tmp)/'slot-admission.json').write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,'current attempt'):
                slots.require_generation(tmp)

    def test_old_preview_never_gets_publication_or_artifact_gate(self):
        with self.assertRaisesRegex(ValueError, 'calendar-slot provenance'):
            slots.verify_publication({'clips': []}, '100')
        with patch('clipping.verify_run'), patch('archive_slots.issues', return_value=[]):
            self.assertFalse(slots.publication_candidate('100'))

    def test_manifest_mismatch_and_consumed_crash_state_block_second_publication(self):
        proof={'issue':7,'version':1,'slot':SLOT,'owner_run_id':'100','owner_attempt':'1','nonce':'original'}
        manifest={'slot_admission':proof,'clips':[{'id':'clip','sha256':'video'}]}
        data={**proof,'phase':'preview_ready','manifest_digest':clipping.digest(manifest)}
        issue={'number':7}
        with patch('clipping.verify_run', return_value={'run_attempt':1}), patch('archive_slots.get_claim', side_effect=lambda p:(issue,data)), patch('archive_slots.patch_record'), patch.dict(os.environ,{'GITHUB_RUN_ID':'publisher'}):
            changed={**manifest,'clips':[{'id':'clip','sha256':'tampered'}]}
            with self.assertRaisesRegex(ValueError,'changed'):
                slots.verify_publication(changed,'100')
            slots.begin_publication(manifest,'100')
            self.assertEqual(data['phase'],'publishing')
            with self.assertRaisesRegex(ValueError,'consumed'):
                slots.begin_publication(manifest,'100')
            # Partial/accepted/pending platform results cannot reopen generation/publication.
            slots.finish_publication(manifest)
            self.assertEqual(data['phase'],'submission_attempt_finished')
            with self.assertRaises(ValueError):slots.begin_publication(manifest,'100')

    def test_workflows_serialize_claims_and_publication_and_preserve_three_times(self):
        root=Path(__file__).resolve().parents[1]
        daily=(root/'.github/workflows/daily-video.yml').read_text()
        publish=(root/'.github/workflows/archive-publish.yml').read_text()
        for cron in slots.CRONS:self.assertIn("cron: '"+cron+"'",daily)
        self.assertEqual(daily.count('cron:'),3)
        self.assertIn('group: archive-previews',daily)
        self.assertIn('group: archive-publication',publish)
        self.assertIn('publication-candidate',publish)

    @patch('archive_slots.trusted_live_run')
    def test_disabled_switch_never_claims_or_spends(self, run):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {**ENV, 'CLIP_PUBLISH_ENABLED':'false'}):
            proof, reason = slots.admit(tmp)
        self.assertIsNone(proof)
        self.assertIn('disabled', reason)
        run.assert_not_called()

    def test_ready_transition_requires_uploaded_unchanged_owner_media(self):
        proof={'issue':7,'version':1,'slot':SLOT,'owner_run_id':'100','owner_attempt':'1','nonce':'original'}
        data={**proof,'phase':'claimed'}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV), patch('archive_slots.get_claim', return_value=({'number':7},data)), patch('archive_slots.patch_record') as update:
            root=Path(tmp);(root/'clip').mkdir();video=root/'clip/clip.mp4';video.write_bytes(b'checked-video')
            manifest={'slot_admission':proof,'clips':[{'id':'clip','sha256':clipping.file_hash(video)}]}
            (root/'manifest.json').write_text(json.dumps(manifest))
            video.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'fingerprint'):
                slots.mark_ready(tmp)
            update.assert_not_called()
            video.write_bytes(b'checked-video')
            slots.mark_ready(tmp)
            self.assertEqual(data['phase'],'preview_ready')
            self.assertEqual(data['manifest_digest'],clipping.digest(manifest))
