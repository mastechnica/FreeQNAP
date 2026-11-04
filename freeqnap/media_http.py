"""Browser media classification and single byte-range handling."""
import mimetypes
import re
from pathlib import Path
VIDEO={'.mp4','.m4v','.mov','.webm','.mkv','.ogv','.oggvideo','.mpeg','.mpg','.ts','.m2ts'}
AUDIO={'.m4b','.wma','.mp3','.m4a','.aac','.wav','.flac','.ogg','.oga','.opus','.aif','.aiff','.weba'}
IMAGE={'.jpg','.jpeg','.png','.gif','.webp','.avif','.bmp','.tif','.tiff','.ico','.heic','.heif'}
TYPES={'.m4b':'audio/mp4','.wma':'audio/x-ms-wma','.mp4':'video/mp4','.m4v':'video/mp4','.mov':'video/quicktime','.webm':'video/webm','.mkv':'video/x-matroska','.ogv':'video/ogg','.oggvideo':'video/ogg','.mpeg':'video/mpeg','.mpg':'video/mpeg','.ts':'video/mp2t','.m2ts':'video/mp2t','.mp3':'audio/mpeg','.m4a':'audio/mp4','.aac':'audio/aac','.wav':'audio/wav','.flac':'audio/flac','.ogg':'audio/ogg','.oga':'audio/ogg','.opus':'audio/ogg','.weba':'audio/webm','.aif':'audio/aiff','.aiff':'audio/aiff','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png','.gif':'image/gif','.webp':'image/webp','.avif':'image/avif','.bmp':'image/bmp','.tif':'image/tiff','.tiff':'image/tiff','.ico':'image/x-icon','.heic':'image/heic','.heif':'image/heif'}

def kind(path):
    suffix=Path(path).suffix.lower()
    return 'video' if suffix in VIDEO else 'audio' if suffix in AUDIO else 'image' if suffix in IMAGE else None

def content_type(path):return TYPES.get(Path(path).suffix.lower()) or mimetypes.guess_type(path)[0] or 'application/octet-stream'

def byte_range(value,total,etag=None,if_range=None):
    if not value or (if_range and if_range!=etag):return 0,total-1,False
    match=re.fullmatch(r'bytes=(\d*)-(\d*)',value)
    if not match or not any(match.groups()) or total==0:raise ValueError('One satisfiable byte range is required')
    first,last=match.groups()
    if not first:
        count=int(last)
        if count<=0:raise ValueError('Invalid suffix range')
        return max(0,total-count),total-1,True
    start=int(first);end=min(total-1,int(last)) if last else total-1
    if start>=total or start>end:raise ValueError('Unsatisfiable byte range')
    return start,end,True
