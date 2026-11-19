import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from freeqnap.access_scope import using
from freeqnap.nas.common import Context
from freeqnap.nas.download_limits import enforce, plan
from freeqnap.nas.downloads import DownloadEngineUnavailable, Downloads, SERVICE
from freeqnap.nas.member_services import downloads


class DownloadQueueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.ctx = Context(Path(temp.name))
        self.manager = Downloads(self.ctx)
        self.manager.target = Mock()
        self.ctx.state.set('downloads_settings', {'pool':'fixture'})
        self.actor = 'user:' + 'a' * 32

    def rows(self, count):
        return {str(i): {'id':str(i), 'gid':str(i), 'created':i, 'desired':'running',
                         'actor':self.actor, 'state':'paused', 'label':'fixture'}
                for i in range(count)}

    def test_add_page_filter_and_reopen_above_old_limit(self):
        rows = self.rows(1100)
        rows['0']['state'] = 'active'
        rows['1']['actor'] = 'user:' + 'b' * 32
        self.ctx.state.set('downloads_jobs', rows)
        with using(self.actor):
            new = self.manager.add({'url':'https://example.org/file.zip'})['job']
            reopened = Downloads(Context(self.ctx.directory))
            def page(**payload):
                return downloads(reopened, self.actor[5:], 'downloads.status', payload)
            first = page()
            self.assertEqual(first['jobs'][0]['id'], new['id'])
            self.assertEqual(first['total_jobs'], 1100)
            ids = [job['id'] for offset in range(0, 1100, first['page_size'])
                   for job in page(offset=offset)['jobs']]
            self.assertEqual(len(set(ids)), 1100)
            self.assertNotIn('1', ids)
            self.assertEqual([r['id'] for r in page(filter='active')['jobs']], ['0'])

    def test_restored_job_outside_cursor_runs_in_first_pass(self):
        rows = self.rows(700)
        rows['0']['desired'] = 'paused'
        rows['1']['attention_required'] = True
        self.ctx.state.set('downloads_jobs', rows)
        self.ctx.state.set('downloads_cursor', 350)
        self.ctx.state.set('downloads_account_limits', {self.actor:{'concurrent':1,'download_kib':10}})
        def rpc(method, args):
            if method in ('tellActive','tellWaiting'):
                return []
            if method == 'tellStatus':
                return {'status':'paused'}
        self.manager.rpc = Mock(side_effect=rpc)
        self.manager.reconcile()
        resumes = [args for method,args in (call.args for call in self.manager.rpc.call_args_list) if method=='unpause']
        self.assertEqual(resumes, [['2']])
        self.manager.rpc.assert_any_call('changeOption',['2',{'max-download-limit':'10240'}])

    def test_enforces_account_limit_past_engine_page_two(self):
        rows = self.rows(700)
        self.ctx.state.set('downloads_jobs', rows)
        self.ctx.state.set('downloads_account_limits', {self.actor:{'concurrent':1,'download_kib':0}})
        waiting = [{'gid':str(i),'status':'waiting' if i==699 else 'paused'} for i in range(700)]
        def rpc(method,args):
            if method=='tellActive':return []
            if method=='tellWaiting':return waiting[args[0]:args[0]+args[1]]
        self.manager.rpc=Mock(side_effect=rpc)
        enforce(self.manager,plan(self.manager))
        self.manager.rpc.assert_any_call('forcePause',['699'])

    def test_engine_start_requires_runnable_intent_enabled_unit_and_valid_mount(self):
        rows=self.rows(1)
        self.ctx.state.set('downloads_jobs',rows)
        self.manager.rpc=Mock(side_effect=DownloadEngineUnavailable())
        self.ctx.run=Mock(return_value='UnitFileState=enabled\nActiveState=inactive\n')
        self.manager.reconcile()
        self.ctx.run.assert_called_with('systemctl','start','--no-block',SERVICE)
        self.ctx.run.reset_mock()
        self.ctx.run.return_value='UnitFileState=disabled\nActiveState=inactive\n'
        self.manager.reconcile()
        self.assertEqual(self.ctx.run.call_count,1)
        rows['0']['desired']='paused'
        self.ctx.state.set('downloads_jobs',rows)
        self.ctx.run.reset_mock()
        self.manager.reconcile()
        self.ctx.run.assert_not_called()
        self.manager.target.side_effect=ValueError('volume missing')
        self.manager.reconcile()
        self.ctx.run.assert_called_once_with('systemctl','stop',SERVICE)
