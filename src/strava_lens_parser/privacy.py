"""Conservative privacy masks applied before any shared geographic output."""
import math
from .streams import distance

def _valid(p):
    return p.get('latitude') is not None and p.get('longitude') is not None and -90<=p['latitude']<=90 and -180<=p['longitude']<=180

def sanitize_track(points,zones,endpoint_mask_m=200):
    points=[p for p in points if _valid(p)]
    if len(points)<2:return []
    cumulative=[0.]
    for a,b in zip(points,points[1:]):cumulative.append(cumulative[-1]+distance(a['latitude'],a['longitude'],b['latitude'],b['longitude']))
    segments=[];current=[]
    for i,p in enumerate(points):
        masked=cumulative[i]<endpoint_mask_m or cumulative[-1]-cumulative[i]<endpoint_mask_m
        for z in zones:
            if distance(p['latitude'],p['longitude'],z['latitude'],z['longitude'])<=z['radius_m']:masked=True
        if p.get('segment_start') and current:segments.append(current);current=[]
        if masked:
            if current:segments.append(current);current=[]
        else:current.append(dict(p))
    if current:segments.append(current)
    return segments

def cells(points,zones,endpoint_mask_m=200):
    result={};protected=list(zones)
    valid=[p for p in points if _valid(p)]
    if endpoint_mask_m>0 and valid:
        protected.extend(dict(latitude=p['latitude'],longitude=p['longitude'],radius_m=endpoint_mask_m) for p in (valid[0],valid[-1]))
    for segment in sanitize_track(points,zones,endpoint_mask_m):
        for p in segment:
            lat=math.floor(p['latitude']*100)/100+.005;lon=math.floor(p['longitude']*100)/100+.005
            # Bounding-circle exclusion is conservative for the entire cell, including corners.
            radius=distance(lat,lon,lat+.005,lon+.005)
            if any(distance(lat,lon,z['latitude'],z['longitude'])<=z['radius_m']+radius for z in protected):continue
            key=(round(lat,3),round(lon,3));result[key]={'latitude':key[0],'longitude':key[1],'visits':1}
    return list(result.values())
