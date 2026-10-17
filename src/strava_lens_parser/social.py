"""Exported social contributions and explicitly supplied received interactions.

Comment bodies and names are not indexed. A network snapshot is an observation
at import time, not evidence of the dates on which relationships began.
"""
import datetime as dt
import re
from .csv_parser import read_csv,local_fields

def identifier(value):
    if not re.fullmatch(r'[0-9]{1,24}',value or ''):raise ValueError('invalid_social_athlete_id')
    return value

def dated(value):
    try:
        if re.match(r'^\d{4}-',value):
            date=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
            if date.tzinfo is None:raise ValueError('social_timezone_required')
        else:date=dt.datetime.strptime(value,'%b %d, %Y, %I:%M:%S %p').replace(tzinfo=dt.timezone.utc)
        return date.timestamp()
    except (ValueError,TypeError):raise ValueError('invalid_social_date')

def records(payloads,activity_ids,observed_at,timezone,archive_hash):
    accepted=set();followed=set();relations=[];counts={}
    for filename,field,direction in [('followers.csv','Follower Athlete ID','follower'),('following.csv','Following Athlete ID','following')]:
        seen=set();count=0;pending=0
        if filename in payloads:
            for row in read_csv(payloads[filename]):
                athlete=identifier(row.get(field));status=row.get('Follow Status')
                if status not in ('Accepted','Pending') or athlete in seen:raise ValueError('invalid_social_relationship')
                seen.add(athlete);count+=int(status=='Accepted');pending+=int(status=='Pending')
                if direction=='follower' and status=='Accepted':accepted.add(athlete)
                if direction=='following' and status=='Accepted':followed.add(athlete)
                relations.append(dict(social_type='relationship',relationship=direction,actor_id=athlete,follow_status=status,timestamp=observed_at))
        counts[direction+'s' if direction=='follower' else 'following']=count if filename in payloads else None
        if direction=='follower':counts['pending_followers']=pending if filename in payloads else None
    network=dict(social_type='network',timestamp=observed_at,archive_hash=archive_hash,observation_basis='import_time',followers_available=int('followers.csv' in payloads),following_available=int('following.csv' in payloads),received_available=int('social_interactions.csv' in payloads),comments_available=int('comments.csv' in payloads),kudos_available=int('reactions.csv' in payloads),**counts)
    network['mutual']=len(accepted & followed) if all(n in payloads for n in ('followers.csv','following.csv')) else None
    yield network
    yield from relations
    for filename,date_field,kind in [('reactions.csv','Reaction Date','Kudos'),('comments.csv','Comment Date','Comment')]:
        if filename not in payloads:continue
        for row in read_csv(payloads[filename]):
            timestamp=dated(row.get(date_field))
            reaction=row.get('Reaction Type','Kudos') if kind=='Kudos' else kind
            if kind=='Kudos' and reaction!='Kudos':raise ValueError('unsupported_social_reaction')
            yield dict(social_type='interaction',direction='given',interaction_type=reaction,timestamp=timestamp,**local_fields(timestamp,timezone))
    seen=set()
    if 'social_interactions.csv' in payloads:
        for row in read_csv(payloads['social_interactions.csv']):
            iid=row.get('Interaction ID','');kind=row.get('Interaction Type');actor=identifier(row.get('Actor Athlete ID'))
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',iid) or iid in seen or kind not in ('Kudos','Comment') or row.get('Activity ID') not in activity_ids:raise ValueError('invalid_received_interaction')
            seen.add(iid);timestamp=dated(row.get('Interaction Date'))
            yield dict(social_type='interaction',direction='received',interaction_type=kind,actor_id=actor,activity_id=row['Activity ID'],interaction_id=iid,is_current_follower=int(actor in accepted),timestamp=timestamp,**local_fields(timestamp,timezone))
