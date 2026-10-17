"""Bounded archive reads with no filesystem extraction."""
import gzip
import hashlib
import stat
import zipfile
from pathlib import PurePosixPath

MAX_MEMBER=128*1024*1024

def inspect_archive(path,max_archive_bytes=2*1024**3,max_expanded_bytes=4*1024**3,max_members=20000):
    if path.stat().st_size>max_archive_bytes:raise ValueError('archive_size_limit')
    seen=set();total=0
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name=info.filename;p=PurePosixPath(name)
            if name in seen or '\\' in name or p.is_absolute() or '..' in p.parts or ':' in name or '\x00' in name:raise ValueError('unsafe_archive_path')
            if stat.S_ISLNK(info.external_attr>>16) or info.flag_bits&1:raise ValueError('unsupported_archive_member')
            seen.add(name);total+=info.file_size
            if len(seen)>max_members or total>max_expanded_bytes:raise ValueError('archive_expansion_limit')
            if info.file_size/max(1,info.compress_size)>200:raise ValueError('archive_ratio_limit')
        if 'activities.csv' not in seen:raise ValueError('missing_activities_csv')
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return {'sha256':digest.hexdigest(),'members':seen,'outer_bytes':total}

def read_member(z,name,max_bytes=MAX_MEMBER):
    info=z.getinfo(name)
    if info.file_size>max_bytes:raise ValueError('member_size_limit')
    with z.open(info) as source:
        stream=gzip.GzipFile(fileobj=source) if name.endswith('.gz') else source
        try:data=stream.read(max_bytes+1)
        finally:
            if stream is not source:stream.close()
    if len(data)>max_bytes:raise ValueError('decoded_member_size_limit')
    if len(data)/max(1,info.file_size)>200:raise ValueError('nested_ratio_limit')
    return data
