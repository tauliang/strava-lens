import json,tempfile,unittest
from pathlib import Path
from tests.test_archive import make_zip
from strava_lens_parser import iter_export

FOLLOWERS=b'Follower Athlete ID,Follow Status,Favorite Status\n11,Accepted,\n12,Pending,\n'
FOLLOWING=b'Following Athlete ID,Follow Status,Favorite Status\n11,Accepted,\n'
REACTIONS=b'Reaction Date,Reaction Type,Parent Type,Parent ID\n"Jan 1, 2024, 12:00:00 PM",Kudos,Activity,999\n'
COMMENTS=b'Comment Date,Comment\n"Jan 2, 2024, 12:00:00 PM",secret comment text\n'
INCOMING=b'Interaction ID,Interaction Date,Interaction Type,Actor Athlete ID,Activity ID\nc1,2024-01-03T12:00:00Z,Comment,11,1\nk1,2024-01-04T12:00:00Z,Kudos,99,1\n'
class SocialTests(unittest.TestCase):
    def import_rows(self,extras):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);archive=make_zip(root/'a.zip',extras=extras)
            rows=list(iter_export(archive,decode_streams=False,observed_at=1700000000))
            return {'counts':{'activity':sum(r['kind']=='activity' for r in rows),'social':sum(r['kind']=='social' for r in rows)}},[r for r in rows if r['kind']=='social'],next(r for r in rows if r['kind']=='snapshot')
    def test_network_snapshot_has_no_invented_follow_dates(self):
        _,rows,_=self.import_rows({'followers.csv':FOLLOWERS,'following.csv':FOLLOWING})
        network=next((r for r in rows if r.get('social_type')=='network'),None)
        self.assertIsNotNone(network);self.assertEqual(network['followers'],1);self.assertEqual(network['pending_followers'],1);self.assertEqual(network['following'],1)
        self.assertEqual(network['followers_available'],1);self.assertNotIn('followed_at',network)
    def test_outgoing_dates_are_preserved_without_comment_bodies(self):
        _,rows,_=self.import_rows({'reactions.csv':REACTIONS,'comments.csv':COMMENTS})
        events=[r for r in rows if r.get('social_type')=='interaction']
        self.assertEqual(len(events),2);self.assertTrue(all(r['direction']=='given' for r in events));self.assertEqual({r['interaction_type'] for r in events},{'Kudos','Comment'})
        self.assertEqual(events[0]['local_year'],2024);self.assertNotIn('secret comment text',json.dumps(rows));self.assertTrue(all('actor_id' not in r for r in events))
    def test_received_interactions_classify_current_followers_only(self):
        _,rows,_=self.import_rows({'followers.csv':FOLLOWERS,'social_interactions.csv':INCOMING})
        events=[r for r in rows if r.get('direction')=='received'];self.assertEqual(len(events),2)
        self.assertEqual({r['actor_id']:r['is_current_follower'] for r in events},{'11':1,'99':0})
    def test_social_records_participate_in_snapshot_reconciliation(self):
        m,rows,snapshot=self.import_rows({'followers.csv':FOLLOWERS,'reactions.csv':REACTIONS})
        self.assertTrue(rows);self.assertEqual(snapshot['expected_records'],m['counts']['activity']+m['counts']['social'])
        self.assertEqual(len({r['event_id'] for r in rows}),len(rows))
    def test_missing_files_are_unknown_not_zero_followers(self):
        _,rows,_=self.import_rows({});network=next((r for r in rows if r.get('social_type')=='network'),None)
        self.assertIsNotNone(network);self.assertEqual(network['followers_available'],0);self.assertIsNone(network['followers']);self.assertEqual(network['received_available'],0)
    def test_incoming_foreign_activity_and_duplicate_ids_are_rejected(self):
        for payload in [INCOMING.replace(b',11,1',b',11,777'),INCOMING+INCOMING.splitlines(keepends=True)[1]]:
            with self.assertRaises(ValueError):self.import_rows({'social_interactions.csv':payload})
