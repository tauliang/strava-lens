"""Occurrence-aware CSV parser; export strings are inert values."""
import collections
import copy
import csv
import datetime as dt
import hashlib
import io
import math
import re
from zoneinfo import ZoneInfo

PARSER_VERSION='1.0.3'
def number(value):
    try:
        n=float(str(value).replace(',',''))
        return n if math.isfinite(n) else None
    except (ValueError,TypeError):return None

def read_csv(payload):
    it=csv.reader(io.StringIO(payload.decode('utf-8-sig')))
    try:header=next(it)
    except StopIteration:raise ValueError('empty_csv')
    seen=collections.Counter(); keys=[]
    for h in header:
        seen[h]+=1;keys.append(h if seen[h]==1 else h+'__'+str(seen[h]))
    for row in it:
        if not row:continue
        if len(row)!=len(keys):raise ValueError('csv_row_width')
        yield dict(zip(keys,row))

def local_fields(epoch, timezone):
    date=dt.datetime.fromtimestamp(epoch,dt.timezone.utc).astimezone(ZoneInfo(timezone)).date()
    return {'local_date':date.isoformat(),'local_week_start':(date-dt.timedelta(days=date.weekday())).isoformat(),'local_month':date.strftime('%Y-%m'),'local_year':date.year}

def quality(record):
    # Recompute metric-specific validity after corrections, preserving provenance flags.
    flags=[x for x in record.get('quality_flags',[]) if x not in ('distance_invalid','duration_conflict','distance_outlier')]
    distance=record.get('distance_m');moving=record.get('moving_time_s');elapsed=record.get('elapsed_time_s')
    record['distance_valid']=int(distance is not None and distance>=0)
    record['duration_valid']=int(moving is not None and elapsed is not None and 0<=moving<=elapsed+1)
    if not record['distance_valid']:flags.append('distance_invalid')
    if not record['duration_valid']:flags.append('duration_conflict')
    speed=distance/moving if distance is not None and moving and moving>0 else 0
    limit={'Run':12,'Walk':5,'Hike':7,'Nordic Ski':15,'Weight Training':1}.get(record.get('sport'),45)
    if speed>limit:flags.append('distance_outlier');record['distance_valid']=0
    record['pace_valid']=int(record['distance_valid'] and record['duration_valid'] and bool(distance and distance>0))
    record['quality_flags']=sorted(set(flags));record['flagged']=int(bool(flags))
    record['pace_min_km']=moving*1000/(60*distance) if record['pace_valid'] else None
    return record

def parse_activities(csv_bytes, athlete_id, snapshot_id, timezone='UTC'):
    rows=list(read_csv(csv_bytes))
    if not rows:raise ValueError('no_activities')
    required={'Activity ID','Activity Date','Activity Type','Filename','Elapsed Time__2','Moving Time','Distance__2'}
    if not required.issubset(rows[0]):raise ValueError('unsupported_activity_schema')
    ids=set()
    for r in rows:
        aid=r['Activity ID']
        if not re.fullmatch(r'[0-9]{1,24}',aid) or aid in ids:raise ValueError('invalid_or_duplicate_activity_id')
        ids.add(aid)
        try:epoch=dt.datetime.strptime(r['Activity Date'],'%b %d, %Y, %I:%M:%S %p').replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:raise ValueError('invalid_activity_date')
        out={'kind':'activity','athlete_id':athlete_id,'snapshot_id':snapshot_id,'activity_id':aid,'event_id':hashlib.sha256((snapshot_id+':activity:'+aid).encode()).hexdigest(),'schema_version':1,'parser_version':PARSER_VERSION,'timestamp':epoch,'time_basis':'csv_utc','activity_name':r.get('Activity Name',''),'sport':r['Activity Type'],'filename':r['Filename'],'gear':r.get('Activity Gear') or r.get('Gear') or r.get('Bike') or '(unassigned)','quality_flags':[]}
        fields={'distance_m':'Distance__2','elapsed_time_s':'Elapsed Time__2','moving_time_s':'Moving Time','elevation_gain_m':'Elevation Gain','relative_effort':'Relative Effort__2','raw_relative_effort':'Relative Effort','raw_distance_km':'Distance','raw_elapsed_time_s':'Elapsed Time','athlete_weight':'Athlete Weight','average_hr':'Average Heart Rate','max_hr':'Max Heart Rate__2','average_watts':'Average Watts','average_cadence':'Average Cadence','calories':'Calories','grade_adjusted_pace':'Average Grade Adjusted Pace','sets':'Total Sets','reps':'Total Reps'}
        for field,column in fields.items():out[field]=number(r.get(column))
        out['max_hr_source']='detailed' if out['max_hr'] is not None else 'missing'
        if out['max_hr'] is None and number(r.get('Max Heart Rate')) is not None:
            out['max_hr']=number(r.get('Max Heart Rate'));out['max_hr_source']='summary'
        if out['relative_effort'] is not None and out['relative_effort']<0:out['relative_effort']=None;out['quality_flags'].append('invalid_effort')
        if out['relative_effort'] is not None and out['raw_relative_effort'] is not None and out['relative_effort']!=out['raw_relative_effort']:out['quality_flags'].append('effort_conflict')
        out.update(local_fields(epoch,timezone));yield quality(out)

def apply_overrides(record, overrides):
    out=copy.deepcopy(record)
    allowed={'distance_m','elapsed_time_s','moving_time_s','elevation_gain_m','relative_effort','average_hr','gear','sport'}
    for row in overrides:
        if row.get('activity_id')!=out['activity_id']:continue
        field=row.get('field')
        if field not in allowed or not row.get('reason') or not row.get('revision'):raise ValueError('invalid_override')
        value=row.get('value') if field in ('gear','sport') else number(row.get('value'))
        if value is None or (isinstance(value,(int,float)) and value<0):raise ValueError('invalid_override_value')
        out[field]=value;out.setdefault('override_revisions',[]).append(str(row['revision']))
    return quality(out)

def parse_preferences(payload):
    allowed={'Maximum Heartrate':'maximum_hr','Functional Threshold Power':'ftp','Measurement Preference':'units'}
    rows=list(read_csv(payload));return {target:rows[0].get(source) for source,target in allowed.items()} if rows else {}
