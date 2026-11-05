"""Explicit opt-in title matching. Results never change streams or subscriptions."""
import base64,hashlib,json,re,secrets,threading,time,urllib.parse
from . import accounts,library_cards,radio_catalog
from .podcast_browser import scope,plain,header,image_type
from .nas import public_http
_MB=threading.Lock();_LAST=0

def profile(g,write=False):
 owner,_=scope(g);cfg=g._request('myradio.status',{}).get('config') or {}
 if write and (g.share or not accounts.permitted(g.session()['user'],'myradio.write')):raise PermissionError('Metadata editing is not enabled')
 flags=g.state.setting('radio-providers:'+owner,{'podcasts':False,'radio':False})
 return owner,cfg,{'musicbrainz':bool(cfg.get('musicbrainz')),'openlibrary':bool(cfg.get('openlibrary')),'podcasts':bool(flags.get('podcasts')),'radio':bool(flags.get('radio'))}

def providers(g,r=None):
 return {'enabled':profile(g)[2],'disclosure':'Only explicit searches send the title/creator query to enabled providers. No audio, private files or playback history is sent. Podcast matches are limited to enrolled shows with a declared US/Canadian region; radio matches use the requested US/Canadian country.'}

def configure(g,r):
 owner,_,_=profile(g,True)
 if set(r)-{'podcasts','radio'} or any(type(v)is not bool for v in r.values()):raise ValueError('Choose provider settings')
 old=g.state.setting('radio-providers:'+owner,{'podcasts':False,'radio':False});g.state.set('radio-providers:'+owner,{**old,**r});return providers(g)

def target(g,kind,ident):
 if kind=='album':return radio_catalog.music(g,{'album':ident})['album']
 if kind in ('podcast','station'):
  library_cards.authorize(g,kind,ident);return {'id':ident}
 if kind=='asset':return g._request('myradio.item',{'id':ident})['item']
 raise ValueError('Choose a metadata editor')

def _mb(query):
 global _LAST
 with _MB:
  time.sleep(max(0,1.1-(time.monotonic()-_LAST)))
  try:return public_http.json_fetch('https://musicbrainz.org/ws/2/release/?'+urllib.parse.urlencode({'query':query,'fmt':'json','limit':8}))
  finally:_LAST=time.monotonic()

def search(g,r):
 if set(r)-{'kind','id','title','artist','country'}:raise ValueError('Unknown metadata search field')
 owner,cfg,enabled=profile(g,True);kind=r.get('kind');item=target(g,kind,r.get('id'));title=r.get('title','');artist=r.get('artist','');country=r.get('country','US')
 if not isinstance(title,str) or not title.strip() or len(title)>500 or not isinstance(artist,str) or len(artist)>500 or any(ord(c)<32 for c in title+artist) or country not in ('US','CA'):raise ValueError('Enter a title and choose US or Canada')
 with g.state.connect() as db:
  expired=[v[0] for v in db.execute("SELECT key FROM settings WHERE key LIKE 'radio-match:%' AND json_extract(value,'$.expires')<?",(time.time(),))]
  for k in expired:db.execute('DELETE FROM settings WHERE key IN (?,?)',(k,'radio-match-art:'+k.split(':')[1]))
  if db.execute("SELECT count(*) FROM settings WHERE key LIKE 'radio-match:%' AND json_extract(value,'$.owner')=?",(owner,)).fetchone()[0]>=256:raise ValueError('Earlier searches are still available. Wait for them to expire before starting more.')
 results=[];provider=''
 if kind=='asset':
  flag='openlibrary' if item['category']=='books' else 'musicbrainz'
  if not enabled[flag]:return {'results':[],'disabled':True,'message':'Enable '+('Open Library' if flag=='openlibrary' else 'MusicBrainz')+' title searches in Library settings first.'}
  native=g._request('myradio.lookup',{'id':r['id'],'title':title,'artist':artist});provider=native['provider'];results=native['results']
 elif kind=='album':
  if not enabled['musicbrainz']:return {'results':[],'disabled':True,'message':'Enable MusicBrainz in Library settings to search album titles.'}
  escape=lambda v:v.replace('\\','\\\\').replace('"','\\"');value=_mb('release:"'+escape(title)+'"'+(' AND artist:"'+escape(artist)+'"' if artist else ''));provider='MusicBrainz / Cover Art Archive'
  for v in value.get('releases',[])[:8]:
   ident=v.get('id','')
   if re.fullmatch('[a-f0-9-]{36}',ident):results.append({'title':str(v.get('title',''))[:500],'artist':''.join(x.get('name','')+x.get('joinphrase','') for x in v.get('artist-credit',[]) if isinstance(x,dict))[:500],'year':str(v.get('date',''))[:4],'source_url':'https://musicbrainz.org/release/'+ident,'cover_url':'https://coverartarchive.org/release/'+ident+'/front-250'})
 elif kind=='podcast':
  if not enabled['podcasts']:return {'results':[],'disabled':True,'message':'Enable the Apple Podcasts title directory in Library settings. Artwork is obtained from publisher RSS, not store promotional art.'}
  from .nas.myradio import origin
  eligible={v['id']:origin(v['metadata']) for v in g._request('myradio.podcasts',{})['feeds']}
  provider='Apple Podcasts title directory / publisher RSS';value=public_http.json_fetch('https://itunes.apple.com/search?'+urllib.parse.urlencode({'term':title+' '+artist,'media':'podcast','entity':'podcast','country':country,'limit':8}))
  for v in value.get('results',[])[:8]:
   feed=v.get('feedUrl','');site=v.get('collectionViewUrl','')
   if eligible.get(hashlib.sha256(feed.encode()).hexdigest()[:32])!=country:continue
   try:public_http.target(feed);public_http.target(site)
   except ValueError:continue
   results.append({'title':plain(v.get('collectionName'),500),'author':plain(v.get('artistName'),500),'genre':plain(v.get('primaryGenreName'),200),'website':site,'feed_lookup':feed})
 else:
  if not enabled['radio']:return {'results':[],'disabled':True,'message':'Enable Radio Browser metadata searches in Library settings.'}
  provider='Radio Browser';value=public_http.json_fetch('https://de1.api.radio-browser.info/json/stations/search?'+urllib.parse.urlencode({'name':title,'countrycode':country,'hidebroken':'true','limit':8,'order':'clickcount','reverse':'true'}))
  for v in value[:8]:
   if v.get('countrycode')!=country:continue
   results.append({'title':plain(v.get('name'),500),'genre':plain(v.get('tags'),200),'website':v.get('homepage',''),'cover_url':v.get('favicon') or None})
 out=[];now=time.time()
 for value in results:
  ticket=secrets.token_hex(16);key='radio-match:'+ticket;g.state.set(key,{'owner':owner,'requester':g.session()['user']['id'],'kind':kind,'id':r['id'],'result':value,'expires':now+600});out.append({'ticket':ticket,**{k:v for k,v in value.items() if k not in ('feed_lookup','cover_url')},'has_cover':bool(value.get('cover_url') or value.get('feed_lookup'))})
 return {'provider':provider,'results':out,'message':'Choose a match to apply. Streams and subscription URLs stay unchanged.'}

def match(g,ticket):
 if not isinstance(ticket,str) or not re.fullmatch('[a-f0-9]{32}',ticket):raise ValueError('Choose a search result')
 owner,_,enabled=profile(g,True);r=g.state.setting('radio-match:'+ticket,{})
 if r.get('owner')!=owner or r.get('requester')!=g.session()['user']['id'] or r.get('expires',0)<time.time():raise PermissionError('Search result expired or belongs to another account')
 item=target(g,r['kind'],r['id']);flag='openlibrary' if r['kind']=='asset' and item['category']=='books' else 'musicbrainz' if r['kind'] in ('asset','album') else 'podcasts' if r['kind']=='podcast' else 'radio'
 if not enabled[flag]:raise PermissionError('That metadata provider is disabled')
 return r

def cover(g,ticket):
 r=match(g,ticket);cached=g.state.setting('radio-match-art:'+ticket,{})
 if cached:
  raw=base64.b64decode(cached['data'],validate=True);return raw,image_type(raw)
 v=r['result'];url=v.get('cover_url')
 if v.get('feed_lookup'):url=header(v['feed_lookup']).get('artwork')
 if not url:raise FileNotFoundError('This result has no publisher cover')
 raw=public_http.fetch(url,1024**2);mime=image_type(raw);g.state.set('radio-match-art:'+ticket,{'data':base64.b64encode(raw).decode(),'mime':mime});return raw,mime

def apply(g,r):
 if set(r)-{'ticket','cover'} or type(r.get('cover',False)) is not bool:raise ValueError('Choose a matching result')
 matched=match(g,r.get('ticket'));kind=matched['kind'];v=dict(matched['result']);v.pop('cover_url',None);v.pop('feed_lookup',None);raw=None;warning=''
 if r.get('cover'):
  try:raw,_=cover(g,r['ticket'])
  except (ValueError,OSError):warning='Metadata can be applied, but that cover could not be loaded. You can upload artwork.'
 if kind=='asset':
  v.pop('website',None);g.request('myradio.metadata',{'id':matched['id'],'metadata':{k:x for k,x in v.items() if x is not None}})
  if raw:g.request('myradio.artwork',{'id':matched['id'],'data_base64':base64.b64encode(raw).decode()})
 elif kind=='album':
  values={k:v[a] for a,k in [('title','album'),('artist','album_artist'),('year','year'),('genre','genre')] if v.get(a)};g.request('myradio.album-save',{'album':matched['id'],'metadata':values,**({'artwork':base64.b64encode(raw).decode()} if raw else {})})
 else:
  v.pop('source_url',None);library_cards.save(g,{'kind':kind,'id':matched['id'],'metadata':{k:x for k,x in v.items() if k in library_cards.FIELDS and x is not None},**({'artwork':base64.b64encode(raw).decode()} if raw else {})})
 return {'saved':True,'warning':warning}
