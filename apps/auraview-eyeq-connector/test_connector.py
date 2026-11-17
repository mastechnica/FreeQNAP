"""Run with python3 -m unittest discover -s apps/auraview-eyeq-connector."""
import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('eyeq_nas_connector',Path(__file__).with_name('connector.py'))
app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)

class Gateway:
    def __init__(self): self.calls=[]
    def request(self,action,payload):
        self.calls.append((action,payload))
        if action=='myradio.item':return {'item':{'id':'one','category':'music','hidden':False}}
        if action=='files.list':return {'entries':[{'name':'Album','directory':True},{'name':'track.mp3'},{'name':'secrets.json'},{'name':'alias.mp3','symlink':True}],'total_entries':4}
        if action.endswith('.catalog'):return {'items':[{'id':'one','name':'Track.mp3','metadata':{'title':'Track','_secret':'hidden'},'path':'/private'}],'total':1}
        return {'filename':'Track.mp3','total_bytes':3,'etag':'file','data_base64':base64.b64encode(b'abc').decode(),'path':'/private'}

class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.gw=Gateway();self.lib=app.Library({'shares':['Music']},lambda:self.gw)
    def test_catalog_removes_paths_and_private_metadata(self):
        value=self.lib.handle('catalog',{'category':'music'})
        self.assertNotIn('/private',json.dumps(value));self.assertNotIn('_secret',json.dumps(value))
    def test_folder_names_become_opaque_ids(self):
        root=self.lib.handle('catalog',{'category':'folders'})['items'][0]
        rows=self.lib.handle('catalog',{'category':'folders','folder':root['id']})['items']
        self.assertEqual([r['title'] for r in rows],['Album','track.mp3'])
        self.lib.handle('read',{'category':'folders','id':rows[1]['id'],'count':1})
        self.assertEqual(self.gw.calls[-1][1]['share'],'Music')
    def test_no_arbitrary_path_or_account_or_mutation(self):
        cases=[('catalog',{'category':'folders','folder':'/etc'}),('catalog',{'category':'music','owner':'other'}),('read',{'category':'music','id':'../secret'}),('read',{'category':'music','id':'one','count':999999}),('files.delete',{})]
        for action,payload in cases:
            with self.subTest(action=action,payload=payload),self.assertRaises(ValueError):self.lib.handle(action,payload)
    def test_private_config_is_atomic_mode_600(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'config.json';app.save(path,{'token':'test-only'})
            self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual(list(Path(d).iterdir()),[path])
    def test_gateway_rechecked_per_chunk(self):
        seen=[]
        def gateway():
            seen.append(1)
            if len(seen)>1:raise PermissionError('Disabled')
            return self.gw
        lib=app.Library({},gateway);lib.handle('read',{'category':'music','id':'one','count':1})
        with self.assertRaises(PermissionError):lib.handle('read',{'category':'music','id':'one','count':1})


class ContractGateway(Gateway):
    def request(self,action,payload):
        self.calls.append((action,payload))
        if action=='myradio.item': return {'item':{'id':'one','category':'books' if payload['id']=='book' else 'music','hidden':False}}
        if action=='photos.catalog': return {'items':[{'id':'one','name':'Picture.heic','metadata':{},'kind':'photo'}],'total':1}
        return super().request(action,payload)

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.gw=ContractGateway();self.lib=app.Library({'categories':['photos','music','books']},lambda:self.gw)
    def test_photo_thumb_uses_actual_native_variant(self):
        self.lib.handle('read',{'category':'photos','id':'one','variant':'thumb','count':1})
        self.assertEqual(self.gw.calls[-1],('photos.read',{'id':'one','variant':'thumbnail','offset':0,'count':1}))
    def test_read_cannot_escape_selected_category(self):
        with self.assertRaises(PermissionError): self.lib.handle('read',{'category':'books','id':'one'})
    def test_disabled_category_rejected_even_for_known_id(self):
        with self.assertRaises(PermissionError): self.lib.handle('read',{'category':'videos','id':'one'})
        with self.assertRaises(PermissionError): self.lib.handle('catalog',{'category':'folders'})
    def test_book_text_requires_books_grant(self):
        lib=app.Library({'categories':['music']},lambda:self.gw)
        with self.assertRaises(PermissionError):lib.handle('book',{'id':'book'})
    def test_photo_kind_rechecked_before_each_chunk(self):
        def request(action,payload):return {'items':[]}
        self.gw.request=request
        with self.assertRaises(PermissionError):self.lib.handle('read',{'category':'photos','id':'one'})
    def test_unsupported_variant_fails_before_media_read(self):
        with self.assertRaises(ValueError):self.lib.handle('read',{'category':'music','id':'one','variant':'preview'})
    def test_readiness_never_reads_original_bytes(self):
        result=self.lib.check()
        self.assertTrue(result['libraries']['music']['available'])
        self.assertFalse(result['cloud_contacted'])
        self.assertFalse(any(a.endswith('.read') for a,p in self.gw.calls))
    def test_config_rejects_insecure_or_credentialed_origins(self):
        for origin in ['http://eyeq.example','https://secret@eyeq.example','https://eyeq.example/api','https://eyeq.example/?token=secret']:
            with self.subTest(origin=origin),self.assertRaises(ValueError):app.validate({'origin':origin,'owner':'a'*32})
    def test_config_rejects_symlink_and_shared_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'config.json';app.save(p,{'origin':'https://eyeq.example','owner':'a'*32})
            self.assertEqual(app.load(p)['owner'],'a'*32)
            alias=Path(d)/'alias.json';alias.symlink_to(p)
            with self.assertRaises(ValueError):app.load(alias)
            p.chmod(0o644)
            with self.assertRaises(ValueError):app.load(p)
    def test_supported_readable_book_extensions(self):
        self.assertTrue({'.epub','.pdf','.txt','.docx','.azw','.azw3','.kpf'}<=app.MEDIA_EXT)
    def test_folder_root_rechecks_removed_share(self):
        class Denied:
            def request(self,*args):raise PermissionError('Removed')
        lib=app.Library({'shares':['Gone']},lambda:Denied())
        self.assertEqual(lib.handle('catalog',{'category':'folders'})['items'],[])

if __name__=='__main__':unittest.main()
