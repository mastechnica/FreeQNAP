"""Bounded ZIP64 writing through guarded broker reads; no source filesystem access."""
import base64,io,stat,time,zipfile,re

class Output:
    def __init__(self,destination,max_bytes=None):self.destination=destination;self.bytes=0;self.aborted=False;self.maximum=max_bytes
    def write(self,data):
        if self.aborted:raise ConnectionAbortedError('ZIP aborted; central directory deliberately omitted')
        if self.maximum is not None and self.bytes+len(data)>self.maximum:raise ValueError('ZIP exceeds the selected output/free-space limit')
        written=self.destination.write(data)
        if written is None:written=len(data)
        if written!=len(data):raise OSError('Short ZIP output write')
        self.bytes+=written;return written
    def tell(self):return self.bytes
    def seek(self,*args):raise io.UnsupportedOperation('ZIP output is streaming')
    def flush(self):self.destination.flush()

def write_zip(destination,reader,info,*,compression='store',max_bytes=None,progress=None):
    if compression not in ('store','deflate'):raise ValueError('Choose store or deflate compression')
    sink=Output(destination,max_bytes);archive=zipfile.ZipFile(sink,'w',compression=zipfile.ZIP_STORED if compression=='store' else zipfile.ZIP_DEFLATED,compresslevel=1 if compression=='deflate' else None,allowZip64=True);seen=set();budget={'entries':0,'input_bytes':0};success=False
    def member(path,name,depth=0):
        if name.startswith('/') or '\\' in name or ':' in name or any(p in ('','..','.') for p in name.split('/')) or any(ord(c)<32 for c in name):raise ValueError('ZIP member name is not a safe portable path')
        if depth>64 or budget['entries']>=200000:raise ValueError('ZIP tree limit exceeded')
        if name in seen:raise ValueError('Duplicate ZIP member name')
        seen.add(name);budget['entries']+=1;node=reader('files.bundle-node',{'ticket':info['ticket'],'path':path})
        stamp=time.localtime(max(315532800,min(node['modified_at'],4354819198)))[:6];item=zipfile.ZipInfo(name+('/' if node['directory'] else ''),stamp);item.create_system=3;item.external_attr=((stat.S_IFDIR|0o2770) if node['directory'] else (stat.S_IFREG|0o660))<<16;item.compress_type=archive.compression;item._compresslevel=1 if compression=='deflate' else None
        if node['directory']:
            archive.writestr(item,b'');page=node
            while True:
                for child in page['entries']:
                    if child.get('symlink'):raise ValueError('ZIP selection contains a symbolic link; choose regular items')
                    member('/'.join(v for v in [path,child['name']] if v),name+'/'+child['name'],depth+1)
                if page['next_offset'] is None:break
                page=reader('files.bundle-node',{'ticket':info['ticket'],'path':path,'offset':page['next_offset'],'expected_etag':node['etag']})
            reader('files.bundle-node',{'ticket':info['ticket'],'path':path,'expected_etag':node['etag']})
        else:
            first=reader('files.bundle-read',{'ticket':info['ticket'],'path':path,'offset':0,'count':1})
            if first['total_bytes']!=node['bytes']:raise ValueError('ZIP source size changed')
            budget['input_bytes']+=first['total_bytes']
            if budget['input_bytes']>16*1024**4:raise ValueError('ZIP selection exceeds the 16 TiB input limit')
            item.file_size=first['total_bytes'];offset=0
            with archive.open(item,'w',force_zip64=True) as target:
                while offset<first['total_bytes']:
                    value=reader('files.bundle-read',{'ticket':info['ticket'],'path':path,'offset':offset,'count':min(512*1024,first['total_bytes']-offset)})
                    chunk=base64.b64decode(value['data_base64'],validate=True)
                    if value['etag']!=first['etag'] or len(chunk)!=min(512*1024,first['total_bytes']-offset):raise ValueError('ZIP source changed or returned a short read')
                    target.write(chunk);offset+=len(chunk)
                    if progress:progress({**budget,'output_bytes':sink.bytes})
        if progress:progress({**budget,'output_bytes':sink.bytes})
    try:
        for root in info['roots']:member(root['path'],root['name'])
        archive.close();success=True;return {**budget,'output_bytes':sink.bytes}
    finally:
        if not success:
            sink.aborted=True
            try:archive.close()
            except (OSError,ValueError):pass
