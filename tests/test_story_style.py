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

    def test_avoids_orphan_caption_tail(self):
        text='It’s an elaborate fantasy about making housework simpler.'
        starts=[i*.05 for i in range(len(text))];ends=[t+.04 for t in starts]
        segments=style.phrase_segments(text,starts,ends)
        self.assertEqual(' '.join(s['text'] for s in segments),text)
        self.assertTrue(all(len(s['text'].split()) > 1 for s in segments))
        self.assertTrue(all(len(style.caption_lines(s['text'])) <= 2 for s in segments))

    def test_line_breaks_preserve_words_and_safe_width(self):
        text='This nineteen fifty-seven kitchen ad turned cabinets'
        lines=style.caption_lines(text)
        self.assertEqual(' '.join(lines),text)
        self.assertLessEqual(len(lines),2)
        self.assertTrue(all(len(line)<=29 for line in lines))

    def test_department_store_hook_packs_whole_words_and_preserves_alignment(self):
        # Exact 52-character opening phrase from failed run 37480576048.
        text = 'How did mid-century department stores guarantee that mass-produced shirts fit every customer consistently?'
        starts = [i * .05 for i in range(len(text))]
        ends = [t + .04 for t in starts]
        segments = style.phrase_segments(text, starts, ends)
        self.assertEqual(' '.join(s['text'] for s in segments), text)
        for segment in segments:
            self.assertLessEqual(len(style.caption_lines(segment['text'])), 2)
            offset = text.index(segment['text'])
            self.assertEqual(segment['start'], starts[offset])
            self.assertEqual(segment['end'], ends[offset + len(segment['text']) - 1])
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(segments, segments[1:])))
        with tempfile.TemporaryDirectory() as tmp:
            source = {'title': 'Quality Control', 'year': '1950', 'creator': 'Archive studio'}
            path = Path(tmp) / 'captions.ass'
            style.write_captions(path, segments, ends[-1] + .1, source)
            self.assertIn('AI-generated narration', path.read_text())

    def test_orphan_rebalancing_does_not_create_three_long_rows(self):
        text = 'a b abcdefghijklmnopqrst uvwxyzabcdefghijklmn opqrstuvwxyzabcdefgh'
        starts = [i * .05 for i in range(len(text))]
        ends = [t + .04 for t in starts]
        segments = style.phrase_segments(text, starts, ends)
        self.assertEqual(' '.join(s['text'] for s in segments), text)
        self.assertTrue(all(len(style.caption_lines(s['text'])) <= 2 for s in segments))
        self.assertTrue(all(a['end'] <= b['start'] for a, b in zip(segments, segments[1:])))

    def test_individual_oversized_words_still_fail_closed(self):
        text = 'a' * 30
        starts = [i * .05 for i in range(len(text))]
        ends = [t + .04 for t in starts]
        with self.assertRaisesRegex(ValueError, 'Caption word exceeds safe width'):
            style.phrase_segments(text, starts, ends)

    def test_modest_reframe_and_context_preserving_default(self):
        full=style.shot_filter(640,480)
        self.assertIn('crop=640:480:0:0',full)
        zoom=style.shot_filter(640,480,{'zoom':1.18,'x':.5})
        self.assertIn('crop=542:480:48:0',zoom)
        with self.assertRaises(ValueError):style.shot_filter(640,480,{'zoom':1.5})
        for framing in [{'zoom':float('nan')},{'x':float('inf')},{'zoom':True},{'portrait':True}]:
            with self.assertRaises(ValueError):style.shot_filter(640,480,framing)

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
