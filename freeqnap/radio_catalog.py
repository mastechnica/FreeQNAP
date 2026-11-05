"""Authorized, account-scoped album and book browsing over existing media APIs."""
import base64,collections,copy,hashlib,json,os,re,threading,time,unicodedata
from .state import atomic
from . import accounts
from .podcast_browser import scope,image_type
_CACHE=collections.OrderedDict();_LOCK=threading.RLock();_BUILD=[threading.Lock() for _ in range(32)];_EPOCH=collections.Counter()

def invalidate(owner,state=None):
 with _LOCK:
  _EPOCH[owner]+=1
  for key in list(_CACHE):
   if _CACHE[key]['owner']==owner:del _CACHE[key]
 if state:
  for path in (state.directory/'radio-index').glob('*.json'):
   try:
    with path.open() as f:
     if json.load(f).get('owner')==owner:path.unlink(missing_ok=True)
   except (OSError,ValueError):continue

def extra(g,item):
 if item['category']!='books':return item
 owner,_=scope(g);value=g.state.setting('book-organization:'+owner+':'+item['id'],{})
 return {**item,'metadata':{**item['metadata'],**value}}

def book_changes(value):
 if not isinstance(value,dict) or set(value)-{'series','series_number','collections'}:raise ValueError('Unknown book organization field')
 out={}
 for key in ('series','series_number'):
  if key in value:
   s=value[key]
   if not isinstance(s,str) or len(s)>(200 if key=='series' else 40) or any(ord(c)<32 for c in s):raise ValueError('Invalid book series')
   out[key]=s.strip()
 if 'collections' in value:
  rows=value['collections']
  if not isinstance(rows,list) or len(rows)>20 or any(not isinstance(v,str) or len(v)>160 or any(ord(c)<32 for c in v) for v in rows):raise ValueError('Choose up to twenty collection names')
  out['collections']=list(dict.fromkeys(v.strip() for v in rows if v.strip()))
 return out

def save_book(g,payload):
 owner,_=scope(g)
 if g.share:raise PermissionError('Shared books are read-only')
 changes=book_changes({k:v for k,v in payload.get('metadata',{}).items() if k in ('series','series_number','collections')})
 item=g._request('myradio.item',{'id':payload.get('id')})['item']
 if item['category']!='books':raise ValueError('Choose a book')
 core={**payload,'metadata':{k:v for k,v in payload.get('metadata',{}).items() if k not in changes}}
 result=g._request('myradio.metadata',core)
 saved=g.state.setting('book-organization:'+owner+':'+item['id'],{});g.state.set('book-organization:'+owner+':'+item['id'],{**saved,**changes});invalidate(owner,g.state)
 return {**result,'item':extra(g,result['item'])}

def inventory(g,kind,refresh=False,archived=False):
 # Recheck native authorization and count even before reading a private cache.
 owner,partition=scope(g);check=g._request('myradio.catalog',{'category':kind,'limit':1,'archived':archived});key=(partition,kind,archived);signature=check['total']
 path=g.state.directory/'radio-index'/(hashlib.sha256(repr(key).encode()).hexdigest()+'.json')
 with _LOCK:cached=_CACHE.get(key)
 if not cached:
  try:
   fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
   with os.fdopen(fd) as f:
    if os.fstat(f.fileno()).st_size>32*1024**2:raise ValueError('Oversized private index')
    value=json.load(f)
   if value.get('owner')==owner and value.get('partition')==partition and value.get('kind')==kind and value.get('archived')==archived and isinstance(value.get('items'),list) and len(value['items'])<=20000:cached=value
  except (OSError,ValueError,TypeError):pass
 def usable(value):return value and value['total']==signature and time.time()-value['at']<86400 and all(v.get('category')==kind for v in value['items'])
 def remember(value):
  with _LOCK:
   _CACHE[key]=value;_CACHE.move_to_end(key)
   while len(_CACHE)>6:_CACHE.popitem(last=False)
 def build():
  with _LOCK:epoch=_EPOCH[owner]
  rows=[];offset=0;seen=set()
  while offset<signature:
   page=g._request('myradio.catalog',{'category':kind,'sort':'title','limit':120,'offset':offset,'archived':archived})
   if not page['items'] or page['total']!=signature:raise ValueError('Library changed while loading. Refresh it.')
   for item in page['items']:
    if item.get('category')!=kind:raise PermissionError('This is outside the shared collection')
    if item['id'] in seen:raise ValueError('Library is changing. Refresh after the import finishes.')
    seen.add(item['id']);item={**item,'metadata':{k:v for k,v in item['metadata'].items() if not k.startswith('_')}};rows.append(item)
   offset+=len(page['items'])
   if offset>20000:raise ValueError('Choose a smaller library before browsing this collection')
  value={'owner':owner,'partition':partition,'kind':kind,'archived':archived,'at':time.time(),'total':signature,'items':rows}
  with _LOCK:
   if _EPOCH[owner]!=epoch:raise ValueError('Metadata changed while indexing. Refresh the collection.')
   remember(value);atomic(path,value)
  return value
 gate=_BUILD[hash(key)%len(_BUILD)]
 if not refresh and usable(cached):
  remember(cached)
  if time.time()-cached['at']>=600 and gate.acquire(blocking=False):
   def update():
    try:build()
    except (ValueError,PermissionError,OSError):pass # Last authorized cache remains; later calls retry.
    finally:gate.release()
   threading.Thread(target=update,daemon=True).start()
  return [extra(g,v) for v in copy.deepcopy(cached['items'])]
 with gate:
  with _LOCK:latest=_CACHE.get(key)
  if not refresh and usable(latest):return [extra(g,v) for v in copy.deepcopy(latest['items'])]
  value=build()
 return [extra(g,v) for v in copy.deepcopy(value['items'])]

def page(items,r):
 limit=r.get('limit',25);offset=r.get('offset',0)
 if limit not in (25,50,60,100,120,500,'all') or type(offset)is not int or offset<0:raise ValueError('Choose a page size')
 total=len(items);offset=0 if limit=='all' else min(offset,max(0,(total-1)//limit*limit))
 return {'items':items if limit=='all' else items[offset:offset+limit],'total':total,'offset':offset,'limit':limit}

def books(g,r):
 if set(r)-{'query','artist','genre','favorite','archived','offset','limit','sort','series','collection','format'}:raise ValueError('Unknown book filter')
 if any(k in r and type(r[k])is not bool for k in ('favorite','archived')):raise ValueError('Invalid book flag')
 if any(k in r and (not isinstance(r[k],str) or len(r[k])>500) for k in ('query','artist','genre','series','collection','sort','format')):raise ValueError('Invalid book filter')
 rows=inventory(g,'books',archived=bool(r.get('archived')));q=str(r.get('query','')).casefold()
 if len(q)>500 or r.get('format','') not in ('','audiobook','ebook'):raise ValueError('Invalid book filter')
 facets={key:sorted({v['metadata'].get(source,'') for v in rows if v['metadata'].get(source)}) for key,source in [('artist','author'),('genre','genre'),('series','series')]};facets['collections']=sorted({x for v in rows for x in v['metadata'].get('collections',[])})
 def match(v):
  m=v['metadata'];fmt='audiobook' if m.get('book_type')=='audiobook' or m.get('playable')=='audio' else 'ebook'
  return q in ' '.join((v['name'],str(m.get('title','')),str(m.get('author','')),str(m.get('genre','')),str(m.get('series','')),' '.join(m.get('collections',[])))).casefold() and all(not r.get(k) or r[k]==m.get(s) for k,s in [('artist','author'),('genre','genre'),('series','series')]) and (not r.get('collection') or r['collection'] in m.get('collections',[])) and (not r.get('format') or r['format']==fmt) and (not r.get('favorite') or v['favorite']) and bool(v.get('hidden'))==bool(r.get('archived'))
 rows=[v for v in rows if match(v)]
 def order(v):
  m=v['metadata'];sort=r.get('sort','title')
  if sort=='newest':return -v['created']
  if sort=='series':
   n=re.search(r'\d+(?:\.\d+)?',m.get('series_number',''));return (m.get('series','').casefold(),float(n[0]) if n else float('inf'),m.get('title',v['name']).casefold())
  return str(m.get({'artist':'author','album':'series','year':'year'}.get(sort,'title'),v['name'])).casefold()
 rows.sort(key=order);return {**page(rows,{**r,'limit':r.get('limit',60)}),'facets':facets}

def music_name(value):
 # Unicode accents and filename punctuation do not create separate albums.
 return ''.join(c for c in unicodedata.normalize('NFKD',str(value).casefold()) if c.isalnum() and not unicodedata.combining(c))

def music_slot(value,default=''):
 text=str(value or default).split('/')[0].strip();number=re.fullmatch(r'\d+',text);return str(int(text)) if number else text.casefold()

def album_signature(title,artist):return hashlib.sha256((music_name(title)+'\0'+music_name(artist)).encode()).hexdigest()

def track_order(v):
 m=v['metadata'];num=lambda s:int(re.search(r'\d+',str(s))[0]) if re.search(r'\d+',str(s)) else 99999
 return (num(m.get('disc',1)),num(m.get('track')),m.get('title',v['name']).casefold(),v['id'])

def albums(g,refresh=False):
 rows=inventory(g,'music',refresh);owner,_=scope(g);sources=g.state.setting('radio-source-groups:'+owner,{})
 performers=collections.defaultdict(set)
 for v in rows:
  m=v['metadata'];group=m.get('source_album_group') or sources.get(v['id'],{}).get('group','')
  if group and m.get('artist'):performers[(group,m.get('album','').casefold())].add(m['artist'].casefold())
 grouped={}
 for v in rows:
  m=v['metadata'];source=sources.get(v['id'],{});group=m.get('source_album_group') or source.get('group','');title=m.get('album') or 'Album not identified';artist=m.get('album_artist') or ('Various artists' if len(performers[(group,m.get('album','').casefold())])>1 else m.get('artist') or 'Artist not identified');year=m.get('year','')[:4]
  reviewed=source.get('album_key') if source.get('album_signature')==album_signature(title,m.get('album_artist') or artist) else None
  if reviewed:components=['reviewed',reviewed]
  elif m.get('album') and music_name(artist) not in ('variousartists','various','artistnotidentified','unknownartist','originalsoundtrack','soundtrack'):components=[music_name(title),music_name(artist)]
  else:components=[music_name(title),group or v['id']]
  ident=hashlib.sha256('\0'.join(components).encode()).hexdigest()[:32]
  a=grouped.setdefault(ident,{'id':ident,'title':title,'artist':artist,'year':year,'tracks':[],'genres':set(),'created':0,'folder':source.get('folder','')})
  a['tracks'].append(v);a['genres'].update(x.strip() for x in re.split('[,;|·]',m.get('genre','')) if x.strip());a['created']=max(a['created'],v['created'])
 out=[]
 for a in grouped.values():
  files=a['tracks'];seen={};visible=[]
  for item in files:
   proof=sources.get(item['id'],{});digest=proof.get('audio_hash')
   if digest and item['metadata'].get('audio_status')!='unavailable' and re.fullmatch('[a-f0-9]{64}',digest) and proof.get('audio_bytes')==item['bytes']:
    m=item['metadata'];identity=(digest,music_name(m.get('title','')),music_name(m.get('artist','')),music_slot(m.get('disc'),'1'),music_slot(m.get('track')))
    if identity in seen:
     seen[identity].setdefault('alternate_copies',[]).append(item);continue
    seen[identity]=item
   visible.append(item)
  a['file_count']=len(files);a['identical_copies']=len(files)-len(visible)
  playable=collections.defaultdict(list)
  def intended_track(v):
   m=v['metadata'];return (music_name(m.get('title','')),music_name(m.get('artist','')),music_slot(m.get('disc'),'1'),music_slot(m.get('track')))
  for item in visible:
   if item['metadata'].get('audio_status')!='unavailable':playable[intended_track(item)].append(item)
  kept=[];unavailable_copies=0
  for item in visible:
   key=intended_track(item);peers=playable[key]
   if item['metadata'].get('audio_status')=='unavailable' and key[0] and key[1] and key[3] and len(peers)==1:
    peers[0].setdefault('unavailable_copies',[]).append(item);unavailable_copies+=1
   else:kept.append(item)
  a['retained_unavailable_copies']=unavailable_copies
  # Group alternative files for the same intended album track. These are explicitly
  # versions, not claimed byte-identical; every original stays selectable.
  def preference(v):
   m=v['metadata'];return (m.get('audio_status')=='unavailable',m.get('playable')=='original-only',not v['name'].lower().endswith(('.flac','.wav','.aiff','.ape')), -v['bytes']/max(1,m.get('duration') or 1),v['id'])
  versions=collections.defaultdict(list);tracks=[];other_versions=0
  for item in sorted(kept,key=preference):
   key=intended_track(item);duration=item['metadata'].get('duration',0)
   candidates=versions[key] if key[0] and key[1] and key[3] and duration>0 and item['metadata'].get('audio_status')!='unavailable' else []
   primary=next((v for v in candidates if abs(v['metadata'].get('duration',0)-duration)<=3.5),None)
   if primary:primary.setdefault('other_versions',[]).append(item);other_versions+=1
   else:versions[key].append(item);tracks.append(item)
  a['other_versions']=other_versions;a['tracks']=tracks
  explicit=collections.Counter(v['metadata'].get('album_artist') for v in a['tracks'] if v['metadata'].get('album_artist'));performers=collections.Counter(v['metadata'].get('artist') for v in a['tracks'] if v['metadata'].get('artist'));years=collections.Counter(v['metadata'].get('year','')[:4] for v in a['tracks'] if v['metadata'].get('year'));a['artist']=explicit.most_common(1)[0][0] if explicit else performers.most_common(1)[0][0] if len(performers)==1 else 'Various artists' if performers else 'Artist not identified';a['year']=years.most_common(1)[0][0] if years else '';a['tracks'].sort(key=track_order);a['genres']=sorted(a['genres']);a['track_count']=len(a['tracks']);a['duration']=sum(v['metadata'].get('duration',0) for v in a['tracks']);a['unavailable_tracks']=sum(v['metadata'].get('audio_status')=='unavailable' for v in a['tracks']);a['needs_review']=sum(v['metadata'].get('identification_status')=='needs-review' for v in a['tracks']);cover_counts=collections.Counter(sources.get(v['id'],{}).get('cover_hash') for v in a['tracks'] if v['metadata'].get('has_cover') and sources.get(v['id'],{}).get('cover_hash'));best_cover=cover_counts.most_common(1)[0][0] if cover_counts else None;a['cover_item']=next((v for v in a['tracks'] if v['metadata'].get('has_cover') and (not best_cover or sources.get(v['id'],{}).get('cover_hash')==best_cover)),None);a['cover_key']=hashlib.sha256('\0'.join(sorted(v['id'] for v in files)).encode()).hexdigest()[:32];art=g.state.setting('radio-album-cover:'+owner+':'+a['cover_key'],{});a['custom_artwork']=bool(art);a['revision']=art.get('revision','');out.append(a)
 return out

def music(g,r):
 if set(r)-{'album','query','artist','genre','sort','offset','limit','refresh','attention'}:raise ValueError('Unknown album filter')
 if type(r.get('refresh',False))is not bool or any(k in r and (not isinstance(r[k],str) or len(r[k])>500) for k in ('album','query','artist','genre','sort','attention')):raise ValueError('Invalid album filter')
 if r.get('attention','') not in ('','identification','audio'):raise ValueError('Choose an album status')
 rows=albums(g,r.get('refresh',False));facets={'artist':sorted({v['artist'] for v in rows}),'genre':sorted({x for v in rows for x in v['genres']})}
 if r.get('album'):
  album=next((v for v in rows if v['id']==r['album']),None)
  if not album:raise PermissionError('Album is unavailable. Refresh your library.')
  return {'album':album,'facets':facets,'album_count':len(rows),'track_count':sum(v['track_count'] for v in rows),'file_count':sum(v['file_count'] for v in rows)}
 q=str(r.get('query','')).casefold()
 if len(q)>500:raise ValueError('Search text is too long')
 rows=[v for v in rows if q in (' '.join([v['title'],v['artist'],*v['genres']]+[t['metadata'].get('title',t['name']) for t in v['tracks']])).casefold() and (not r.get('artist') or v['artist']==r['artist']) and (not r.get('genre') or r['genre'] in v['genres']) and (not r.get('attention') or r['attention']=='identification' and v['needs_review'] or r['attention']=='audio' and v['unavailable_tracks'])]
 sort=r.get('sort','title')
 if sort not in ('title','artist','newest','year'):raise ValueError('Choose an album order')
 rows.sort(key=lambda v:-v['created'] if sort=='newest' else (v['year'] if sort=='year' else v[sort]).casefold(),reverse=sort=='year')
 clean=[{k:v for k,v in a.items() if k!='tracks'} for a in rows]
 return {**page(clean,r),'facets':facets,'album_count':len(rows),'track_count':sum(v['track_count'] for v in rows),'file_count':sum(v['file_count'] for v in rows)}

def album_save(g,r):
 if set(r)-{'album','metadata','artwork'}:raise ValueError('Unknown album edit')
 owner,_=scope(g)
 if g.share or not accounts.permitted(g.session()['user'],'myradio.write'):raise PermissionError('This album is read-only')
 a=music(g,{'album':r.get('album')})['album'];files=[];pending=list(a['tracks']);seen=set()
 while pending:
  item=pending.pop()
  if item['id'] in seen:continue
  seen.add(item['id']);files.append(item)
  for field in ('alternate_copies','unavailable_copies','other_versions'):pending.extend(item.get(field,[]))
 if len(files)>1000:raise ValueError('Edit a smaller album or individual tracks')
 changes=r.get('metadata',{})
 if not isinstance(changes,dict) or set(changes)-{'album','album_artist','genre','year'}:raise ValueError('Choose album fields')
 from .nas.myradio import clean,FIELDS
 for k,v in changes.items():clean(v,FIELDS[k])
 raw=None
 if 'artwork' in r and not isinstance(r['artwork'],str):raise ValueError('Invalid album cover')
 if r.get('artwork'):
  raw=base64.b64decode(r['artwork'],validate=True)
  if not 1<=len(raw)<=1024**2:raise ValueError('Choose artwork below 1 MB')
  mime=image_type(raw)
 updated=0
 try:
  for item in files:
   if changes:g.request('myradio.metadata',{'id':item['id'],'metadata':changes});updated+=1
  if raw:g.state.set('radio-album-cover:'+owner+':'+a['cover_key'],{'data':r['artwork'],'mime':mime,'revision':hashlib.sha256(raw).hexdigest()[:16]})
 except Exception as error:raise ValueError('Album changes were saved for '+str(updated)+' tracks before the operation stopped. Refresh and review before retrying.') from error
 finally:invalidate(owner,g.state)
 return {'updated':updated,'cover_saved':bool(raw)}

def album_art(g,ident):
 a=music(g,{'album':ident})['album'];owner,_=scope(g);value=g.state.setting('radio-album-cover:'+owner+':'+a['cover_key'],{})
 if not value:raise FileNotFoundError('No custom album cover')
 raw=base64.b64decode(value['data'],validate=True);return raw,image_type(raw)
