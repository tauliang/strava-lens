import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from strava_lens_parser import inspect_export, iter_export
from tests.test_csv import data
from tests.test_streams import GPX
from tests.test_social import FOLLOWERS, INCOMING

OBSERVED = 1768000000
CONFIG = {'hr_zones':[100,130,150,170], 'goals':[{'sport':'Run','metric':'activity_count','target':10,'period':'year'}]}


def fixture(path, payload=None, stream=GPX):
    members = {'activities.csv':payload or data(**{'7':'activities/a.gpx'}),
               'activities/a.gpx':stream,'followers.csv':FOLLOWERS,
               'social_interactions.csv':INCOMING}
    with zipfile.ZipFile(path, 'w') as archive:
        for name, raw in members.items():
            archive.writestr(zipfile.ZipInfo(name, (2020,1,1,0,0,0)), raw)
    return path


class ExportTests(unittest.TestCase):
    def test_matches_original_importer_golden_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path=fixture(Path(temp)/'export.zip')
            rows=list(iter_export(path,config=CONFIG,observed_at=OBSERVED))
            expected=json.loads((Path(__file__).parent/'fixtures/golden_gpx_export.json').read_text())
            self.assertEqual(sorted(rows,key=lambda r:r['event_id']),expected)
            self.assertEqual({p.name for p in Path(temp).iterdir()},{'export.zip'})

    def test_identity_retry_and_caller_config_are_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            path=fixture(Path(temp)/'export.zip');config=copy.deepcopy(CONFIG)
            one=list(iter_export(path,config=config,observed_at=OBSERVED))
            two=list(iter_export(path,config=config,observed_at=OBSERVED))
            self.assertEqual(one,two);self.assertEqual(config,CONFIG)
            self.assertEqual(inspect_export(path,config=config).snapshot_id,one[-1]['snapshot_id'])
            self.assertNotEqual(inspect_export(path,timezone='America/New_York',config=config).snapshot_id,one[-1]['snapshot_id'])
            self.assertNotEqual(inspect_export(path,decode_streams=False,config=config).snapshot_id,one[-1]['snapshot_id'])

    def test_corrupt_stream_preserves_summary_and_terminal_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            path=fixture(Path(temp)/'export.zip',stream=b'broken XML')
            rows=list(iter_export(path,observed_at=OBSERVED));activity=next(r for r in rows if r['kind']=='activity')
            self.assertEqual(activity['stream_status'],'quarantined')
            self.assertEqual(rows[-1]['kind'],'snapshot');self.assertEqual(rows[-1]['quarantined_streams'],1)
            self.assertFalse(any(r['kind']=='sample' for r in rows))

    def test_fatal_late_error_never_emits_terminal_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=[];path=fixture(Path(temp)/'export.zip')
            with self.assertRaises(ValueError):
                for row in iter_export(path,config={'goals':[{'metric':'bogus'}]},observed_at=OBSERVED):rows.append(row)
            self.assertTrue(rows)
            self.assertFalse(any(r['kind']=='snapshot' for r in rows))

    def test_reordered_and_added_activity_reuses_stream_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            path=fixture(Path(temp)/'a.zip')
            first=list(iter_export(path,observed_at=OBSERVED))
            newer=data(**{'0':'2','7':''})+data(**{'7':'activities/a.gpx'}).split(b'\n',1)[1]
            path2=fixture(Path(temp)/'b.zip',payload=newer)
            second=list(iter_export(path2,observed_at=OBSERVED))
            stream_ids=lambda rows:{r['event_id'] for r in rows if r['kind']=='sample'}
            self.assertEqual(stream_ids(first),stream_ids(second))
            self.assertNotEqual(first[-1]['snapshot_id'],second[-1]['snapshot_id'])
            self.assertEqual(sum(r['kind']=='activity' for r in second),2)

    def test_invalid_observation_and_unknown_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            path=fixture(Path(temp)/'a.zip')
            with self.assertRaises(ValueError):list(iter_export(path,observed_at=float('nan')))
            path=fixture(path,payload=b'Activity ID\n1\n')
            with self.assertRaises(ValueError):list(iter_export(path))

    def test_cli_reports_counts_only_and_fails_without_partial_output(self):
        import subprocess,sys
        with tempfile.TemporaryDirectory() as temp:
            path=fixture(Path(temp)/'export.zip')
            command=[sys.executable,'-m','strava_lens_parser',str(path)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['counts']['activity'],1)
            self.assertNotIn('secret comment',result.stdout)
            fixture(path,stream=b'corrupt GPX')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout)['quarantined_streams'],1)
            fixture(path,payload=b'unsupported\nprivate-value\n')
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(result.stdout,'')
            self.assertNotIn('private-value',result.stderr)
