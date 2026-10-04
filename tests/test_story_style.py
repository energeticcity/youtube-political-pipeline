import tempfile
from pathlib import Path
import unittest

import archive_story_style as style


class StoryStyleTests(unittest.TestCase):
    def test_phrase_timing_and_punctuation(self):
        text='These cabinets fly. In a dream, of course.'
        starts=[i*.05 for i in range(len(text))];ends=[t+.04 for t in starts]
        segments=style.phrase_segments(text,starts,ends)
        self.assertEqual([s['text'] for s in segments],['These cabinets fly.','In a dream,','of course.'])
        self.assertEqual(segments[1]['start'],starts[text.index('In')])
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(segments,segments[1:])))

    def test_line_breaks_preserve_words_and_safe_width(self):
        text='This nineteen fifty-seven kitchen ad turned cabinets'
        lines=style.caption_lines(text)
        self.assertEqual(' '.join(lines),text)
        self.assertLessEqual(len(lines),2)
        self.assertTrue(all(len(line)<=29 for line in lines))

    def test_modest_reframe_and_context_preserving_default(self):
        full=style.shot_filter(640,480)
        self.assertIn('crop=640:480:0:0',full)
        zoom=style.shot_filter(640,480,{'zoom':1.18,'x':.5})
        self.assertIn('crop=542:480:48:0',zoom)
        with self.assertRaises(ValueError):style.shot_filter(640,480,{'zoom':1.5})

    def test_caption_bounds_and_disclosure(self):
        source={'title':'Practical Dreamer','year':'1957','creator':'Handy (Jam) Organization'}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'captions.ass'
            style.write_captions(path,[{'start':0,'end':2,'text':'A grounded dream.'}],30,source)
            content=path.read_text()
            self.assertIn('AI-generated narration',content)
            self.assertIn('Prelinger Archives',content)
            self.assertIn('96,192,490',content)
            with self.assertRaises(ValueError):
                style.write_captions(path,[{'start':29,'end':32,'text':'Too late.'}],30,source)
