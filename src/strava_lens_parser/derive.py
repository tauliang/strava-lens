"""Deterministic duration-aware analysis. No proprietary training estimates."""
import bisect
import math
from .privacy import cells
from .csv_parser import number

def zone_intervals(samples,pause_events,boundaries):
    boundaries=[float(x) for x in boundaries]
    if len(boundaries)!=4 or boundaries!=sorted(set(boundaries)) or any(not math.isfinite(x) or x<=0 for x in boundaries):raise ValueError('invalid_hr_zones')
    zones=[0.]*5;paused=0.;unobserved=0.
    events=sorted(pause_events,key=lambda x:x['timestamp'])
    for a,b in zip(samples,samples[1:]):
        start,end=a['timestamp'],b['timestamp']
        if end<=start:continue
        cuts=[start]+[e['timestamp'] for e in events if start<e['timestamp']<end]+[end]
        for left,right in zip(cuts,cuts[1:]):
            active=True
            for event in events:
                if event['timestamp']>left:break
                active=event['timer_state']=='start'
            duration=right-left
            if not active:paused+=duration
            elif end-start>30 or b.get('segment_start') or a.get('hr') is None:unobserved+=duration
            else:zones[bisect.bisect_right(boundaries,a['hr'])]+=duration
    return {'zone_seconds':zones,'observed_s':sum(zones),'unobserved_s':unobserved,'paused_s':paused}

def _segments(samples,max_speed=45):
    result=[];current=[]
    for p in samples:
        d=p.get('distance_m');t=p.get('timestamp')
        if d is None or t is None or d<0:
            if current:result.append(current);current=[]
            continue
        if current:
            a=current[-1];gap=t-a['timestamp'];delta=d-a['distance_m']
            if gap<=0 or gap>30 or delta<0 or delta/max(gap,.001)>max_speed or p.get('segment_start'):
                result.append(current);current=[]
        current.append(p)
    if current:result.append(current)
    return result

def _time_at(distances,times,value):
    j=bisect.bisect_left(distances,value)
    if j>=len(distances):return None
    if distances[j]==value:return times[j]
    if j==0:return None
    gap=distances[j]-distances[j-1]
    return times[j-1]+(times[j]-times[j-1])*(value-distances[j-1])/gap if gap>0 else None

def best_efforts(samples,targets_m,max_speed=45):
    best={}
    for segment in _segments(samples,max_speed):
        ds=[p['distance_m'] for p in segment];ts=[p['timestamp'] for p in segment]
        for target in targets_m:
            candidates=[]
            for d,t in zip(ds,ts):
                end=_time_at(ds,ts,d+target)
                if end is not None:candidates.append((end-t,t,end))
                start=_time_at(ds,ts,d-target)
                if start is not None:candidates.append((t-start,start,t))
            if candidates:
                duration,start,end=min(candidates)
                if duration>0 and (target not in best or duration<best[target]['duration_s']):best[target]={'kind':'best_effort','timestamp':start,'target_m':target,'duration_s':duration,'end_timestamp':end,'calculation_version':1}
    return [best[t] for t in sorted(best)]

def derive_records(records,config,activity):
    samples=[r for r in records if r['kind']=='sample'];timers=[r for r in records if r['kind']=='timer'];start=samples[0]['timestamp'] if samples else activity['timestamp']
    for row in records:
        if row['kind']=='timer':continue
        r={k:v for k,v in row.items() if k not in ('latitude','longitude')};r['elapsed_s']=r['timestamp']-start
        if r.get('speed_mps') and r['speed_mps']>0:r['pace_min_km']=1000/(60*r['speed_mps'])
        yield r
        if config.get('exact_gps') and row.get('latitude') is not None and row.get('longitude') is not None:
            yield {'kind':'gps','timestamp':row['timestamp'],'latitude':row['latitude'],'longitude':row['longitude'],'elapsed_s':r['elapsed_s']}
    # Effective-dated custom boundaries. No implicit max-HR estimate.
    zones=config.get('hr_zones',[])
    if zones and isinstance(zones[0],dict):
        date=activity.get('local_date','9999-12-31');eligible=[v for v in zones if v['effective_date']<=date]
        zones=max(eligible,key=lambda v:v['effective_date'])['boundaries'] if eligible else []
    if zones and samples:
        result=zone_intervals(samples,timers,zones)
        for i,seconds in enumerate(result['zone_seconds']):
            yield {'kind':'zone','timestamp':start,'zone':i+1,'seconds':seconds,'observed_s':result['observed_s'],'unobserved_s':result['unobserved_s'],'paused_s':result['paused_s'],'calculation_version':1,'sport':activity['sport'],'local_week_start':activity.get('local_week_start'),'local_year':activity.get('local_year')}
    if activity['sport']=='Run' and activity.get('duration_valid'):
        for row in best_efforts(samples,[1000,1609.344,5000,10000,21097.5,42195],max_speed=12):yield row
        segments=_segments(samples,max_speed=12)
        if len(segments)==1 and len(segments[0])==len(samples) and len(samples)>1:
            ds=[p['distance_m'] for p in samples];ts=[p['timestamp'] for p in samples];previous=ts[0]
            for km in range(1,int((ds[-1]-ds[0])/1000)+1):
                end=_time_at(ds,ts,ds[0]+1000*km)
                yield {'kind':'split','timestamp':previous,'split':km,'distance_m':1000,'duration_s':end-previous,'calculation_version':1};previous=end
    for cell in cells(samples,config.get('privacy_zones',[]),endpoint_mask_m=200):yield dict(cell,kind='geography',timestamp=start,calculation_version=1,sport=activity['sport'])
