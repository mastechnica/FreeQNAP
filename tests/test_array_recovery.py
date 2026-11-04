import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from freeqnap.nas.array_recovery import ArrayRecovery, parse_member, validate_members
from freeqnap.nas.common import Context

def metadata(role=0):
    return {'uuid':'a'*32,'member_uuid':str(role)*32,'level':'raid5','devices':4,'events':42,
            'role':role,'component_sectors':1000000,'data_offset_sectors':262144,
            'recovery_start':900000 if role==3 else None,'state':'active',
            'layout':'left-symmetric','chunk':'512K','version':'1.2'}

class ArrayRecoveryTests(unittest.TestCase):
    def test_exact_counter_geometry_roles_and_rebuilding_gate(self):
        members=[{'metadata':metadata(i)} for i in range(4)]
        self.assertTrue(validate_members(members,'a'*32)['force_required'])
        for key,value in [('events',43),('uuid','b'*32),('component_sectors',3),('data_offset_sectors',8),('role',0),('member_uuid','0'*32),('recovery_start',1000001)]:
            changed=copy.deepcopy(members);changed[1]['metadata'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_members(changed,'a'*32)
        with self.assertRaises(ValueError):validate_members(members[:3],'a'*32)
        changed=copy.deepcopy(members);changed[1]['metadata']['events']=43
        self.assertTrue(validate_members(changed,'a'*32,live=True))
        changed[1]['metadata']['component_sectors']=3
        with self.assertRaises(ValueError):validate_members(changed,'a'*32,live=True)

    def test_checksum_and_complete_numeric_metadata(self):
        raw='''Version : 1.2
Array UUID : aaaaaaaa:aaaaaaaa:aaaaaaaa:aaaaaaaa
Device UUID : 11111111:11111111:11111111:11111111
Raid Level : raid5
Raid Devices : 4
Events : 42
Used Dev Size : 1000000 sectors
Data Offset : 262144 sectors
Recovery Offset : 900000 sectors
Device Role : Active device 3
Checksum : deadbeef - correct
State : active
Layout : left-symmetric
Chunk Size : 512K
'''
        self.assertEqual(parse_member(raw)['recovery_start'],900000)
        for invalid in [raw.replace(' - correct',' - incorrect'),raw.replace('Events : 42','Events : unknown'),raw.replace('Active device 3','spare')]:
            with self.assertRaises(ValueError):parse_member(invalid)

    def test_permission_cannot_apply_a_different_recovery_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=Context(tmp);recovery=ArrayRecovery(ctx,None)
            plan=ctx.plan('array-recovery',{'mode':'resume','snapshot':{}},'RESUME')
            request={'plan_id':plan['id'],'digest':plan['digest'],'confirmation':'RESUME'}
            with self.assertRaisesRegex(ValueError,'permission'):recovery.apply(request,'readonly')
            self.assertFalse(ctx.reviewed(request,'array-recovery')[1]['consumed'])

    def test_no_recreation_or_member_mutations_in_workflow(self):
        text=(Path(__file__).parents[1]/'freeqnap/nas/array_recovery.py').read_text()
        for forbidden in ["'--create'","'--zero-superblock'","'--assume-clean'","'--remove'","'--fail'","'--add'"]:
            self.assertNotIn(forbidden,text)
        self.assertIn("'--readonly'",text)
        self.assertIn("'--no-block'",text)

    def test_metadata_export_is_bounded_and_rejects_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=Context(tmp);r=ArrayRecovery(ctx,None);ident='f'*32
            folder=r.directory/ident;folder.mkdir(parents=True)
            (folder/'metadata.tar').write_bytes(b'private metadata')
            value=r.download({'id':ident,'offset':0,'count':4})
            self.assertEqual(value['total_bytes'],16)
            for req in [{'id':'../root'},{'id':ident,'count':2**30},{'id':ident,'offset':-1}]:
                with self.assertRaises(ValueError):r.download(req)
            (folder/'metadata.tar').unlink();(folder/'metadata.tar').symlink_to(Path(tmp)/'other')
            with self.assertRaises(OSError):r.download({'id':ident})


    def test_apply_failure_consumes_once_and_records_required_inspection(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=Context(tmp);r=ArrayRecovery(ctx,None);backup='b'*32;target=r.directory/backup;target.mkdir(parents=True);(target/'metadata.tar').write_bytes(b'fixture backup')
            import hashlib
            snapshot={'pool':'data','group':'data','uuid':'a'*32,'array':None,'force_required':True,'members':[{'device':'/dev/fixture'+str(i)} for i in range(4)]}
            body={'mode':'readonly','snapshot':snapshot,'metadata_backup':{'id':backup,'sha256':hashlib.sha256(b'fixture backup').hexdigest()}}
            plan=ctx.plan('array-recovery',body,'EXACT');request={'plan_id':plan['id'],'digest':plan['digest'],'confirmation':'EXACT','backup_acknowledged':True}
            with patch.object(r,'snapshot',return_value=copy.deepcopy(snapshot)),patch.object(r,'pools',return_value=({},[])),patch.object(ctx,'run',side_effect=RuntimeError('assembly refused')) as run:
                with self.assertRaises(RuntimeError):r.apply(request,'readonly')
                self.assertEqual(run.call_count,1)
                with self.assertRaisesRegex(ValueError,'expired, used|Stored plan contents changed'):r.apply(request,'readonly')
                self.assertEqual(run.call_count,1)
            result=ctx.state.setting('array-recovery:'+'a'*32);self.assertEqual(result['phase'],'needs-inspection');self.assertFalse(result['parity_verified'])
    def test_deleting_metadata_retains_latest_and_current_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx=Context(tmp);r=ArrayRecovery(ctx,None)
            import json,os,time
            for i in (1,2):
                ident=str(i)*32;folder=r.directory/ident;folder.mkdir(parents=True);(folder/'metadata.tar').write_bytes(b'fixture');(folder/'manifest.json').write_text(json.dumps({'uuid':'a'*32,'group':'data'}));os.utime(folder/'metadata.tar',(i,i))
            older='1'*32;latest='2'*32
            request=lambda ident:{'id':ident,'confirmation':'DELETE METADATA '+ident,'backup_copied':True}
            with self.assertRaisesRegex(ValueError,'latest'):r.backup_remove(request(latest))
            plan=ctx.plan('array-recovery',{'metadata_backup':{'id':older}},'EXACT')
            with self.assertRaisesRegex(ValueError,'current recovery plan'):r.backup_remove(request(older))
            ctx.consume(ctx.directory/'plans'/(plan['id']+'.json'),plan)
            r.backup_remove(request(older));self.assertTrue((r.directory/latest/'metadata.tar').exists())
