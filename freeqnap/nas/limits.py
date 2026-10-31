"""Conservative runtime filesystem addressability, separate from raw disk capacity."""
import os
import struct

def ext4_limit(pointer_bytes=None,page_bytes=None):
    bits=8*(pointer_bytes if pointer_bytes is not None else struct.calcsize('P'))
    page=page_bytes if page_bytes is not None else os.sysconf('SC_PAGE_SIZE')
    return (1<<bits)*page if bits<64 else None

def require_ext4_size(byte_count,pointer_bytes=None,page_bytes=None):
    limit=ext4_limit(pointer_bytes,page_bytes)
    if limit is not None and byte_count>limit:
        raise ValueError('This 32-bit kernel cannot safely mount one ext4 filesystem larger than 16 TiB. Use bounded logical volumes; no initialization was started.')
    return limit
