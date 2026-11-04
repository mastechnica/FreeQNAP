import base64
import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.common import Context
from freeqnap.nas.myradio import MyRadio
from freeqnap.nas.radio_metadata import extract_book, plain, xml, zip_member
from freeqnap.nas.public_http import target

class Fixture(Context):
    def volume(self,ident):
        pool=self.config()['pools'][ident]
        if pool['filesystem_uuid']!='fixture-volume':raise ValueError('Volume identity changed')
        return pool,Path(pool['mountpoint'])

def rename(source_fd,source,target_fd,target):
    os.link(source,target,src_dir_fd=source_fd,dst_dir_fd=target_fd,follow_symlinks=False)
    os.unlink(source,dir_fd=source_fd)

class MyRadioTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.volume=self.root/'volume';self.volume.mkdir();self.ctx=Fixture(self.root/'state')
        cfg=self.ctx.config();cfg['pools']['data']={'name':'data','filesystem_uuid':'fixture-volume','mountpoint':str(self.volume),'read_only':False};self.ctx.save(cfg)
        self.radio=MyRadio(self.ctx);self.radio.configure({'pool':'data'})
        self.addCleanup(patch.stopall);patch('freeqnap.nas.myradio.rename_exclusive',rename).start();patch('freeqnap.nas.myradio.audio_metadata',lambda fd:{'artist':'Test artist','album':'Test album','genre':'Jazz','duration':12}).start();patch('freeqnap.nas.myradio.jpeg',lambda fd,**kw:b'cover').start()
    def upload(self,data=b'Hello book',name='book.txt',kind='books'):
        value=self.radio.upload_begin({'category':kind,'name':name,'bytes':len(data)})
        self.radio.upload_chunk({'upload_id':value['upload_id'],'offset':0,'data_base64':base64.b64encode(data).decode()})
        return self.radio.upload_finish({'upload_id':value['upload_id']})['item']
    def test_upload_text_playback_and_identity_bounds(self):
        item=self.upload();self.assertEqual(self.radio.book_text({'id':item['id']})['text'],'Hello book')
        self.assertEqual(base64.b64decode(self.radio.read({'id':item['id']})['data_base64']),b'Hello book')
        path=self.volume/'.freeqnap-myradio'/self.radio.asset(item['id'])['path'];path.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.radio.read({'id':item['id']})
        for bad in ['../../root','a'*100]:
            with self.assertRaises(ValueError):self.radio.asset(bad)
    def test_music_filters_and_metadata_survive_rescan(self):
        item=self.upload(b'audio','song.mp3','music');self.radio.metadata({'id':item['id'],'metadata':{'title':'Owner title','genre':'Blues'},'favorite':True})
        self.radio.scan({});result=self.radio.catalog({'category':'music','genre':'Blues','favorite':True})
        self.assertEqual(result['items'][0]['metadata']['title'],'Owner title')
        sidecar=self.volume/'.freeqnap-myradio'/'music'/item['id']/'metadata.json'
        self.assertEqual(json.loads(sidecar.read_text())['title'],'Owner title')
    def test_originals_and_photo_archive_cannot_be_reached_through_general_files(self):
        from freeqnap.nas.files import Files
        with self.assertRaises(ValueError):
            with Files(self.ctx).directory('pool:data','.freeqnap-myradio'):pass
        item=self.upload();self.assertNotIn('path',item)
        self.assertFalse(self.radio.config()['musicbrainz']);self.assertFalse(self.radio.config()['openlibrary'])
        with self.assertRaises(ValueError):self.radio.lookup({'id':item['id']})
    def test_bad_names_offsets_and_nested_symlinks_fail_closed(self):
        for bad in ['../x.mp3','.secret.mp3','a/b.mp3','x.exe']:
            with self.assertRaises(ValueError):self.radio.upload_begin({'category':'music','name':bad,'bytes':1})
        value=self.radio.upload_begin({'category':'music','name':'x.mp3','bytes':2})
        with self.assertRaises(ValueError):self.radio.upload_chunk({'upload_id':value['upload_id'],'offset':1,'data_base64':'YQ=='})
        with self.assertRaises(ValueError):self.radio.upload_finish({'upload_id':value['upload_id']})
        (self.volume/'.freeqnap-myradio'/'books').rmdir();(self.volume/'.freeqnap-myradio'/'books').symlink_to(self.root)
        with self.assertRaises(OSError):self.upload()
    def test_unsupported_original_is_retained_and_readable_companion_can_play(self):
        original=self.upload(b'Kindle fixture','book.kpf');self.assertEqual(original['metadata']['playable'],'original-only')
        text=self.upload(b'Readable edition','book.txt');self.radio.metadata({'id':original['id'],'metadata':{'companion_id':text['id']}})
        self.assertEqual(self.radio.book_text({'id':original['id']})['text'],'Readable edition')
        self.assertEqual(base64.b64decode(self.radio.read({'id':original['id']})['data_base64']),b'Kindle fixture')
    def test_private_marker_and_volume_identity_required(self):
        marker=self.volume/'.freeqnap-myradio'/'.library.json';marker.write_text('{}')
        with self.assertRaises(ValueError):self.upload()
    def test_episode_feed_does_not_expose_private_feed_url(self):
        source=b'<rss><channel><title>My podcast</title><item><guid>x</guid><title>Episode</title><enclosure url="https://public.example/episode.mp3" type="audio/mpeg"/></item></channel></rss>'
        with patch('freeqnap.nas.myradio.public_http.target'),patch('freeqnap.nas.myradio.public_http.fetch',return_value=source):self.radio.feed_add({'url':'https://public.example/rss?private=TOKEN','country':'US'})
        result=self.radio.feeds({});self.assertEqual(result['feeds'][0]['title'],'My podcast');self.assertNotIn('TOKEN',json.dumps(result));self.assertEqual(len(result['episodes']),1)
    def test_metadata_source_cannot_be_script_or_credentials(self):
        item=self.upload()
        for source in ['javascript:alert(1)','https://user:secret@example.org/']:
            with self.assertRaises(ValueError):self.radio.metadata({'id':item['id'],'metadata':{'source_url':source}})

    def test_download_interruption_resume_and_post_rename_reconciliation(self):
        class Response:
            status=200
            def __init__(self,data,fail=False):self.data=data;self.fail=fail
            def getheader(self,key):return {'Content-Length':'11','ETag':'"same"'}.get(key)
            def read(self,count):
                if self.fail and not self.data:raise OSError('connection lost')
                data=self.data;self.data=b'';return data
        @contextlib.contextmanager
        def first(*args,**kwargs):yield Response(b'Hello ',True),'https://public.example/book.txt'
        with patch('freeqnap.nas.myradio.public_http.target'):
            source=self.radio.queue_url({'category':'books','name':'book.txt','url':'https://public.example/book.txt'},lambda *a:'job')['source_id']
        with patch('freeqnap.nas.myradio.public_http.open_url',first),self.assertRaises(OSError):self.radio.download({'source':source})
        self.assertEqual(self.radio.status()['pending'][0]['bytes'],6)
        @contextlib.contextmanager
        def resume(url,headers,**kwargs):
            self.assertEqual(headers['Range'],'bytes=6-');self.assertEqual(headers['If-Range'],'"same"')
            response=Response(b'world');response.status=206
            response.getheader=lambda key:{'Content-Length':'5','Content-Range':'bytes 6-10/11','ETag':'"same"'}.get(key)
            yield response,url
        with patch('freeqnap.nas.myradio.public_http.open_url',resume),patch.object(self.radio,'register',side_effect=RuntimeError('interrupted after rename')):
            with self.assertRaises(RuntimeError):self.radio.download({'source':source})
        with patch('freeqnap.nas.myradio.public_http.open_url',side_effect=AssertionError('must not redownload')):
            item=self.radio.download({'source':source})['item']
        self.assertEqual(self.radio.book_text({'id':item['id']})['text'],'Hello world')
        self.assertFalse(self.radio.status()['pending'])
    def test_download_refuses_changed_partial_and_reconciles_interrupted_state(self):
        with patch('freeqnap.nas.myradio.public_http.target'):
            source=self.radio.queue_url({'category':'books','name':'book.txt','url':'https://public.example/book.txt'},lambda *a:'job')['source_id']
        with self.ctx.state.connect() as db:db.execute("UPDATE radio_sources SET status='running' WHERE id=?",(source,))
        self.radio.reconcile_downloads();self.assertEqual(self.radio.status()['pending'][0]['status'],'retryable')
        partial=self.volume/'.freeqnap-myradio'/'incoming'/(source+'.part');partial.write_bytes(b'changed')
        with patch('freeqnap.nas.myradio.public_http.open_url',side_effect=AssertionError('no request')):
            with self.assertRaisesRegex(ValueError,'partial changed'):self.radio.download({'source':source})
        self.assertEqual(partial.read_bytes(),b'changed')
    def test_upload_finish_reconciles_rename_without_overwrite(self):
        start=self.radio.upload_begin({'category':'books','name':'book.txt','bytes':5})
        self.radio.upload_chunk({'upload_id':start['upload_id'],'offset':0,'data_base64':'SGVsbG8='})
        with patch.object(self.radio,'register',side_effect=RuntimeError('crash')):
            with self.assertRaises(RuntimeError):self.radio.upload_finish({'upload_id':start['upload_id']})
        item=self.radio.upload_finish({'upload_id':start['upload_id']})['item']
        self.assertEqual(self.radio.book_text({'id':item['id']})['text'],'Hello')

    def test_resume_upload_compares_existing_bytes_and_preserves_original(self):
        start=self.radio.upload_begin({'category':'books','name':'book.txt','bytes':6});ident=start['upload_id']
        self.radio.upload_chunk({'upload_id':ident,'offset':0,'data_base64':'SGVs'})
        self.assertTrue(self.radio.upload_chunk({'upload_id':ident,'offset':0,'data_base64':'SGVs'})['verified_existing'])
        with self.assertRaisesRegex(ValueError,'same original'):self.radio.upload_chunk({'upload_id':ident,'offset':0,'data_base64':'YmFk'})
        self.radio.upload_chunk({'upload_id':ident,'offset':3,'data_base64':'bG8h'})
        item=self.radio.upload_finish({'upload_id':ident})['item'];self.assertEqual(self.radio.book_text({'id':item['id']})['text'],'Hello!')

    def test_custom_cover_survives_rescan_with_bounded_native_decoder_budget(self):
        item=self.upload(b'audio','track.mp3','music')
        with patch('freeqnap.nas.myradio.jpeg',return_value=b'custom-cover') as decode:
            self.radio.artwork({'id':item['id'],'data_base64':'eA=='})
            self.assertEqual(decode.call_args.kwargs['memory_limit'],384*1024**2)
        with patch('freeqnap.nas.myradio.jpeg',side_effect=AssertionError('must retain custom cover')):
            self.radio.scan({})
        cover=self.radio.read({'id':item['id'],'variant':'cover'})
        self.assertEqual(base64.b64decode(cover['data_base64']),b'custom-cover')
        self.assertTrue(self.radio.asset(item['id'])['metadata']['custom_cover'])

class BookAndNetworkTests(unittest.TestCase):
    def test_epub_reading_order_docx_and_markup_are_safe(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:
            z.writestr('META-INF/container.xml','<container><rootfile full-path="OEBPS/book.opf"/></container>')
            z.writestr('OEBPS/book.opf','<package xmlns="urn:test"><manifest><item id="a" href="a.xhtml"/></manifest><spine><itemref idref="a"/></spine></package>')
            z.writestr('OEBPS/a.xhtml','<html><h1>A chapter</h1><script>secret()</script><p>Safe words.</p></html>')
        with tempfile.TemporaryFile() as f:
            f.write(raw.getvalue());f.flush();value=extract_book(f.fileno(),'.epub')
        self.assertIn('A chapter',value['text']);self.assertIn('Safe words.',value['text']);self.assertNotIn('secret',value['text'])
        self.assertEqual(plain('<style>hidden</style>Read me'),'Read me')
    def test_xml_entities_zip_traversal_and_bombs_rejected(self):
        for raw in [b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>','<!DOCTYPE x><x/>'.encode('utf-16')]:
            with self.assertRaises(ValueError):xml(raw)
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('../x','x');z.writestr('bomb','x'*100000)
        with zipfile.ZipFile(io.BytesIO(data.getvalue())) as z:
            for path in ['../x','bomb']:
                with self.assertRaises(ValueError):zip_member(z,path)
    def test_public_resolution_blocks_internal_and_mixed_dns(self):
        def resolver(*args,**kwargs):return [(None,None,None,None,('8.8.8.8',443))]
        self.assertEqual(target('https://public.example/',resolver)[1],['8.8.8.8'])
        for address in ['127.0.0.1','192.168.1.1','169.254.169.254','::1','::ffff:192.168.1.1','64:ff9b::c0a8:101','2002:c0a8:101::']:
            def bad(*args,**kwargs):return [(None,None,None,None,(address,443)),(None,None,None,None,('8.8.8.8',443))]
            with self.assertRaises(ValueError):target('https://public.example/',bad)
        for url in ['file:///etc/passwd','https://name:password@public.example/','https://public.example/#secret','https://@public.example/']:
            with self.assertRaises(ValueError):target(url,resolver)

class RegionalRadioTests(unittest.TestCase):
    setUp=MyRadioTests.setUp
    def test_foreign_stations_hidden_and_direct_playback_denied(self):
        with self.ctx.state.connect() as db:
            for code in ('US','CA','GB',''):
                ident=(code or 'unknown').lower().ljust(32,'0');db.execute('INSERT INTO radio_stations(id,name,url,metadata) VALUES(?,?,?,?)',(ident,'Regional '+code,'https://public.example/live',json.dumps({'countrycode':code})))
        listed=self.radio.stations({})['items'];self.assertTrue(all(v['metadata']['countrycode'] in ('US','CA') for v in listed))
        with self.assertRaises(ValueError):self.radio.station_source({'id':'gb'.ljust(32,'0')})
        self.assertEqual(self.radio.stations({'country':'CA','query':'Regional'})['items'][0]['metadata']['countrycode'],'CA')
    def test_online_search_pins_each_requested_country_and_drops_bad_directory_rows(self):
        calls=[]
        def directory(url):
            from urllib.parse import urlsplit,parse_qs
            q=parse_qs(urlsplit(url).query);calls.append(q);return [{'countrycode':'GB','stationuuid':'foreign','name':'Foreign','url':'https://public.example/live'}]
        with patch('freeqnap.nas.myradio.public_http.json_fetch',side_effect=directory),patch('freeqnap.nas.myradio.public_http.probe_stream') as probe:
            self.radio.station_refresh({'query':'Jazz','country':'CA'});probe.assert_not_called()
        self.assertEqual(calls[0]['countrycode'],['CA']);self.assertEqual(calls[0]['name'],['Jazz'])
        with self.assertRaises(ValueError):self.radio.station_refresh({'country':'GB'})
    def test_podcast_country_required_and_old_unclassified_records_retained(self):
        with self.assertRaises(ValueError):self.radio.feed_add({'url':'https://public.example/rss','country':'GB'})
        with self.ctx.state.connect() as db:db.execute('INSERT INTO radio_feeds VALUES(?,?,?,?,NULL)',('a'*32,'https://public.example/rss?private=TOKEN','Old podcast','{}'))
        result=self.radio.feeds({});self.assertFalse(result['feeds']);self.assertEqual(len(result['unclassified_feeds']),1);self.assertNotIn('TOKEN',json.dumps(result))
        self.radio.feed_add({'id':'a'*32,'country':'CA'});result=self.radio.feeds({});self.assertEqual(result['feeds'][0]['metadata']['countrycode'],'CA')
