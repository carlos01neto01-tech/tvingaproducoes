"""Testes unitários sem baixar modelos. Execute python -m unittest discover -s tests -v."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from pipeline import ass_color, ass_timestamp, create_ass, make_caption_events, suggest_clips

class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.segments=[{'start':float(i*5),'end':float(i*5+4),'text':f'Este é um exemplo importante número {i}, como vamos trabalhar para melhorar esta notícia?','words':[]} for i in range(75)]
    def test_ten_suggestions_with_no_overlap(self):
        result=suggest_clips(self.segments,10)
        self.assertEqual(len(result),10)
        for i,a in enumerate(result):
            self.assertGreater(a['end'],a['start'])
            for b in result[i+1:]:
                self.assertLessEqual(max(0,min(a['end'],b['end'])-max(a['start'],b['start'])),(a['end']-a['start'])*0.14)
    def test_no_segments(self):
        self.assertEqual(suggest_clips([],10),[])
    def test_color(self):
        self.assertEqual(ass_color('#123456'),'&H00563412')
        self.assertEqual(ass_color('nope'),'&H00FFFFFF')
    def test_timestamp(self):
        self.assertEqual(ass_timestamp(61.25),'0:01:01.25')
    def test_ass_generated(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'captions.ass'
            create_ass(self.segments,0,25,{'font':'Arial','accent':'#FFCC22','animation':'fade','position':'bottom'},output)
            txt=output.read_text()
            self.assertIn('[Events]',txt)
            self.assertIn('Dialogue:',txt)
            self.assertIn('\\fad',txt)
            self.assertIn('FF',txt)
    def test_word_events(self):
        segment=[{'start':0,'end':3,'text':'A coisa está muito bem agora','words':[{'start':i*.5,'end':(i+1)*.5,'text':w} for i,w in enumerate('A coisa está muito bem agora'.split())]}]
        events=make_caption_events(segment,0,3,3)
        self.assertEqual(len(events),2)
        self.assertEqual(events[0]['start'],0)
        self.assertAlmostEqual(events[1]['end'],3)

if __name__=='__main__':unittest.main()
