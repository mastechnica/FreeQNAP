#!/usr/bin/env python3
"""AuraView EyeQ Connector App for AuraStore (including FreeQNAP hardware).

Only local configuration selects a NAS identity and folders. Cloud requests may
read catalog IDs; they cannot change users, browse arbitrary paths or mutate files.
"""
import argparse
import asyncio
import base64
import contextlib
import sqlite3
import getpass
import hashlib
import json
import mimetypes
import math
import os
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

CATEGORIES={'music','books','podcasts','photos','videos','folders'}
MEDIA_EXT={'.mp3','.m4a','.m4b','.aac','.flac','.ogg','.opus','.wav','.aiff','.mp4','.m4v','.mov','.webm','.mkv','.jpg','.jpeg','.png','.webp','.gif','.heic','.pdf','.epub','.txt','.docx','.azw','.azw3','.mobi','.kpf','.aif','.alac','.wma','.avi','.m2ts','.ts','.tif','.tiff'}

def integer(value, low, high):
    if type(value) is not int or not low<=value<=high: raise ValueError('Invalid range')
    return value

class ReadState:
    """Use existing console state without schema creation or journal-mode changes."""
    def __init__(self, directory):
        self.directory=Path(directory)
    @contextlib.contextmanager
    def connect(self):
        db=sqlite3.connect((self.directory/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=10)
        db.row_factory=sqlite3.Row
        try: yield db
        finally: db.close()
    def setting(self,key,default=None):
        with self.connect() as db: row=db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default


class Library:
    def __init__(self, config, gateway=None):
        self.config=config; self.refs={}; self.photo_kinds={}; self.gateway_factory=gateway

    def gateway(self):
        if self.gateway_factory: return self.gateway_factory()
        from freeqnap import accounts
        from freeqnap.nas.broker import Client
        from freeqnap.personal_access import Gateway
        state=ReadState(self.config.get('state','/var/lib/freeqnap'))
        def session():
            with state.connect() as db:
                row=db.execute('SELECT * FROM local_accounts WHERE id=?',(self.config['owner'],)).fetchone()
            if not row or not row['enabled'] or row['must_change']: raise PermissionError('NAS account disabled or password change required')
            return {'user':accounts.public(row)}
        session()
        return Gateway(Client(timeout=25),state,session)

    def enabled(self, category):
        if category not in CATEGORIES or category not in self.config.get('categories', sorted(CATEGORIES)):
            raise PermissionError('This library is not enabled for this connector')

    def check(self):
        """Local readiness only: no enrollment, media bytes, scan or network request."""
        result={}
        for category in self.config.get('categories', sorted(CATEGORIES)):
            try:
                value=self.handle('catalog',{'category':category})
                result[category]={'available':True,'total':value['total']}
            except Exception:
                result[category]={'available':False,'message':'Check local account permission and library storage.'}
        return {'libraries':result,'read_only':True,'cloud_contacted':False}

    def reference(self, share, path):
        ident=hashlib.sha256((share+'\0'+path).encode()).hexdigest()
        if len(self.refs)>=20000: self.refs.clear()
        self.refs[ident]=(share,path)
        return ident

    def handle(self, action, p):
        if not isinstance(p,dict): raise ValueError('Object required')
        gw=self.gateway()  # re-read enabled state and rights on every request/chunk
        if action=='catalog':
            if set(p)-{'category','query','offset','folder'}: raise ValueError('Unsupported catalog field')
            category=p.get('category','music'); query=p.get('query',''); offset=integer(p.get('offset',0),0,1000000)
            self.enabled(category)
            if not isinstance(query,str) or len(query)>200: raise ValueError('Invalid search')
            if category=='folders':
                folder=p.get('folder')
                if not folder:
                    items=[]
                    for share in self.config.get('shares',[]):
                        # Do not advertise stale or no-longer-authorized local roots.
                        try: gw.request('files.list',{'share':share,'path':'','offset':0,'limit':1})
                        except Exception: continue
                        items.append({'id':self.reference(share,''),'title':share,'kind':'folder'})
                    return {'items':items,'total':len(items),'offset':0}
                if folder not in self.refs: raise ValueError('Browse this folder again')
                share,path=self.refs[folder]
                value=gw.request('files.list',{'share':share,'path':path,'offset':offset,'limit':60,'query':query})
                items=[]
                for row in value.get('entries',[]):
                    name=row['name']
                    if row.get('symlink'): continue
                    kind=row.get('kind',row.get('type',''))
                    directory=kind in ('directory','dir') or row.get('is_dir') is True or row.get('directory') is True
                    if not directory and Path(name).suffix.lower() not in MEDIA_EXT: continue
                    child=(path.rstrip('/')+'/' if path else '')+name
                    items.append({'id':self.reference(share,child),'title':name,'kind':'folder' if directory else 'file'})
                total=value.get('total_entries',len(items))
                return {'items':items,'total':total,'offset':offset,'next_offset':offset+len(value.get('entries',[])) if offset+len(value.get('entries',[]))<total else None}
            photo=category in ('photos','videos')
            value=gw.request('photos.catalog' if photo else 'myradio.catalog',
                {'limit':60,'offset':offset,**({'q':query,'kind':'video' if category=='videos' else 'photo'} if photo else {'query':query,'category':category})})
            items=[]
            for row in value.get('items',[]):
                meta=row.get('metadata') or {}
                items.append({'id':row['id'],'filename':str(row.get('name',''))[:500],'title':str(meta.get('title') or row.get('name','Media'))[:500],
                    'artist':str(meta.get('artist') or meta.get('author') or '')[:500],
                    'album':str(meta.get('album') or '')[:500], 'kind':category,
                    'has_artwork':photo or bool(meta.get('has_cover')),
                    **{key:(meta[key][:500] if isinstance(meta[key],str) else meta[key]) for key in ('author','narrator','genre','year','series','track','disc','duration') if key in meta and (isinstance(meta[key],str) or type(meta[key]) in (int,float) and math.isfinite(meta[key]))}})
            total=value.get('total',len(items))
            return {'items':items,'total':total,'offset':offset,'next_offset':offset+len(items) if offset+len(items)<total else None}
        if action in ('read','book'):
            allowed={'id','category','offset','count','variant'} if action=='read' else {'id','offset'}
            if set(p)-allowed: raise ValueError('Unsupported read field')
            ident=p.get('id','')
            if not isinstance(ident,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ident): raise ValueError('Invalid item')
            offset=integer(p.get('offset',0),0,2**50)
            if action=='book':
                self.enabled('books')
                return gw.request('myradio.book-text',{'id':ident,'offset':offset,'count':12000})
            count=integer(p.get('count',262144),1,262144); category=p.get('category')
            self.enabled(category)
            variant=p.get('variant','original')
            if variant not in ('original','cover','preview','thumb'): raise ValueError('Invalid variant')
            if category=='folders':
                if variant!='original': raise ValueError('Folders expose original media only')
                if ident not in self.refs: raise ValueError('Browse this media folder again')
                share,path=self.refs[ident]
                if Path(path).suffix.lower() not in MEDIA_EXT: raise ValueError('Only media files may be read')
                value=gw.request('files.read',{'share':share,'path':path,'offset':offset,'count':count})
                value={**value,'filename':Path(path).name}
            else:
                if category in ('photos','videos'):
                    if variant=='cover': raise ValueError('Choose a photo thumbnail or preview')
                    variant='thumbnail' if variant=='thumb' else variant
                    # Keep a photos-only pairing from accepting a known video ID.
                    # Asset kind is immutable; cache only that fact, never permission or bytes.
                    if self.photo_kinds.get(ident)!=category:
                        row=gw.request('photos.catalog',{'id':ident,'kind':'video' if category=='videos' else 'photo','limit':1})
                        if not row.get('items'): raise PermissionError('Item is outside this library')
                        if len(self.photo_kinds)>=20000: self.photo_kinds.clear()
                        self.photo_kinds[ident]=category
                else:
                    if variant not in ('original','cover'): raise ValueError('Choose media or cover')
                    row=gw.request('myradio.item',{'id':ident})['item']
                    if row.get('category')!=category or row.get('hidden'): raise PermissionError('Item is outside this library')
                value=gw.request('photos.read' if category in ('photos','videos') else 'myradio.read',{'id':ident,'variant':variant,'offset':offset,'count':count})
            return {k:value[k] for k in ('filename','total_bytes','etag','data_base64')}
        raise ValueError('Read-only media operation required')

def save(path, config):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name(path.name+'.'+secrets.token_hex(4))
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f: json.dump(config,f); f.flush(); os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)

def validate(config):
    if not isinstance(config,dict): raise ValueError('Invalid connector configuration')
    parsed=urlsplit(config.get('origin',''))
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:
        raise ValueError('EyeQ origin must be an HTTPS origin without a path or credentials')
    if not re.fullmatch('[a-f0-9]{32}',config.get('owner','')): raise ValueError('Select a local NAS account')
    categories=config.get('categories',sorted(CATEGORIES))
    if not isinstance(categories,list) or not categories or any(v not in CATEGORIES for v in categories): raise ValueError('Choose media libraries')
    shares=config.get('shares',[])
    if not isinstance(shares,list) or len(shares)>32 or any(not isinstance(v,str) or not re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9._:-]{0,99}',v) for v in shares): raise ValueError('Choose local share names')
    return config

def load(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode&0o077 or path.stat().st_size>16384:
        raise ValueError('Connector configuration must be a regular private file (mode 600)')
    return validate(json.loads(path.read_text()))

def status(path, state):
    save(path.with_name(path.stem+'.status.json'),{'state':state,'updated':time.time()})

async def run(config, path):
    from websockets.asyncio.client import connect
    validate(config)
    lib=Library(config)
    uri=config['origin'].rstrip('/').replace('https://','wss://',1)+'/api/aurastore/bridge'
    delay=2
    while True:
        try:
            status(path,'connecting')
            async with connect(uri,max_size=32768,ping_interval=20,open_timeout=15) as ws:
                await ws.send(json.dumps({'id':config['id'],'token':config['token']}))
                async def heartbeat():
                    while True:
                        await asyncio.sleep(20); await ws.send('{"type":"ping"}')
                task=asyncio.create_task(heartbeat()); delay=2
                try:
                    async for raw in ws:
                        req=json.loads(raw)
                        if req.get('type')=='pong':
                            status(path,'online'); continue
                        try:
                            result=await asyncio.to_thread(lib.handle,req['action'],req.get('payload',{}))
                            reply={'id':req['id'],'ok':True,'result':result}
                        except Exception:
                            reply={'id':req.get('id'),'ok':False}  # no paths, credentials or private errors upstream
                        await ws.send(json.dumps(reply))
                finally:
                    task.cancel()
                    try: await task
                    except asyncio.CancelledError: pass
        except Exception:
            status(path,'reconnecting')
            print('AuraStore connection unavailable; retrying.',file=sys.stderr)
            await asyncio.sleep(delay); delay=min(60,delay*2)

def main():
    p=argparse.ArgumentParser(description='AuraView EyeQ Connector App')
    p.add_argument('--config',default='/var/lib/auraview-eyeq-connector/account.json')
    p.add_argument('--pair',action='store_true'); p.add_argument('--owner',help='Local NAS account ID')
    p.add_argument('--name',default='AuraStore'); p.add_argument('--share',action='append',default=[])
    p.add_argument('--category',action='append',choices=sorted(CATEGORIES),help='Limit paired libraries (repeatable)')
    p.add_argument('--origin',default='https://eyeq.auraviewsystems.com')
    p.add_argument('--check',action='store_true',help='Check local library readiness without contacting EyeQ')
    p.add_argument('--status',action='store_true',help='Show safe transport state without credentials')
    args=p.parse_args(); path=Path(args.config)
    if args.owner:
        # Accept a local username for people; persist only its immutable account ID.
        with ReadState('/var/lib/freeqnap').connect() as db:
            row=db.execute('SELECT id FROM local_accounts WHERE id=? OR username=?',(args.owner,args.owner)).fetchone()
        if not row: raise SystemExit('Local NAS account not found')
        args.owner=row['id']
    if args.check and args.owner:
        config=validate({'origin':args.origin.rstrip('/'),'owner':args.owner,'shares':args.share,'categories':args.category or sorted(CATEGORIES)})
        print(json.dumps(Library(config).check(),indent=2)); return
    if args.pair:
        if path.exists(): raise SystemExit('Already paired. Revoke the old connector in EyeQ and remove its configuration before pairing again.')
        if not args.owner or not re.fullmatch('[a-f0-9]{32}',args.owner): raise SystemExit('Select the local NAS account with --owner')
        config=validate({'origin':args.origin.rstrip('/'),'owner':args.owner,'shares':args.share,'categories':args.category or sorted(CATEGORIES)})
        Library(config).gateway()  # verify account before consuming the code
        code=getpass.getpass('EyeQ pairing code (hidden): ')
        req=Request(config['origin']+'/api/aurastore/enroll',data=json.dumps({'code':code,'name':args.name}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=20) as response: enrolled=json.loads(response.read(16385))
        if not re.fullmatch('[a-f0-9]{24}',enrolled.get('id','')) or not isinstance(enrolled.get('token'),str) or not 32<=len(enrolled['token'])<=128:
            raise ValueError('Invalid EyeQ enrollment response; revoke the incomplete pairing in EyeQ')
        config.update({key:enrolled[key] for key in ('id','token')})
        save(path,config); print('AuraStore paired. Start the connector service.'); return
    config=load(path)
    if args.check: print(json.dumps(Library(config).check(),indent=2)); return
    if args.status:
        status_path=path.with_name(path.stem+'.status.json')
        value=json.loads(status_path.read_text()) if status_path.exists() else {'state':'not-started'}
        if time.time()-value.get('updated',0)>90 and value['state']!='not-started': value['state']='stale'
        print(json.dumps(value)); return
    if not isinstance(config.get('id'),str) or not isinstance(config.get('token'),str): raise SystemExit('Pair the connector first')
    asyncio.run(run(config,path))

if __name__=='__main__': main()
