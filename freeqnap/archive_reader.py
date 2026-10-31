"""Read libarchive entries without allowing the library to write to the filesystem."""
import ctypes as C
import ctypes.util
import os
import stat


def safe_member(value):
    if not isinstance(value,str) or not value or value.startswith('/') or '\\' in value or ':' in value or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Unsafe archive member path')
    parts=value.rstrip('/').split('/')
    while parts and parts[0]=='.':parts.pop(0)
    if not parts:return ()
    if len(parts)>64 or any(p in ('','..','.') or p.startswith('.freeqnap') or len(os.fsencode(p))>255 for p in parts):raise ValueError('Unsafe/reserved archive member path or excessive depth')
    return tuple(parts)


class Reader:
    def __init__(self,fd):
        library=ctypes.util.find_library('archive')
        if not library:raise ValueError('Archive support is unavailable; install libarchive13t64')
        self.lib=C.CDLL(library);self.handle=None
        signatures={
            'archive_read_new':(C.c_void_p,[]),'archive_read_support_format_all':(C.c_int,[C.c_void_p]),
            'archive_read_support_format_raw':(C.c_int,[C.c_void_p]),
            'archive_read_open_fd':(C.c_int,[C.c_void_p,C.c_int,C.c_size_t]),
            'archive_read_next_header':(C.c_int,[C.c_void_p,C.POINTER(C.c_void_p)]),
            'archive_read_data':(C.c_ssize_t,[C.c_void_p,C.c_void_p,C.c_size_t]),
            'archive_read_free':(C.c_int,[C.c_void_p]),'archive_error_string':(C.c_char_p,[C.c_void_p]),
            'archive_entry_pathname_utf8':(C.c_char_p,[C.c_void_p]),'archive_entry_size':(C.c_int64,[C.c_void_p]),'archive_entry_size_is_set':(C.c_int,[C.c_void_p]),
            'archive_entry_filetype':(C.c_uint,[C.c_void_p]),'archive_entry_symlink':(C.c_char_p,[C.c_void_p]),
            'archive_entry_hardlink':(C.c_char_p,[C.c_void_p]),'archive_entry_is_encrypted':(C.c_int,[C.c_void_p]),
            'archive_format':(C.c_int,[C.c_void_p]),'archive_filter_code':(C.c_int,[C.c_void_p,C.c_int])}
        for n,(restype,args) in signatures.items():
            f=getattr(self.lib,n);f.restype=restype;f.argtypes=args
        self.handle=self.lib.archive_read_new()
        try:
            self.check(self.lib.archive_read_support_format_all(self.handle));self.check(self.lib.archive_read_support_format_raw(self.handle))
            # Built-in filters only: never ask libarchive to launch external programs.
            for name in ('gzip','bzip2','xz','lzma','zstd','lz4'):
                fn=getattr(self.lib,'archive_read_support_filter_'+name,None)
                if fn:fn.argtypes=[C.c_void_p];fn.restype=C.c_int;fn(self.handle)
            self.check(self.lib.archive_read_open_fd(self.handle,fd,1024*1024))
        except Exception:self.close();raise
    def check(self,result):
        if result<0:
            message=self.lib.archive_error_string(self.handle)
            raise ValueError('Archive rejected: '+(message.decode('utf-8','replace') if message else str(result)))
    def entries(self):
        while True:
            entry=C.c_void_p();result=self.lib.archive_read_next_header(self.handle,C.byref(entry))
            if result==1:return
            self.check(result)
            raw=self.lib.archive_entry_pathname_utf8(entry)
            if not raw:raise ValueError('Archive filename is missing or not UTF-8')
            if self.lib.archive_entry_is_encrypted(entry) or self.lib.archive_entry_symlink(entry) is not None or self.lib.archive_entry_hardlink(entry) is not None:raise ValueError('Encrypted entries and symbolic/hard links are not extracted')
            mode=self.lib.archive_entry_filetype(entry)
            if mode not in (stat.S_IFREG,stat.S_IFDIR):raise ValueError('Only regular files and directories are extracted')
            raw_format=self.lib.archive_format(self.handle)&0xff0000==0x090000
            if raw_format and self.lib.archive_filter_code(self.handle,0)==0:raise ValueError('File is not a supported compressed archive')
            yield {'name':raw.decode('utf-8','strict'),'directory':mode==stat.S_IFDIR,'size':self.lib.archive_entry_size(entry) if self.lib.archive_entry_size_is_set(entry) else -1,'raw':raw_format}
    def chunks(self):
        buf=C.create_string_buffer(1024*1024)
        while True:
            count=self.lib.archive_read_data(self.handle,buf,len(buf));self.check(count)
            if not count:return
            yield buf.raw[:count]
    def close(self):
        if self.handle:self.lib.archive_read_free(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
