import unittest
from strava_lens_parser import derive,privacy

def point(t,d,hr=140,lat=40,lon=-74):return {'kind':'sample','timestamp':t,'distance_m':d,'hr':hr,'latitude':lat,'longitude':lon,'speed_mps':5}
class DeriveTests(unittest.TestCase):
    def test_irregular_zones_gap_and_last_sample(self):
        result=derive.zone_intervals([point(0,0,100),point(10,20,150),point(41,60,180),point(51,80,200)],[],[120,160,180,190])
        self.assertEqual(result['zone_seconds'],[10,0,0,10,0]);self.assertEqual(result['observed_s'],20);self.assertEqual(result['unobserved_s'],31)
    def test_pause_mid_interval_and_missing_hr(self):
        timers=[{'timestamp':5,'timer_state':'stop_all'},{'timestamp':15,'timer_state':'start'}]
        result=derive.zone_intervals([point(0,0,100),point(10,10,None),point(20,20,150)],timers,[120,160,180,190]);self.assertEqual(result['observed_s'],5);self.assertEqual(result['paused_s'],10);self.assertEqual(result['unobserved_s'],5)
    def test_best_effort_interpolation(self):
        rows=[point(0,0),point(20,100),point(40,200),point(60,300)]
        best=derive.best_efforts(rows,[150]);self.assertEqual(best[0]['duration_s'],30);self.assertEqual(best[0]['target_m'],150)
    def test_invalid_distance_reset_gaps_and_jumps(self):
        for rows in [[point(0,0),point(10,-1),point(20,150)],[point(0,0),point(31,100),point(62,200)],[point(0,0),point(1,1000)]]:
            self.assertEqual(derive.best_efforts(rows,[150]),[])
    def test_missing_power_and_raw_gps_do_not_leak(self):
        rows=list(derive.derive_records([point(0,0),point(10,100)],{}, {'sport':'Run','timestamp':0,'duration_valid':1}))
        samples=[r for r in rows if r['kind']=='sample'];self.assertEqual(len(samples),2);self.assertNotIn('latitude',samples[0]);self.assertFalse(any(r['kind']=='gps' for r in rows));self.assertFalse(any('normalized_power' in r for r in rows))
class PrivacyTests(unittest.TestCase):
    def test_short_track_completely_masked(self):
        self.assertEqual(privacy.sanitize_track([point(0,0),point(10,100)],[],200),[])
    def test_zone_crossing_creates_disconnected_segments(self):
        points=[point(i*10,i*300,lat=40,lon=-74+i*.004) for i in range(9)]
        zones=[{'latitude':40,'longitude':-73.984,'radius_m':150}]
        result=privacy.sanitize_track(points,zones,200);self.assertEqual(len(result),2);self.assertTrue(all(p['longitude']!=-73.984 for seg in result for p in seg))
    def test_coarse_cell_touching_zone_is_suppressed(self):
        points=[point(i*10,i*1000,lat=40.001,lon=-74+i*.01) for i in range(4)]
        safe=privacy.cells(points,[{'latitude':40.009,'longitude':-73.981,'radius_m':100}],endpoint_mask_m=0)
        self.assertFalse(any(c['latitude']==40.005 and c['longitude']==-73.985 for c in safe))
    def test_leading_unknown_distance_does_not_abort_valid_segment(self):
        rows=[point(0,None),point(10,0),point(20,50),point(30,100)]
        result=list(derive.derive_records(rows,{}, {'sport':'Run','timestamp':0,'duration_valid':1}))
        self.assertEqual(len([r for r in result if r['kind']=='sample']),4)
    def test_shared_cells_cannot_reintroduce_endpoint_buffer(self):
        points=[point(i*10,i*85,lat=40,lon=-74+i*.001) for i in range(31)]
        result=privacy.cells(points,[],endpoint_mask_m=200)
        self.assertEqual(len(result),1)
