import errno
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from transfer import bind_when_available


class AddressWaitTests(unittest.TestCase):
    def test_unpowered_link_can_become_ready_without_network_mutation(self):
        class Listener:
            attempts=0
            def bind(self,address):
                self.attempts+=1
                if self.attempts<3:raise OSError(errno.EADDRNOTAVAIL,'inactive link')
        listener=Listener();clock=[0];messages=[]
        def sleep(seconds):clock[0]+=seconds
        bind_when_available(listener,('192.168.77.1',1069),3,
                            emit=lambda *args,**kwargs:messages.append(args[0]),
                            clock=lambda:clock[0],sleep=sleep)
        self.assertEqual(listener.attempts,3)
        self.assertEqual(len(messages),1)
        self.assertIn('WAITING',messages[0])

    def test_missing_address_times_out(self):
        class Listener:
            def bind(self,address):raise OSError(errno.EADDRNOTAVAIL,'inactive link')
        clock=[0]
        def sleep(seconds):clock[0]+=seconds
        with self.assertRaisesRegex(TimeoutError,'still unavailable'):
            bind_when_available(Listener(),('192.168.77.1',1069),1,
                                emit=lambda *args,**kwargs:None,
                                clock=lambda:clock[0],sleep=sleep)

    def test_port_collision_is_not_misreported_as_link_wait(self):
        class Listener:
            def bind(self,address):raise OSError(errno.EADDRINUSE,'port occupied')
        with self.assertRaises(OSError) as result:
            bind_when_available(Listener(),('192.168.77.1',1069))
        self.assertEqual(result.exception.errno,errno.EADDRINUSE)




class RamOnlyTransferTests(unittest.TestCase):
    def fixture(self,root,kernel='same-kernel',ram=True):
        import hashlib,json,struct,zlib
        root.mkdir();payload=('owned RAM diagnostic fixture '+kernel).encode()*100
        h=bytearray(struct.pack('>7I4B32s',0x27051956,0,0,len(payload),0x8000,0x8000,zlib.crc32(payload),5,2,2,0,b'FreeQNAP test'))
        h[4:8]=struct.pack('>I',zlib.crc32(h));image=bytes(h)+payload
        manifest={'schema':1,'model':'TS-431XeU','architecture':'armhf','kernel':kernel,'artifacts':{'uImage':{'bytes':len(image),'sha256':hashlib.sha256(image).hexdigest(),'crc32':f'{zlib.crc32(image):08x}'}}}
        if ram:manifest.update(ram_only=True,flash_allowed=False)
        (root/'manifest.json').write_text(json.dumps(manifest));(root/'uImage').write_bytes(image);return image,manifest
    def test_ram_only_default_rejected_but_explicit_paired_immutable_bytes_allowed(self):
        import tempfile
        from core import verified_image
        from transfer import load_boot_images
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);first,_=self.fixture(root/'first');second,_=self.fixture(root/'second')
            with self.assertRaisesRegex(ValueError,'RAM-only'):verified_image(root/'first')
            self.assertEqual(verified_image(root/'first',allow_ram_only=True)[1],first)
            with self.assertRaises(ValueError):load_boot_images(root/'first',additional_ram_release=root/'second')
            result=load_boot_images(root/'first',allow_ram_only=True,additional_ram_release=root/'second')
            self.assertEqual(set(result),{b'uImage',b'experiment.uImage'});(root/'first'/'uImage').write_bytes(b'changed');self.assertEqual(result[b'uImage'],first)
    def test_paired_release_requires_same_kernel_and_both_flash_prohibited(self):
        import tempfile,json
        from transfer import load_boot_images
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root/'first');self.fixture(root/'second',kernel='different')
            with self.assertRaises(ValueError):load_boot_images(root/'first',allow_ram_only=True,additional_ram_release=root/'second')
            _,m=self.fixture(root/'normal',ram=False)
            with self.assertRaises(ValueError):load_boot_images(root/'normal',allow_ram_only=True,additional_ram_release=root/'first')
            m.update(ram_only=True,flash_allowed=True);(root/'normal'/'manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):load_boot_images(root/'normal',allow_ram_only=True)


class RollbackTransferTests(unittest.TestCase):
    fixture=RamOnlyTransferTests.fixture
    def test_different_kernel_rollback_requires_independent_exact_pin(self):
        import tempfile,json,hashlib
        from transfer import load_boot_images
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);candidate,_=self.fixture(root/'new',kernel='new')
            old,manifest=self.fixture(root/'old',kernel='old',ram=False);manifest['generic_root_selector']=True;(root/'old/manifest.json').write_text(json.dumps(manifest))
            pin=hashlib.sha256(old).hexdigest()
            result=load_boot_images(root/'new',allow_ram_only=True,rollback_release=root/'old',rollback_sha256=pin)
            self.assertEqual(set(result),{b'uImage',b'rollback.uImage'})
            for bad in (None,'0'*64,'bad'):
                with self.assertRaises(ValueError):load_boot_images(root/'new',allow_ram_only=True,rollback_release=root/'old',rollback_sha256=bad)
            with self.assertRaises(ValueError):load_boot_images(root/'old',rollback_release=root/'old',rollback_sha256=pin)
            with self.assertRaises(ValueError):load_boot_images(root/'new',allow_ram_only=True,additional_ram_release=root/'new',rollback_release=root/'old',rollback_sha256=pin)
    def test_kernel_release_alias_does_not_bypass_comparison_kernel_check(self):
        import tempfile,json
        from transfer import load_boot_images
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,kernel in [('a','first'),('b','second')]:
                _,m=self.fixture(root/name,kernel=kernel);m['kernel_release']=m.pop('kernel');(root/name/'manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):load_boot_images(root/'a',allow_ram_only=True,additional_ram_release=root/'b')

if __name__=='__main__':unittest.main()
