import gzip,io,json,tempfile,unittest,zipfile
from pathlib import Path
from tests.test_csv import data
from strava_lens_parser import archive,iter_export

def make_zip(path,payload=None,extras=None):
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('activities.csv',data() if payload is None else payload)
        for name,value in (extras or {}).items():z.writestr(name,value)
    return path
class ArchiveTests(unittest.TestCase):
    def test_traversal_symlink_duplicate_and_expansion_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'a.zip'
            for name in ['../escape','/absolute','activities/../../x','activities\\x']:
                make_zip(p,extras={name:b'x'})
                with self.assertRaises(ValueError):archive.inspect_archive(p)
            with zipfile.ZipFile(p,'w') as z:
                info=zipfile.ZipInfo('link');info.create_system=3;info.external_attr=0o120777<<16;z.writestr(info,'outside')
            with self.assertRaises(ValueError):archive.inspect_archive(p)
            make_zip(p,extras={'activities/a.fit.gz':gzip.compress(b'0'*1000)})
            with zipfile.ZipFile(p) as z:
                with self.assertRaises(ValueError):archive.read_member(z,'activities/a.fit.gz',max_bytes=100)
    def test_outer_limits_and_missing_schema(self):
        with tempfile.TemporaryDirectory() as t:
            p=make_zip(Path(t)/'a.zip')
            with self.assertRaises(ValueError):archive.inspect_archive(p,max_archive_bytes=10)
            make_zip(p,payload=b'wrong\n1\n')
            with self.assertRaises(ValueError):list(iter_export(p,decode_streams=False))
