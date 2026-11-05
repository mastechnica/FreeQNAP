"""Personal My Radio landing page; recent plays never masquerade as past statistics."""
from . import radio_catalog,radio_listening,library_cards
from .podcast_browser import Browser

def overview(g):
 result=radio_listening.overview(g);status=g._request('myradio.status',{});recent=result['recent'];sections=[];counts={**status.get('counts',{})}
 music=[];books=[]
 if status.get('config',{}).get('location_selected'):
  music=radio_catalog.music(g,{'limit':25,'sort':'newest'})['items'][:6];books=radio_catalog.inventory(g,'books')
 fallback={'music':[{'kind':'album','album':v,'id':v['id'],'title':v['title']} for v in music],
  'audiobooks':[{'kind':'audiobooks','id':v['id'],'item':v,'title':v['metadata'].get('title',v['name']),'shared':''} for v in books if v['metadata'].get('book_type')=='audiobook' or v['metadata'].get('playable')=='audio'][:6],
  'books':[{'kind':'books','id':v['id'],'item':v,'title':v['metadata'].get('title',v['name']),'shared':''} for v in books if v['metadata'].get('book_type')!='audiobook' and v['metadata'].get('playable')!='audio'][:6]}
 feeds=g._request('myradio.podcasts',{})['feeds'];fallback['podcasts']=[]
 for v in feeds[:6]:
  v=library_cards.overlay(g,'podcast',v);p=Browser(g).profile(v);show={'id':v['id'],'title':v['title'],'has_artwork':p['can_art'] or v['metadata'].get('custom_artwork'),'custom_artwork':v['metadata'].get('custom_artwork'),'card_revision':v['metadata'].get('card_revision','')};fallback['podcasts'].append({'kind':'show','id':v['id'],'title':v['title'],'show':show})
 stations=g.request('myradio.stations',{})['items'];fallback['radio']=[{'kind':'radio','id':v['id'],'title':v['name'],'item':{**v,'station':True},'shared':''} for v in stations[:6]]
 for kind,label in [('music','Music'),('audiobooks','Audiobooks'),('podcasts','Podcasts'),('radio','Internet Radio'),('books','Books & reading')]:sections.append({'kind':kind,'title':label,'mode':'recent' if recent[kind] else 'explore','items':recent[kind] or fallback[kind]})
 counts.update(audiobooks=sum(v['metadata'].get('book_type')=='audiobook' or v['metadata'].get('playable')=='audio' for v in books),ebooks=sum(v['metadata'].get('book_type')!='audiobook' and v['metadata'].get('playable')!='audio' for v in books),shows=len(feeds),radio=len(stations))
 return {**result,'sections':sections,'counts':counts}
