import importlib.util
import unittest

if any(importlib.util.find_spec(m) is None for m in ("shapely", "plotly")):
    raise unittest.SkipTest("shapely and plotly are needed: analysis/requirements-nspd-py39.txt "
                            "and analysis/requirements-round4-py39.txt")

import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from nspd_collect import Client, Stop, strip_rights
from nspd_export import export, object_key, max_floor, to_4326, numeric


class NspdChecks(unittest.TestCase):
    def test_rights_are_removed_recursively(self):
        src={'properties':{'options':{'right_type':'x', 'floors':'2-22'},
             'other':[{'ownership_type':'y', 'determination_couse':'z', 'safe':1}]}}
        self.assertEqual(strip_rights(src), {'properties':{'options':{'floors':'2-22'}, 'other':[{'safe':1}]}})

    def test_mercator_and_range_floors(self):
        lon,lat=37.618,55.751
        x=6378137*math.radians(lon);y=6378137*math.log(math.tan(math.pi/4+math.radians(lat)/2))
        actual=to_4326(x,y)
        self.assertAlmostEqual(float(actual[0]),lon)
        self.assertAlmostEqual(float(actual[1]),lat)
        self.assertEqual(max_floor('2-22'),22)
        self.assertIsNone(max_floor(None))

    def test_unidentified_features_do_not_collapse(self):
        a={'properties':{'category':36369, 'options':{'floors':'1'}}}
        b={'properties':{'category':36369, 'options':{'floors':'2'}}}
        self.assertNotEqual(object_key(a),object_key(b))

    def test_numeric_missing_and_zero_remain_distinct(self):
        self.assertIsNone(numeric(pd.NA))
        self.assertIsNone(numeric(float('nan')))
        self.assertIsNone(numeric(''))
        self.assertEqual(numeric('0'),0)
        self.assertEqual(numeric('1 200,5'),1200.5)

    def test_stop_prevents_network(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'STOP').write_text('test')
            client=Client(d,lambda text:None)
            with patch('urllib.request.urlopen') as network:
                with self.assertRaises(Stop):client.post((0,1,0,1),[36369])
                network.assert_not_called()

    def test_export_keeps_latest_duplicate_and_reports_partial_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            pd.DataFrame([dict(tile_id='a',lat_min=55.7,lat_max=55.8,lon_min=37.6,lon_max=37.7),
                          dict(tile_id='b',lat_min=55.7,lat_max=55.8,lon_min=37.7,lon_max=37.8)]).to_csv(root/'tiles_2km.csv',index=False)
            x=6378137*math.radians(37.618);y=6378137*math.log(math.tan(math.pi/4+math.radians(55.751)/2))
            records=[]
            for time,floor in [('2026-09-01T10:00:00','2'),('2026-09-01T11:00:00','2-22')]:
                f=dict(id=1,properties=dict(category=36369, externalKey='77:test', systemInfo={'updated':time},
                    options={'floors':floor,'right_type':'must not persist'}),
                    geometry=dict(type='Point',coordinates=[x,y],crs={'properties':{'name':'EPSG:3857'}}))
                records.append(json.dumps(dict(tile='a',ts=time,f=[f])))
            (root/'raw_view.jsonl').write_text('\n'.join(records)+'\n')
            (root/'done_view.txt').write_text('a\n')
            result=export(root)
            table=pd.read_parquet(root/'tables/moscow_buildings.parquet')
            self.assertEqual(len(table),1)
            self.assertEqual(table.iloc[0].floors_n,22)
            self.assertNotIn('right_type',table)
            self.assertFalse(result['complete'])
            self.assertEqual(result['counts']['duplicates'],1)


if __name__=='__main__':unittest.main()
