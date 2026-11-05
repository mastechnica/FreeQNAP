"""Personal playback sessions and bounded wall-time accounting, never inferred history."""
import collections,copy,json,re,secrets,time
from . import activity,accounts
from .podcast_browser import scope
KINDS=('music','audiobooks','books','podcasts','radio')

def principal(g):
 session=g.session()
 if not session or session['user'].get('must_change'):raise PermissionError('Sign in again')
 if g.managed:raise PermissionError('Listening history belongs to the signed-in account')
 # Native authorization is repeated, including account disable/read revocation.
 view=copy.copy(g);view.managed=None;view.share=None;view._request('myradio.status',{})
 return session['user']['id']

def ensure(state):
 with state.connect() as db:db.executescript('CREATE TABLE IF NOT EXISTS radio_listening(id TEXT PRIMARY KEY,listener TEXT NOT NULL,target TEXT NOT NULL,kind TEXT NOT NULL,item TEXT NOT NULL,shared TEXT NOT NULL,started REAL NOT NULL,last REAL NOT NULL,seconds REAL NOT NULL DEFAULT 0,playing INTEGER NOT NULL DEFAULT 0,ended INTEGER NOT NULL DEFAULT 0); CREATE INDEX IF NOT EXISTS radio_listening_owner ON radio_listening(listener,last); CREATE INDEX IF NOT EXISTS radio_listening_kind ON radio_listening(listener,kind,last);')

def resolve(g,snapshot):
 view=copy.copy(g);view.managed=None;view.share=snapshot.get('shared') or None
 if snapshot['kind']=='radio':
  rows=view.request('myradio.stations',{})['items'];item=next((v for v in rows if v['id']==snapshot['id']),None)
  if not item:raise PermissionError('Station is unavailable')
  return {'id':item['id'],'kind':'radio','title':item['name'],'creator':item['metadata'].get('country',''),'genre':item['metadata'].get('tags',''),'item':{**item,'station':True},'shared':''}
 item=view.request('myradio.item',{'id':snapshot['id']})['item'];m=item['metadata'];kind='audiobooks' if item['category']=='books' and (m.get('book_type')=='audiobook' or m.get('playable')=='audio') else item['category']
 return {'id':item['id'],'kind':kind,'title':m.get('title') or item['name'],'creator':m.get('author') or m.get('artist') or m.get('series',''),'genre':m.get('genre',''),'item':item,'shared':view.share or ''}

def listen(g,r):
 if set(r)-{'event','id','kind','session','playing'}:raise ValueError('Unknown playback field')
 owner=principal(g);ensure(g.state);event=r.get('event');now=time.time()
 if event=='start':
  if r.get('kind') not in KINDS:raise ValueError('Choose a playback category')
  item=resolve(g,{'id':r.get('id'),'kind':r['kind'],'shared':g.share or ''});ident=secrets.token_hex(16)
  with g.state.connect() as db:
   if db.execute('SELECT count(*) FROM radio_listening WHERE listener=? AND started>?',(owner,now-60)).fetchone()[0]>=120:raise ValueError('Playback is changing too quickly; tracking will resume with a later play')
   db.execute('INSERT INTO radio_listening(id,listener,target,kind,item,shared,started,last) VALUES(?,?,?,?,?,?,?,?)',(ident,owner,item['id'],item['kind'],json.dumps({k:v for k,v in item.items() if k!='item'}),item['shared'],now,now))
  activity.record(g.state,'user:'+owner,'myradio.play.'+item['kind'],'started');return {'session':ident,'tracking_since':now}
 if event not in ('tick','stop') or not isinstance(r.get('session'),str) or not re.fullmatch('[a-f0-9]{32}',r['session']) or type(r.get('playing',False)) is not bool:raise ValueError('Invalid playback event')
 with g.state.connect() as db:row=db.execute('SELECT * FROM radio_listening WHERE id=? AND listener=?',(r['session'],owner)).fetchone()
 if not row:raise PermissionError('Playback session unavailable')
 if row['ended']:return {'saved':True,'seconds':row['seconds'],'ended':True}
 resolve(g,{**json.loads(row['item']),'shared':row['shared']})
 elapsed=min(60,max(0,now-row['last'])) if row['playing'] else 0
 with g.state.connect() as db:
  n=db.execute('UPDATE radio_listening SET last=?,seconds=seconds+?,playing=?,ended=? WHERE id=? AND listener=? AND last=?',(now,elapsed,int(r.get('playing',False) and event!='stop'),int(event=='stop'),row['id'],owner,row['last'])).rowcount
  if n!=1:raise ValueError('Playback update changed; a later heartbeat will reconcile it')
 if event=='stop':activity.record(g.state,'user:'+owner,'myradio.play.'+row['kind'],'succeeded')
 return {'saved':True,'seconds':row['seconds']+elapsed,'ended':event=='stop'}

def overview(g):
 owner=principal(g);ensure(g.state)
 with g.state.connect() as db:
  recent=[dict(v) for kind in KINDS for v in db.execute('SELECT * FROM radio_listening WHERE listener=? AND kind=? ORDER BY last DESC LIMIT 20',(owner,kind))]
  totals=db.execute('SELECT coalesce(sum(seconds),0),count(*),min(started) FROM radio_listening WHERE listener=?',(owner,)).fetchone()
  by_kind={v[0]:v[1] for v in db.execute('SELECT kind,sum(seconds) FROM radio_listening WHERE listener=? GROUP BY kind',(owner,))}
  leaders=[dict(v) for kind in ('music','radio') for v in db.execute('SELECT target,kind,item,shared,sum(seconds) AS seconds,count(*) AS plays,max(last) AS last FROM radio_listening WHERE listener=? AND kind=? GROUP BY target,kind,shared ORDER BY seconds DESC LIMIT 5',(owner,kind))]
  genre_rows=[(json.loads(v[0]).get('genre',''),v[1]) for v in db.execute('SELECT item,seconds FROM radio_listening WHERE listener=? AND seconds>0',(owner,))]
 resolved={}
 def checked(row):
  key=(row['target'],row['kind'],row['shared'])
  if key not in resolved:
   try:resolved[key]=resolve(g,{**json.loads(row['item']),'shared':row['shared']})
   except (ValueError,PermissionError,OSError):resolved[key]=None
  return resolved[key]
 groups={k:[] for k in KINDS}
 for row in recent:
  if len(groups[row['kind']])>=5:continue
  v=checked(row)
  if v:groups[row['kind']].append({**v,'last':row['last'],'seconds':row['seconds'],'session_id':row['id']})
 top=[]
 for row in leaders:
  v=checked(row)
  if v:top.append({**v,'seconds':row['seconds'],'plays':row['plays']})
 genres=collections.Counter()
 for text,seconds in genre_rows:
  name=next((v.strip() for v in re.split('[,;|·]',text) if v.strip()),'Unspecified');genres[name]+=seconds
 denominator=sum(genres.values())
 return {'recent':groups,'stats':{'total_seconds':totals[0],'sessions':totals[1],'tracking_since':totals[2],'by_kind':by_kind,'genres':[{'name':k,'seconds':v,'percent':v/denominator*100 if denominator else 0} for k,v in genres.most_common(8)],'top_tracks':[v for v in top if v['kind']=='music'][:5],'top_stations':[v for v in top if v['kind']=='radio'][:5]},'measurement':'Browser-reported playback, bounded by server wall time; missed/offline heartbeats may undercount. Seeking does not add listening time. Earlier listening is not reconstructed.'}
