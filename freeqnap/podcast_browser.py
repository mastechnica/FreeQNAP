"""Session-scoped podcast browsing over the existing authorized personal API."""
import collections,concurrent.futures,hashlib,html,json,os,re,threading,time
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET
from . import library_shares
from .nas import public_http
_CACHE=collections.OrderedDict();_LOCK=threading.RLock();_BUILD=threading.Lock();_ART=threading.BoundedSemaphore(2)
ID=re.compile('[a-f0-9]{32}\\Z')

def epoch(value):
    if not isinstance(value,str):return None
    try:
        try:d=parsedate_to_datetime(value)
        except (ValueError,TypeError):d=datetime.fromisoformat(value.replace('Z','+00:00'))
        return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError,TypeError,OverflowError):return None

def duration(value):
    try:
        parts=str(value).split(':');total=0
        if len(parts)>3:return 0
        for p in parts:total=total*60+float(p)
        return max(0,min(total,604800))
    except (ValueError,TypeError):return 0

def plain(value,n=600):return html.unescape(re.sub('<[^>]*>',' ',str(value or '')))[:n].strip()
def scope(g):
    session=g.session()
    if not session or session['user'].get('must_change'):raise PermissionError('Sign in again')
    user=session['user'];owner=g.managed or user['id'];shared=g.share or ''
    if shared:owner=library_shares.resolve(g.state,user,shared)['owner']
    return owner,hashlib.sha256((owner+'\0'+user['id']+'\0'+shared).encode()).hexdigest()

def header(url):
    """Read channel artwork/categories only; never fetch an episode enclosure."""
    data={};genres=[];parser=ET.XMLPullParser(events=('start','end'));stack=[];size=0;tail=b''
    with public_http.open_url(url) as (response,_):
        while size<512*1024:
            chunk=response.read(min(32768,512*1024-size))
            if not chunk:break
            size+=len(chunk);check=(tail+chunk).replace(b'\0',b'').upper();tail=chunk[-64:]
            if b'<!DOCTYPE' in check or b'<!ENTITY' in check:raise ValueError('Unsafe podcast XML')
            parser.feed(chunk)
            for event,node in parser.read_events():
                tag=node.tag.split('}')[-1]
                if event=='start':
                    if tag in ('item','entry'):data['genres']=list(dict.fromkeys(genres))[:16];return data
                    stack.append(tag)
                    if len(stack)>64:raise ValueError('Podcast XML nesting limit')
                    if tag=='image' and node.get('href'):data['artwork']=node.get('href')
                    if tag=='category' and node.get('text'):genres.append(node.get('text')[:80])
                else:
                    value=''.join(node.itertext()).strip()
                    if tag in ('title','description','author') and len(stack)>1 and stack[-2] in ('channel','feed'):data[tag]=plain(value,10000 if tag=='description' else 500)
                    if tag=='url' and len(stack)>1 and stack[-2]=='image':data.setdefault('artwork',value)
                    if tag=='link' and len(stack)>1 and stack[-2] in ('channel','feed') and value.startswith(('https://','http://')):data['website']=value[:8192]
                    stack.pop()
    data['genres']=list(dict.fromkeys(genres))[:16];return data

def starter():
    rows=json.loads((Path(__file__).resolve().parents[1]/'docs/technology-podcast-starter.json').read_text())['feeds']
    return {hashlib.sha256(r['url'].encode()).hexdigest()[:32]:r for r in rows}

class Browser:
    def __init__(self,g):self.g=g;self.owner,self.scope=scope(g)
    def authorize(self,feed=None):
        data=self.g._request('myradio.podcasts',{'feed':feed} if feed else {})
        if feed and not any(r['id']==feed for r in data['feeds']):raise PermissionError('Podcast show is unavailable')
        return data
    def profile(self,feed,warm=False):
        key='podcast-profile:'+self.owner+':'+feed['id'];saved=self.g.state.setting(key,{})
        known=starter().get(feed['id']) or ({'url':saved['feed_url'],'source':'','category':'Uncategorized'} if saved.get('feed_url') else None);meta=feed.get('metadata',{})
        if warm and known and (not saved.get('checked') or time.time()-saved['checked']>7*86400):
            try:
                info=header(known['url']);saved={**saved,**info,'checked':time.time()};self.g.state.set(key,saved)
            except (ValueError,OSError,ET.ParseError):pass
        genres=list(dict.fromkeys(([known['category']] if known and known['category']!='Uncategorized' else [])+saved.get('genres',[])+meta.get('genres',[]))) or ['Uncategorized']
        website=meta['website'] if 'website' in meta else saved.get('website') or (known or {}).get('source') or ''
        if website:
            try:public_http.target(website)
            except ValueError:website=''
        return {**saved,'genres':genres[:16],'website':website,'artwork':saved.get('artwork') or meta.get('artwork'),'can_art':bool(saved.get('artwork') or meta.get('artwork') or known)}
    def remember(self,ident,url):
        self.authorize(ident);public_http.target(url)
        key='podcast-profile:'+self.owner+':'+ident;saved=self.g.state.setting(key,{})
        self.g.state.set(key,{**saved,'feed_url':url})
    def warm(self):
        data=self.authorize()
        for feed in data['feeds']:self.profile(feed,True)
        return len(data['feeds'])
    def inventory(self,refresh=False):
        authorized=self.authorize();from .library_cards import overlay
        feeds=[overlay(self.g,'podcast',v) for v in authorized['feeds']];signature=tuple((r['id'],r.get('checked_at')) for r in feeds)
        with _LOCK:cached=_CACHE.get(self.scope)
        if not refresh and cached and cached['signature']==signature and time.time()-cached['at']<60:return feeds,cached['episodes'],cached['windows']
        with _BUILD:
            episodes=[];windows=set()
            def read(feed):
                result=self.g._request('myradio.podcasts',{'feed':feed['id'],'limit':500,'offset':0});rows=list(result['episodes']);seen={v['id'] for v in rows};offset=0
                while result.get('pagination') and result.get('next_offset') is not None:
                    next_offset=result['next_offset']
                    if not isinstance(next_offset,int) or next_offset<=offset:raise ValueError('Podcast listing did not advance')
                    offset=next_offset;page=self.g._request('myradio.podcasts',{'feed':feed['id'],'limit':500,'offset':offset})
                    if any(v['id'] in seen for v in page['episodes']):raise ValueError('Podcast catalog changed. Refresh the library.')
                    rows+=page['episodes'];seen.update(v['id'] for v in page['episodes']);result={**page}
                    if len(rows)>20000:raise ValueError('Podcast catalog limit reached')
                return feed,{**result,'episodes':rows}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                for feed,result in pool.map(read,feeds):
                    rows=result['episodes'];episodes.extend(rows)
                    if not result.get('pagination') and len(rows)>=300:windows.add(feed['id'])
                    if len(episodes)>20000:raise ValueError('Podcast browser catalog limit reached. Choose a smaller collection.')
            with _LOCK:
                _CACHE[self.scope]={'at':time.time(),'signature':signature,'episodes':episodes,'windows':windows};_CACHE.move_to_end(self.scope)
                while len(_CACHE)>2:_CACHE.popitem(last=False)
            return feeds,episodes,windows
    def listing(self,r):
        if set(r)-{'view','feed','query','genre','publisher','age','saved','sort','offset','limit','refresh'}:raise ValueError('Unknown podcast filter')
        view=r.get('view','shows');limit=r.get('limit',25);offset=r.get('offset',0)
        if view not in ('shows','episodes') or limit not in (25,50,100,500,'all') or type(offset)is not int or offset<0:raise ValueError('Choose a podcast view and page size')
        query=str(r.get('query','')).casefold();genre=str(r.get('genre',''));publisher=str(r.get('publisher',''));age=str(r.get('age',''));saved=r.get('saved','');sort=r.get('sort','newest')
        if len(query)>255 or age not in ('','7','30','90','365','older','undated') or saved not in ('','yes','no') or sort not in ('newest','oldest','title','publisher','episodes','duration'):raise ValueError('Invalid podcast filters')
        if type(r.get('refresh',False)) is not bool:raise ValueError('Invalid refresh option')
        feeds,episodes,windows=self.inventory(r.get('refresh',False));by_feed={f['id']:[] for f in feeds}
        for row in episodes:
            if row['feed'] in by_feed:by_feed[row['feed']].append(row)
        all_genres=set();all_publishers=set();cards=[];all_cards=[];now=time.time()
        def age_ok(date):
            if not age:return True
            if age=='undated':return date is None
            if date is None:return False
            days=max(0,(now-date)/86400)
            return days>365 if age=='older' else days<=int(age)
        def normalized(row):
            m=row['metadata'];stamp=epoch(m.get('published'));return {'id':row['id'],'feed':row['feed'],'title':row['title'],'description':plain(m.get('description')),'published':m.get('published'),'published_at':stamp,'duration_seconds':duration(m.get('duration')),'asset':row.get('asset')}
        for feed in feeds:
            p=self.profile(feed);m=feed['metadata'];author=plain(m.get('author'),500);p['genres']=m.get('genres') or p['genres'];all_genres.update(p['genres']);all_publishers.add(author)
            rows=[normalized(v) for v in by_feed[feed['id']]];dates=[v['published_at'] for v in rows if v['published_at'] is not None];latest=max(dates) if dates else None
            matching=[v for v in rows if age_ok(v['published_at']) and (not saved or bool(v['asset'])==(saved=='yes')) and (not query or query in (' '.join((v['title'],v['description'],feed['title'],author,plain(m.get('description'))))).casefold())]
            all_cards.append({'id':feed['id'],'title':feed['title'],'publisher':author,'description':plain(m.get('description'),10000),'genres':p['genres'],'website':p['website'],'has_artwork':p['can_art'] or m.get('custom_artwork',False),'custom_artwork':m.get('custom_artwork',False),'card_revision':m.get('card_revision',''),'episode_count':len(rows),'matching_count':len(matching),'saved_count':sum(bool(v['asset']) for v in rows),'latest_at':latest,'recent_window':feed['id'] in windows,'rows':matching})
            if genre and genre not in p['genres'] or publisher and publisher!=author:continue
            if (query or age or saved) and not matching and not (query and not age and not saved and query in (' '.join((feed['title'],author,plain(m.get('description'))))).casefold()):continue
            cards.append(all_cards[-1])
        options={'genres':sorted(all_genres),'publishers':sorted(v for v in all_publishers if v)}
        selected=None
        if view=='episodes':
            selected=next((v for v in all_cards if v['id']==r.get('feed')),None)
            if not any(f['id']==r.get('feed') for f in feeds):raise PermissionError('Podcast show is unavailable')
            items=selected['rows'] if selected else []
            if sort in ('newest','oldest'):items=sorted(items,key=lambda v:(v['published_at'] is None,(-v['published_at'] if sort=='newest' else v['published_at']) if v['published_at'] is not None else 0,v['id']))
            elif sort=='duration':items=sorted(items,key=lambda v:(-v['duration_seconds'],v['title'].casefold()))
            else:items=sorted(items,key=lambda v:v['title'].casefold())
        else:
            items=cards
            if sort in ('newest','oldest'):items=sorted(items,key=lambda v:(v['latest_at'] is None,(-v['latest_at'] if sort=='newest' else v['latest_at']) if v['latest_at'] is not None else 0,v['title'].casefold()))
            elif sort=='episodes':items=sorted(items,key=lambda v:(-v['episode_count'],v['title'].casefold()))
            else:items=sorted(items,key=lambda v:(v['publisher'] if sort=='publisher' else v['title']).casefold())
        total=len(items);offset=min(offset,((total-1)//limit*limit if total else 0)) if limit!='all' else 0
        clean=lambda row:{k:v for k,v in row.items() if k!='rows'}
        return {'view':view,'items':[clean(v) for v in (items if limit=='all' else items[offset:offset+limit])],'total':total,'offset':offset,'limit':limit,'show':clean(selected) if selected else None,'options':options,'show_count':len(feeds),'indexed_episodes':len(episodes),'recent_window':bool(selected and selected['recent_window']),'unclassified_feeds':self.authorize().get('unclassified_feeds',[])}
    def artwork(self,ident):
        if not isinstance(ident,str) or not ID.fullmatch(ident):raise ValueError('Choose a podcast show')
        feed=next(v for v in self.authorize(ident)['feeds'] if v['id']==ident);profile=self.profile(feed,True);url=profile.get('artwork')
        if not url:raise ValueError('No publisher artwork available')
        key=hashlib.sha256((self.owner+'\0'+ident+'\0'+url).encode()).hexdigest();root=self.g.state.directory/'podcast-art';root.mkdir(mode=0o700,exist_ok=True);path=root/key
        if path.is_file() and not path.is_symlink() and time.time()-path.stat().st_mtime<7*86400:raw=path.read_bytes()
        else:
            if not _ART.acquire(False):raise ValueError('Artwork is busy; try again shortly')
            try:
                raw=public_http.fetch(url,4*1024**2)
                image_type(raw)
                temp=root/(key+'.'+str(time.time_ns())+'.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
                os.replace(temp,path)
                files=sorted((p for p in root.iterdir() if p.is_file() and not p.is_symlink()),key=lambda p:p.stat().st_mtime,reverse=True);size=0
                for index,old in enumerate(files):
                    size+=old.stat().st_size
                    if index>=256 or size>512*1024**2:old.unlink(missing_ok=True)
            finally:_ART.release()
        return raw,image_type(raw)

def image_type(raw):
    if raw.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if raw[:4]==b'RIFF' and raw[8:12]==b'WEBP':return 'image/webp'
    raise ValueError('Unsupported podcast artwork')
