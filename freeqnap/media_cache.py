"""Private HTTP image caching; authorization must succeed before any 304."""
import hashlib
from pathlib import PurePosixPath

POLICY = 'private, no-cache, max-age=0, must-revalidate'


def preview_resource(photo, radio, variant, path, inline):
    return (photo and variant in ('thumbnail', 'preview') or
            radio and variant == 'cover' or
            inline and PurePosixPath(path.lower()).name in ('cover.jpg','cover.jpeg','cover.png','folder.jpg','poster.jpg','albumart.jpg'))


def tag(value, user, shared=''):
    return '"'+hashlib.sha256((str(user)+'\0'+str(shared)+'\0'+str(value)).encode()).hexdigest()+'"'


def matches(header, etag):
    return any(value.strip().removeprefix('W/') in ('*', etag) for value in (header or '').split(','))
