"""Local administrator tools; no raw shell or destructive default."""
import argparse, json
from pathlib import Path
from . import auth, backups, inventory, plans
from .state import State, atomic

def main():
    p = argparse.ArgumentParser(prog='freeqnap')
    p.add_argument('--state', type=Path, default=Path('/var/lib/freeqnap'))
    s = p.add_subparsers(dest='command', required=True)
    s.add_parser('status')
    s.add_parser('init-admin')
    q=s.add_parser('reset-local-password');q.add_argument('--username',required=True)
    q=s.add_parser('enroll-admin');q.add_argument('--output',type=Path,required=True)
    q = s.add_parser('backup-policy')
    q.add_argument('--daily', choices=('on', 'off'), required=True)
    q.add_argument('--keep', type=int, default=7)
    q.add_argument('--mirror-path', type=Path)
    q.add_argument('--mirror-uuid')
    s.add_parser('backup-enqueue')
    q = s.add_parser('plan-pool')
    q.add_argument('--name', required=True)
    q.add_argument('--level', choices=plans.LEVELS, required=True)
    q.add_argument('--disk', action='append', required=True)
    q.add_argument('--output', type=Path, required=True)
    q = s.add_parser('backup-create')
    q.add_argument('--source', type=Path)
    q.add_argument('--destination', type=Path, required=True)
    q.add_argument('--keep', type=int, default=7)
    for name in ('backup-verify', 'restore-preview'):
        q = s.add_parser(name)
        q.add_argument('archive', type=Path)
    a = p.parse_args()
    if a.command == 'status':
        value = inventory.collect()
    elif a.command == 'enroll-admin':
        token=auth.enrollment(State(a.state));atomic(a.output,{'enrollment_token':token,'expires_in_seconds':1800});value={'saved_privately':str(a.output),'expires_in_seconds':1800}
    elif a.command == 'init-admin':
        auth.initialize(State(a.state))
        value = {'administrator_configured': True, 'password_logged': False}
    elif a.command == 'reset-local-password':
        import os,getpass,warnings
        from . import accounts
        state=State(a.state)
        if os.geteuid() not in (0,state.database.stat().st_uid):raise ValueError('Use root or the console service account')
        accounts.ensure(state)
        with state.connect() as db:
            target=db.execute('SELECT * FROM local_accounts WHERE username=?',(a.username,)).fetchone();admin=db.execute('SELECT * FROM local_accounts WHERE primary_admin=1').fetchone()
        if not target:raise ValueError('Local account not found')
        with warnings.catch_warnings():
            warnings.simplefilter('error',getpass.GetPassWarning);one=getpass.getpass('New temporary password: ');two=getpass.getpass('Confirm temporary password: ')
        if one!=two:raise ValueError('Passwords do not match')
        value=accounts.change(state,accounts.public(admin),{'action':'set-password','id':target['id'],'password':one})
    elif a.command == 'backup-policy':
        if not 1 <= a.keep <= 365:
            raise ValueError('Retention must be 1–365')
        if bool(a.mirror_path) != bool(a.mirror_uuid):
            raise ValueError('Mirror path and UUID are required together')
        value = {'daily': a.daily == 'on', 'keep': a.keep}
        if a.mirror_path:
            backups.mounted(a.mirror_path, a.mirror_uuid)
            value['mirror'] = {'path': str(a.mirror_path.resolve()), 'uuid': a.mirror_uuid}
        State(a.state).set('backup_policy', value)
    elif a.command == 'backup-enqueue':
        value = {'job_id': State(a.state).enqueue('config-backup', {})}
    elif a.command == 'plan-pool':
        value = plans.pool_plan(inventory.collect(), a.name, a.level, a.disk)
        atomic(a.output, value)
    elif a.command == 'backup-create':
        value = backups.create(a.source or a.state, a.destination, a.keep)
    elif a.command == 'backup-verify':
        value = backups.verify(a.archive)
    else:
        value = backups.restore_preview(a.archive)
    print(json.dumps(value, indent=2))
if __name__ == '__main__':
    main()
