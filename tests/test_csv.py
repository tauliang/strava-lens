import csv,io,sys,unittest
from pathlib import Path
from strava_lens_parser import csv_parser
HEADERS=['Activity ID','Activity Date','Activity Name','Activity Type','Elapsed Time','Distance','Relative Effort','Filename','Elapsed Time','Moving Time','Distance','Relative Effort','Average Heart Rate','Elevation Gain','Activity Gear']
def data(**changes):
    row=['1','Nov 1, 2026, 5:30:00 AM','<script> | delete','Run','600','6.54','12','activities/999.fit.gz','600','600','6547.4','13','140','20','Shoe']
    for k,v in changes.items(): row[int(k)]=v
    out=io.StringIO();w=csv.writer(out);w.writerow(HEADERS);w.writerow(row);return out.getvalue().encode()
class ParserTests(unittest.TestCase):
    def parse(self,**kw):return list(csv_parser.parse_activities(data(**kw),'personal','snap','America/New_York'))[0]
    def test_detailed_si_values_and_untrusted_name(self):
        r=self.parse();self.assertEqual(r['distance_m'],6547.4);self.assertEqual(r['activity_name'],'<script> | delete');self.assertEqual(r['filename'],'activities/999.fit.gz');self.assertEqual(r['relative_effort'],13);self.assertIn('effort_conflict',r['quality_flags']);self.assertEqual(r['local_date'],'2026-11-01');self.assertEqual(r['local_week_start'],'2026-10-26')
    def test_zero_effort_is_known_but_empty_is_unknown(self):
        self.assertEqual(self.parse(**{'11':'0'})['relative_effort'],0);self.assertIsNone(self.parse(**{'11':''})['relative_effort'])
    def test_strength_zero_distance_and_duration_conflict(self):
        r=self.parse(**{'3':'Weight Training','10':'0','9':'700'});self.assertEqual(r['distance_m'],0);self.assertFalse(r['duration_valid']);self.assertTrue(r['distance_valid'])
    def test_invalid_nonfinite_and_missing_required(self):
        for v in ['NaN','Infinity','oops','-2']:
            self.assertFalse(self.parse(**{'10':v})['distance_valid'])
        with self.assertRaises(ValueError):list(csv_parser.parse_activities(b'Activity ID\n1\n','personal','s'))
    def test_thousands_and_duplicate_ids(self):
        self.assertEqual(self.parse(**{'5':'1,060.83'})['raw_distance_km'],1060.83)
        payload=data();payload+=payload.splitlines(keepends=True)[1]
        with self.assertRaises(ValueError):list(csv_parser.parse_activities(payload,'p','s'))
    def test_numeric_ids_and_bad_width(self):
        with self.assertRaises(ValueError):self.parse(**{'0':'1 | delete'})
        with self.assertRaises(ValueError):list(csv_parser.parse_activities(data()+b'2,short\n','p','s'))
    def test_override_requires_known_field_and_valid_type(self):
        r=self.parse();fixed=csv_parser.apply_overrides(r,[{'activity_id':'1','field':'distance_m','value':'5000','reason':'device correction','revision':'1'}]);self.assertEqual(fixed['distance_m'],5000);self.assertEqual(r['distance_m'],6547.4)
        with self.assertRaises(ValueError):csv_parser.apply_overrides(r,[{'activity_id':'1','field':'activity_id','value':'2'}])
    def test_pace_minutes_per_kilometer(self):
        self.assertEqual(self.parse(**{'8':'1500','9':'1500','10':'5000'})['pace_min_km'],5)

    def test_vital_summary_max_hr_fallback_and_body_weight(self):
        rows=list(csv.reader(io.StringIO(data().decode())))
        rows[0]+=['Max Heart Rate','Max Heart Rate','Athlete Weight']
        rows[1]+=['185','','70.5']
        out=io.StringIO();csv.writer(out).writerows(rows)
        r=list(csv_parser.parse_activities(out.getvalue().encode(),'personal','snap'))[0]
        self.assertEqual(r['max_hr'],185);self.assertEqual(r['athlete_weight'],70.5);self.assertEqual(r['max_hr_source'],'summary')
