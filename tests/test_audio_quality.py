import unittest
from archive_audio_quality import normalized,validate_review
class AudioQualityTests(unittest.TestCase):
    def test_year_and_apostrophe_notation_do_not_create_false_mismatch(self):
        self.assertEqual(normalized("Nineteen sixty-seven, BART’s tube.",'1967'),normalized("1967, BART's tube.",'1967'))
    def test_blind_heard_transcript_required_and_material_omission_rejected(self):
        expected='This floating section will become part of a railway tunnel under the bay.'
        with self.assertRaises(ValueError):validate_review({'pass':True,'issues':[]},expected)
        with self.assertRaises(ValueError):validate_review({'pass':True,'issues':[],'heard_text':'This floating section is completely different and has no railway.'},expected)
        self.assertEqual(validate_review({'pass':True,'issues':[],'heard_text':expected},expected),1)
    def test_audible_defect_blocks_despite_matching_words(self):
        with self.assertRaises(ValueError):validate_review({'pass':False,'issues':['clipping'],'heard_text':'A transcript is not proof of clean sound.'},'A transcript is not proof of clean sound.')
