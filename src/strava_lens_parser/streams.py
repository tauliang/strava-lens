"""Normalize FIT/GPX into SI records; integrity failures quarantine a stream."""
import datetime as dt
import io
import math
import xml.etree.ElementTree as ET
import fitdecode
from .csv_parser import number

FIT_EPOCH=631065600

def distance(lat1,lon1,lat2,lon2):
    a,b=math.radians(lat1),math.radians(lat2);da=b-a;dl=math.radians(lon2-lon1)
    h=math.sin(da/2)**2+math.cos(a)*math.cos(b)*math.sin(dl/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))

def epoch(value):
    if isinstance(value,dt.datetime):return value.replace(tzinfo=dt.timezone.utc).timestamp()
    return None

def decode_activity(raw,filename,revision_id):
    name=filename[:-3] if filename.endswith('.gz') else filename
    try:
        if name.endswith('.fit'):yield from _fit(raw)
        elif name.endswith('.gpx'):yield from _gpx(raw)
        else:raise ValueError('unsupported_stream_format')
    except Exception as error:
        raise ValueError('stream_decode_failed') from error

def _fit(raw):
    with fitdecode.FitReader(io.BytesIO(raw),check_crc=fitdecode.CrcCheck.RAISE,error_handling=fitdecode.ErrorHandling.RAISE) as reader:
        for frame in reader:
            if not isinstance(frame,fitdecode.FitDataMessage):continue
            values={f.name:f.value for f in frame.fields if f.value is not None}
            timestamp=epoch(values.get('timestamp'))
            if timestamp is None:continue
            if frame.name=='event' and values.get('event')=='timer':
                yield {'kind':'timer','timestamp':timestamp,'timer_state':str(values.get('event_type',''))};continue
            if frame.name not in ('record','lap','session'):continue
            if frame.name=='session':continue
            r={'kind':'sample' if frame.name=='record' else 'lap','timestamp':timestamp}
            mapping={'distance_m':'distance' if frame.name=='record' else 'total_distance','hr':'heart_rate' if frame.name=='record' else 'avg_heart_rate','cadence':'cadence' if frame.name=='record' else 'avg_cadence','altitude_m':'enhanced_altitude' if 'enhanced_altitude' in values else 'altitude','speed_mps':'enhanced_speed' if 'enhanced_speed' in values else 'speed','watts':'power','elapsed_time_s':'total_elapsed_time','moving_time_s':'total_timer_time'}
            for key,field in mapping.items():r[key]=number(values.get(field))
            if r['hr'] is not None and not 0<r['hr']<=255:r['hr']=None
            for field,key in [('position_lat','latitude'),('position_long','longitude')]:
                value=number(values.get(field));r[key]=value*180/2**31 if value is not None else None
            if r.get('latitude') is not None and not -90<=r['latitude']<=90:raise ValueError('invalid_latitude')
            yield r

def _gpx(raw):
    # Reject non-UTF8 encodings and declarations; UTF8 GPX is the supported archive format.
    text=raw.decode('utf-8-sig')
    if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper() or '\x00' in text:raise ValueError('xml_declaration_rejected')
    root=ET.fromstring(text);total=0;previous=None
    for segment in root.iter():
        if segment.tag.split('}')[-1]!='trkseg':continue
        previous=None
        for pt in segment:
            if pt.tag.split('}')[-1]!='trkpt':continue
            lat=number(pt.get('lat'));lon=number(pt.get('lon'))
            if lat is None or lon is None or not (-90<=lat<=90 and -180<=lon<=180):raise ValueError('invalid_coordinate')
            values={e.tag.split('}')[-1]:e.text for e in pt.iter() if e.text}
            if not values.get('time'):continue
            time=dt.datetime.fromisoformat(values['time'].replace('Z','+00:00'))
            if time.tzinfo is None:raise ValueError('gpx_timezone_required')
            speed=None
            if previous:
                delta=distance(previous[0],previous[1],lat,lon);total+=delta;gap=time.timestamp()-previous[2]
                if 0<gap<=30 and delta/gap<=45:speed=delta/gap
            yield {'kind':'sample','timestamp':time.timestamp(),'distance_m':total,'latitude':lat,'longitude':lon,'hr':number(values.get('hr')),'cadence':number(values.get('cad')),'altitude_m':number(values.get('ele')),'watts':number(values.get('power')),'speed_mps':speed,'segment_start':int(previous is None)}
            previous=(lat,lon,time.timestamp())
