"""Account-scoped display metadata; never edits stream/feed destinations."""
import base64,hashlib,re
from . import accounts
from .podcast_browser import scope,image_type
FIELDS={'title':500,'author':500,'genre':200,'description':10000,'website':2000}

def key(g,kind,ident):
 if kind not in ('podcast','station') or not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):raise ValueError('Choose a show or station')
 owner,_=scope(g)
 return 'library-card:'+owner+':'+kind+':'+ident

def authorize(g,kind,ident):
 rows=g._request('myradio.podcasts' if kind=='podcast' else 'myradio.stations',{})['feeds' if kind=='podcast' else 'items']
 if not any(v['id']==ident for v in rows):raise PermissionError('This item is not available in your library')

def overlay(g,kind,row):
 saved=g.state.setting(key(g,kind,row['id']),{});m=saved.get('metadata',{});out={**row,'metadata':{**row.get('metadata',{})}}
 if m.get('title'):out['title' if kind=='podcast' else 'name']=m['title']
 out['metadata'].update({('tags' if kind=='station' and k=='genre' else k):v for k,v in m.items() if k!='title'})
 if m.get('genre') and kind=='podcast':out['metadata']['genres']=[v.strip() for v in m['genre'].split(',') if v.strip()] or ['Uncategorized']
 out['metadata']['custom_artwork']=bool(saved.get('artwork'));out['metadata']['card_revision']=saved.get('revision','')
 return out

def save(g,r):
 if set(r)-{'kind','id','metadata','artwork','reset_artwork'}:raise ValueError('Unknown item field')
 if 'reset_artwork' in r and type(r['reset_artwork']) is not bool:raise ValueError('Choose whether to restore publisher artwork')
 kind=r.get('kind');ident=r.get('id');k=key(g,kind,ident);u=g.session()['user']
 if g.share or not accounts.permitted(u,'myradio.write'):raise PermissionError('Your library is read-only')
 if g.managed and u['role']!='administrator':raise PermissionError('Administrator access required')
 authorize(g,kind,ident);changes=r.get('metadata',{})
 if not isinstance(changes,dict) or set(changes)-FIELDS.keys():raise ValueError('Unknown metadata field')
 for name,value in changes.items():
  if not isinstance(value,str) or len(value)>FIELDS[name] or any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Invalid library text')
  if name=='title' and not value.strip():raise ValueError('Enter a title')
  if name=='website' and value:
   from .nas.public_http import target
   target(value)
 saved=g.state.setting(k,{});saved['metadata']={**saved.get('metadata',{}),**{k:v.strip() for k,v in changes.items()}}
 if 'artwork' in r:
  try:raw=base64.b64decode(r['artwork'],validate=True)
  except (ValueError,TypeError):raise ValueError('Invalid cover image') from None
  if not 1<=len(raw)<=1024**2:raise ValueError('Choose JPEG, PNG or WebP cover art below 1 MB')
  saved['mime']=image_type(raw);saved['artwork']=r['artwork']
 if r.get('reset_artwork') is True:saved.pop('artwork',None);saved.pop('mime',None)
 saved['revision']=hashlib.sha256(__import__('json').dumps(saved,sort_keys=True).encode()).hexdigest()[:16];g.state.set(k,saved)
 return {'saved':True,'revision':saved['revision']}

def artwork(g,kind,ident):
 k=key(g,kind,ident);authorize(g,kind,ident);saved=g.state.setting(k,{})
 if not saved.get('artwork'):raise FileNotFoundError('No custom artwork')
 raw=base64.b64decode(saved['artwork'],validate=True);return raw,image_type(raw)


def stations(g,result,request):
 from .nas.myradio import clean,region
 q=clean(request.get('query',''),200).casefold();group=clean(request.get('group',''),100).casefold();country=clean(request.get('country',''),100);country=region(country) if country else ''
 items=[overlay(g,'station',v) for v in result['items']]
 groups=sorted({tag.strip() for v in items for tag in v['metadata'].get('tags','').split(',') if tag.strip()})[:300]
 def match(v):
  m=v['metadata'];tags=[x.strip().casefold() for x in m.get('tags','').split(',')]
  return q in (v['name']+' '+m.get('tags','')+' '+m.get('country','')+' '+m.get('author','')+' '+m.get('description','')).casefold() and (not group or group in tags) and (not country or country==m.get('countrycode')) and (request.get('favorite') is not True or v['favorite'])
 return {**result,'groups':groups,'items':[v for v in items if match(v)]}
