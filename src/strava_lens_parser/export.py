"""Framework-independent normalized export iterator; persistence is caller-owned."""
import collections
import copy
import datetime as dt
import hashlib
import json
import math
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional, Union
from zoneinfo import ZoneInfo
from .archive import inspect_archive, read_member
from .csv_parser import PARSER_VERSION, parse_activities, apply_overrides, local_fields


@dataclass(frozen=True)
class ExportIdentity:
    archive_sha256: str
    snapshot_id: str
    parser_version: str = PARSER_VERSION
    schema_version: int = 1


def _identity(info, decode, timezone, athlete_id, config):
    ZoneInfo(timezone)
    if not isinstance(athlete_id, str) or not athlete_id:
        raise ValueError('invalid_athlete_id')
    settings = {'parser': PARSER_VERSION, 'decode': decode, 'timezone': timezone,
                'athlete': athlete_id, 'config': config}
    sid = hashlib.sha256((info['sha256'] + json.dumps(settings, sort_keys=True, allow_nan=False)).encode()).hexdigest()
    return ExportIdentity(info['sha256'], sid)


def inspect_export(path: Union[str, Path], *, decode_streams: bool = True,
                   timezone: str = 'UTC', athlete_id: str = 'personal',
                   config: Optional[dict] = None) -> ExportIdentity:
    """Validate archive metadata and identify it; no files are written."""
    return _identity(inspect_archive(Path(path)), decode_streams, timezone,
                     athlete_id, copy.deepcopy(config or {}))


def iter_export(path: Union[str, Path], *, decode_streams: bool = True,
                timezone: str = 'UTC', athlete_id: str = 'personal',
                config: Optional[dict] = None,
                observed_at: Optional[float] = None) -> Iterator[dict[str, Any]]:
    """Yield provisional records, ending with a snapshot manifest on success.

    Consume to completion before activating an import. Fatal errors can occur
    after records have been yielded. Persist the first observation time and
    pass it on retries for repeatable import-date social/goal records.
    """
    path = Path(path)
    config = copy.deepcopy(config or {})
    decode = decode_streams
    info = inspect_archive(path)
    sid = _identity(info, decode, timezone, athlete_id, config).snapshot_id
    epoch = time.time() if observed_at is None else float(observed_at)
    if not math.isfinite(epoch):
        raise ValueError('invalid_observation_time')
    counts = collections.Counter()
    failures = 0
    expanded = 0
    def track(record):
        counts[record['kind']] += 1
        return record
    def base(kind):
        return {'kind': kind, 'athlete_id': athlete_id, 'snapshot_id': sid,
                'timestamp': epoch, 'import_epoch': epoch, 'schema_version': 1,
                'parser_version': PARSER_VERSION}
    with zipfile.ZipFile(path) as z:
        config=dict(config)
        if 'privacy_zones.csv' in info['members']:
            from .csv_parser import read_csv
            zones=list(config.get('privacy_zones',[]))
            for row in read_csv(read_member(z,'privacy_zones.csv')):
                coords=[float(x) for x in re.findall(r'[-+]?\d+(?:\.\d+)?',row.get('Latitude & Longitude',''))]
                radius_text=row.get('Radius','');radius_values=re.findall(r'\d+(?:\.\d+)?',radius_text)
                if len(coords)!=2 or not radius_values:raise ValueError('invalid_privacy_zone')
                radius=float(radius_values[0])*(1000 if 'kilo' in radius_text.lower() else 1609.344 if 'mile' in radius_text.lower() else 1)
                if not (-90<=coords[0]<=90 and -180<=coords[1]<=180 and radius>0):raise ValueError('invalid_privacy_zone')
                zones.append(dict(latitude=coords[0],longitude=coords[1],radius_m=radius))
            config['privacy_zones']=zones
        activities=list(parse_activities(read_member(z,'activities.csv'),athlete_id,sid,timezone))
        overrides=config.get('overrides',[]);processed=[]
        for activity in activities:
            activity=apply_overrides(activity,overrides)
            filename=activity['filename'];revision=None;status='summary_only';telemetry=[]
            if filename and filename not in info['members']:activity['quality_flags'].append('missing_stream');status='missing'
            elif filename and decode:
                try:
                    raw=read_member(z,filename);expanded+=len(raw)
                    if expanded>4*1024**3:raise ValueError('aggregate_decode_limit')
                    revision=hashlib.sha256((athlete_id+':'+activity['activity_id']+':'+PARSER_VERSION).encode()+raw).hexdigest()
                    # Configuration determines derived data and privacy; raw revision remains reusable.
                    revision=hashlib.sha256((revision+json.dumps(config,sort_keys=True)).encode()).hexdigest()
                    from .streams import decode_activity
                    from .derive import derive_records
                    raw_records=list(decode_activity(raw,filename,revision))
                    first=next((r['timestamp'] for r in raw_records if r['kind']=='sample'),None)
                    if first is not None:
                        activity['csv_timestamp']=activity['timestamp'];activity['stream_timestamp']=first
                        if abs(first-activity['timestamp'])>30:activity['quality_flags'].append('timestamp_conflict')
                        activity['timestamp']=first;activity['time_basis']='stream_utc';activity.update(local_fields(first,timezone))
                    context={k:activity.get(k) for k in ('sport','duration_valid','distance_valid','timestamp','local_date','local_week_start')}
                    context['timezone']=timezone
                    revision=hashlib.sha256((revision+json.dumps(context,sort_keys=True)).encode()).hexdigest()
                    telemetry=list(derive_records(raw_records,config,activity))
                    for ordinal,r in enumerate(telemetry):
                        r.update({'athlete_id':athlete_id,'activity_id':activity['activity_id'],'stream_revision_id':revision,'schema_version':1,'parser_version':PARSER_VERSION})
                        r['event_id']=hashlib.sha256((revision+':'+r['kind']+':'+str(ordinal)).encode()).hexdigest()
                        yield track(r)
                    status='decoded'
                except (ValueError,KeyError,EOFError,OSError) as error:
                    if str(error)=='aggregate_decode_limit':raise
                    failures+=1;status='quarantined';activity['quality_flags'].append('stream_quarantined');revision=None
            activity['comparison_month_day']=local_fields(epoch,timezone)['local_date'][5:]
            activity['stream_status']=status;activity['stream_revision_id']=revision or ''
            activity['flagged']=int(bool(activity['quality_flags']));activity['import_epoch']=epoch
            yield track(activity);processed.append(activity)
            if revision:
                membership=base('membership');membership.update({'activity_id':activity['activity_id'],'stream_revision_id':revision,'expected_records':len(telemetry),'event_id':hashlib.sha256((sid+':member:'+revision).encode()).hexdigest()});yield track(membership)
        from .social import records as social_records
        social_files=('followers.csv','following.csv','reactions.csv','comments.csv','social_interactions.csv')
        payloads={name:read_member(z,name) for name in social_files if name in info['members']}
        for ordinal,row in enumerate(social_records(payloads,{a['activity_id'] for a in processed},epoch,timezone,info['sha256'])):
            social=base('social');social.update(row);social['event_id']=sid+':social:'+str(ordinal);yield track(social)
        if 'structured_details.csv' in info['members']:
            from .csv_parser import read_csv,number
            by_id={a['activity_id']:a for a in activities}
            for ordinal,row in enumerate(read_csv(read_member(z,'structured_details.csv'))):
                activity=by_id.get(row.get('Activity ID'))
                if activity is None:continue
                exercise=base('exercise');exercise.update(activity_id=activity['activity_id'],timestamp=activity['timestamp'],exercise=row.get('Exercise Name',''),repetitions=number(row.get('Repetitions')),duration_s=number(row.get('Duration (seconds)')),weight_raw=row.get('Weight',''),event_id=sid+':exercise:'+str(ordinal))
                yield track(exercise)
        # Configured goals/preferences are kept as operational data, never raw account demographics.
        for i,goal in enumerate(config.get('goals',[])):
            if goal.get('metric') not in ('distance_m','moving_time_s','activity_count','elevation_gain_m'):raise ValueError('invalid_goal_metric')
            from .csv_parser import number
            target=number(goal.get('target'))
            if target is None or target<=0:raise ValueError('invalid_goal_target')
            period=goal.get('period');today=dt.date.fromisoformat(local_fields(epoch,timezone)['local_date'])
            if period=='year':begin=today.replace(month=1,day=1)
            elif period=='month':begin=today.replace(day=1)
            elif period=='week':begin=today-dt.timedelta(days=today.weekday())
            else:raise ValueError('invalid_goal_period')
            selected=[a for a in processed if a['sport']==goal.get('sport') and begin.isoformat()<=a['local_date']<=today.isoformat()]
            value=sum(1 if goal['metric']=='activity_count' else (a.get(goal['metric']) or 0) for a in selected if (goal['metric']!='distance_m' or a['distance_valid']) and (goal['metric']!='moving_time_s' or a['duration_valid']))
            item=base('goal');item.update({k:goal.get(k) for k in ('sport','metric','period')});item.update(target=target,event_id=sid+':goal:'+str(i),progress_value=value,progress_pct=round(100*value/target,1),period_start=begin.isoformat(),as_of=today.isoformat());yield track(item)
    for i,threshold in enumerate(config.get('gear_thresholds',[])):
        from .csv_parser import number
        target=number(threshold.get('distance_m'));gear=threshold.get('gear')
        if not isinstance(gear,str) or not gear or target is None or target<=0:raise ValueError('invalid_gear_threshold')
        recorded=sum(a['distance_m'] for a in processed if a['gear']==gear and a['distance_valid'])
        item=base('gear_threshold');item.update(gear=gear,target_m=target,recorded_m=recorded,remaining_m=target-recorded,event_id=sid+':gear:'+str(i));yield track(item)
    record=base('snapshot');record.update({'event_id':sid+':snapshot','expected_records':len(activities)+counts.get('social',0)+counts.get('exercise',0)+counts.get('goal',0)+counts.get('gear_threshold',0),'expected_groups':1+counts.get('membership',0),'quarantined_streams':failures,'decode_enabled':int(decode),'timezone':timezone,'exact_gps':int(bool(config.get('exact_gps',False)))})
    yield track(record)
