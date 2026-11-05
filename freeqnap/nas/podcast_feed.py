"""Read an oversized public RSS/Atom feed as a bounded recent-episode snapshot."""
from xml.etree import ElementTree as ET
from . import public_http
MAX_INPUT=16*1024**2
MAX_OUTPUT=2*1024**2

def local(tag):return tag.split('}')[-1]
def text(node,key,limit):
    return next((''.join(v.itertext()).strip()[:limit] for v in node if local(v.tag)==key),'')
def snapshot(response,max_input=MAX_INPUT,max_items=300):
    parser=ET.XMLPullParser(events=('start','end'));out=ET.Element('rss',version='2.0');channel=ET.SubElement(out,'channel');stack=[];count=total=0;tail=b'';finished=False;seen_root=False
    while not finished:
        chunk=response.read(min(65536,max_input-total+1))
        if not chunk:break
        total+=len(chunk)
        if total>max_input:raise ValueError('Podcast inventory exceeds the bounded reader limit')
        check=(tail+chunk).replace(b'\x00',b'').upper()
        if b'<!DOCTYPE' in check or b'<!ENTITY' in check:raise ValueError('Podcast feed contains an unsafe XML declaration')
        tail=chunk[-64:]
        try:parser.feed(chunk)
        except ET.ParseError:raise ValueError('Invalid podcast XML') from None
        try:events=list(parser.read_events())
        except ET.ParseError:raise ValueError('Invalid podcast XML') from None
        for event,node in events:
            tag=local(node.tag)
            if event=='start':
                if not seen_root:
                    if tag not in ('rss','feed'):raise ValueError('Choose an RSS or Atom podcast feed')
                    seen_root=True
                stack.append(node)
                if len(stack)>64:raise ValueError('Podcast XML nesting limit exceeded')
                continue
            parent=stack[-2] if len(stack)>1 else None
            if tag in ('item','entry'):
                item=ET.SubElement(channel,'item')
                for key,limit in [('title',500),('description',2000),('pubDate',200),('guid',2000),('author',500),('duration',80)]:
                    value=text(node,key,limit)
                    if not value and key=='description':value=text(node,'summary',2000)
                    if not value and key=='guid':value=text(node,'id',2000)
                    if not value and key=='pubDate':value=text(node,'published',200)
                    if value:ET.SubElement(item,key).text=value
                enclosure=next((v for v in node if local(v.tag)=='enclosure' or local(v.tag)=='link' and v.get('rel')=='enclosure'),None)
                if enclosure is not None:
                    url=enclosure.get('url') or enclosure.get('href') or ''
                    if len(url)<=8192:ET.SubElement(item,'enclosure',url=url,type=(enclosure.get('type') or 'audio/mpeg')[:100])
                if parent is not None:parent.remove(node)
                node.clear();count+=1
                if count>=max_items:finished=True;break
            elif parent is not None and local(parent.tag) in ('channel','feed') and tag in ('title','description','subtitle','author'):
                key='description' if tag=='subtitle' else tag
                if channel.find(key) is None:ET.SubElement(channel,key).text=''.join(node.itertext()).strip()[:4000]
            stack.pop()
    if not finished:
        try:parser.close()
        except ET.ParseError:raise ValueError('Invalid podcast XML') from None
    if not count:raise ValueError('No podcast episodes found')
    while True:
        raw=ET.tostring(out,encoding='utf-8',xml_declaration=True)
        if len(raw)<=MAX_OUTPUT:return raw
        items=channel.findall('item')
        if len(items)<2:raise ValueError('Podcast metadata exceeds the bounded reader limit')
        channel.remove(items[-1])

def fetch(url):
    with public_http.open_url(url) as (response,_):return snapshot(response)
