import struct,unittest
from strava_lens_parser import streams

def crc(payload):
    value=0
    for byte in payload:
        value^=byte
        for _ in range(8):value=(value>>1)^0xA001 if value&1 else value>>1
    return value

def fit_bytes():
    # Definition: record timestamp, distance (cm), HR, and position semicircles.
    definition=bytes([0x40,0,0])+struct.pack('<H',20)+bytes([5,253,4,0x86,5,4,0x86,3,1,2,0,4,0x85,1,4,0x85])
    records=b''.join(bytes([0])+struct.pack('<IIBii',1000000000+t,dist,hr,2**29,0) for t,dist,hr in [(0,0,120),(10,5000,130),(20,10000,140)])
    body=definition+records;header=struct.pack('<BBHI4s',12,0x20,100,len(body),b'.FIT');raw=header+body;return raw+struct.pack('<H',crc(raw))
GPX=b'''<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg><trkpt lat="40" lon="-74"><ele>10</ele><time>2026-01-01T12:00:00Z</time><extensions><hr>125</hr><cad>80</cad></extensions></trkpt><trkpt lat="40.001" lon="-74"><time>2026-01-01T12:00:10Z</time></trkpt></trkseg></trk></gpx>'''
class StreamTests(unittest.TestCase):
    def test_fit_normalization_and_crc(self):
        rows=list(streams.decode_activity(fit_bytes(),'a.fit','rev'));samples=[r for r in rows if r['kind']=='sample'];self.assertEqual(len(samples),3);self.assertEqual(samples[1]['distance_m'],50);self.assertEqual(samples[1]['hr'],130);self.assertEqual(samples[0]['latitude'],45);self.assertEqual(samples[0]['timestamp'],1631065600)
        bad=fit_bytes()[:-1]+b'\xff'
        with self.assertRaises(ValueError):list(streams.decode_activity(bad,'a.fit','rev'))
    def test_gpx_extensions_and_cumulative_distance(self):
        r=list(streams.decode_activity(GPX,'a.gpx','r'));self.assertEqual(len(r),2);self.assertEqual(r[0]['hr'],125);self.assertGreater(r[1]['distance_m'],100);self.assertIsNone(r[1]['hr'])
    def test_xml_entities_and_invalid_coordinates(self):
        with self.assertRaises(ValueError):list(streams.decode_activity(b'<!DOCTYPE gpx [<!ENTITY x SYSTEM "file:///etc/passwd">]><gpx>&x;</gpx>','a.gpx','r'))
        with self.assertRaises(ValueError):list(streams.decode_activity(GPX.replace(b'lat="40"',b'lat="999"'),'a.gpx','r'))
    def test_unknown_format_and_truncation(self):
        with self.assertRaises(ValueError):list(streams.decode_activity(b'abc','a.exe','r'))
        with self.assertRaises(ValueError):list(streams.decode_activity(fit_bytes()[:25],'a.fit','r'))
    def test_gpx_speed_uses_observed_distance_and_time(self):
        rows=list(streams.decode_activity(GPX,'a.gpx','r'));self.assertAlmostEqual(rows[1]['speed_mps'],11.1195,places=3)
