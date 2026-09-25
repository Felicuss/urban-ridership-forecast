"""Checks for mistakes that change the ML signal or the affected forecast cells.

Run without pytest: PYTHONPATH=analysis python -m unittest discover -s tests -p test_kaggle_round.py
"""
import unittest

import numpy as np
import pandas as pd

from s42_adaptive_profiles import weighted_median
from s43_collect_transport_events import parse_page
from s45_incident_adjustment import exposure


class ResearchChecks(unittest.TestCase):
    def test_reply_body_is_not_misread_as_a_new_incident(self):
        html='''<div class="tgme_widget_message" data-post="DtOperativno/12">
        <a class="tgme_widget_message_reply" href="https://t.me/DtOperativno/11">
        <div class="tgme_widget_message_text js-message_reply_text">Задерживаются трамваи № 17.</div></a>
        <div class="tgme_widget_message_text js-message_text">Восстановлено движение трамваев.</div>
        <time datetime="2025-11-20T04:02:37+00:00"></time></div>'''
        posts=parse_page(html)
        self.assertEqual(posts[0]['text'],'Восстановлено движение трамваев.')
        self.assertEqual(posts[0]['reply_to'],'https://t.me/DtOperativno/11')

    def test_incident_preserves_moscow_time_and_crosses_midnight(self):
        events=pd.DataFrame([dict(event_id='1',routes='17',start_ts='2025-11-20T23:45:00+03:00',
                                  end_ts='2025-11-21T00:30:00+03:00')])
        x,_=exposure(events)
        d=pd.Timestamp('2025-11-20').dayofyear-1
        self.assertAlmostEqual(x[d,5,23],.25)
        self.assertAlmostEqual(x[d+1,5,0],.5)
        self.assertAlmostEqual(x.sum(),.75)

    def test_weighted_median_is_independent_for_each_route_hour(self):
        values=np.array([[[0,100]],[[50,10]],[[100,0]]],dtype=float)
        got=weighted_median(values,np.array([.1,.2,.7]))
        np.testing.assert_array_equal(got,[[100,0]])


if __name__=='__main__':
    unittest.main()
