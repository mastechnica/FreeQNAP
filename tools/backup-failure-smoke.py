#!/usr/bin/env python3
"""Real Restic failure tests in private namespaces and bounded RAM filesystems.

Never opens commissioned pools, real repositories or production configuration.
"""
import argparse, hashlib, json, os, secrets, shutil, subprocess, sys, tempfile, time
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-isolated-test',action='store_true',required=True)
    p.add_argument('--inner',action='store_true')
    a=p.parse_args()
    if sys.platform!='linux' or os.geteuid()!=0:raise SystemExit('Linux root fixture required')
    if not a.inner:
        os.execvp('unshare',['unshare','--mount','--net','--fork','--propagation','private',sys.executable,str(Path(__file__).resolve()),'--confirm-isolated-test','--inner'])
    subprocess.run(['mount','--make-rprivate','/'],check=True)
    for command in ('restic','mount','umount'):
        if not shutil.which(command):raise SystemExit('Required test dependency unavailable')
    report={};mounts=[];child=None
    with tempfile.TemporaryDirectory(prefix='freeqnap-backup-failure-') as directory:
        root=Path(directory)
        try:
            # All payload, cache, credentials and repository data stay in bounded RAM.
            subprocess.run(['mount','-t','tmpfs','-o','size=96m,mode=700','tmpfs',str(root)],check=True);mounts.append(root)
            source=root/'source';source.mkdir();destination=root/'destination';destination.mkdir()
            subprocess.run(['mount','-t','tmpfs','-o','size=24m,mode=700','tmpfs',str(destination)],check=True);mounts.append(destination)
            password=root/'password';password.write_text(secrets.token_urlsafe(32));password.chmod(0o600)
            repository=destination/'repository'
            env={**os.environ,'RESTIC_REPOSITORY':str(repository),'RESTIC_PASSWORD_FILE':str(password),'RESTIC_CACHE_DIR':str(root/'cache'),'GOMAXPROCS':'2','GOGC':'50'}
            def command(*args,expect=True,timeout=90):
                result=subprocess.run(['restic','--json',*args],env=env,capture_output=True,timeout=timeout)
                if expect and result.returncode:raise RuntimeError('Isolated Restic '+args[0]+' failed: '+str(result.returncode))
                return result
            proof=os.urandom(1024**2);(source/'proof.bin').write_bytes(proof);expected=hashlib.sha256(proof).hexdigest()
            command('init');first=command('backup','--quiet','--tag','freeqnap','--',str(source))
            snapshot=next(r['snapshot_id'] for r in map(json.loads,first.stdout.splitlines()) if r.get('message_type')=='summary')
            if len(snapshot)!=64:raise RuntimeError('Ambiguous snapshot identity')
            def verify_good(label):
                command('check','--read-data');stage=root/label
                command('restore',snapshot,'--target',str(stage),'--verify')
                restored=stage/str(source).lstrip('/')/'proof.bin'
                if hashlib.sha256(restored.read_bytes()).hexdigest()!=expected:raise AssertionError('Last good backup damaged')
                shutil.rmtree(stage)
            verify_good('initial-restore')
            # Force real ENOSPC in this fixture only; the source remains readable.
            (source/'new.bin').write_bytes(os.urandom(4*1024**2))
            filler=destination/'capacity-fixture'
            with filler.open('wb') as stream:
                while True:
                    try:stream.write(b'\0'*65536);stream.flush()
                    except OSError as error:
                        if error.errno!=28:raise
                        break
            failed=command('backup','--quiet','--',str(source),expect=False)
            if failed.returncode==0:raise AssertionError('Full destination accepted backup')
            filler.unlink();verify_good('after-full-restore')
            rows=json.loads(command('snapshots').stdout)
            if [r['id'] for r in rows]!=[snapshot]:raise AssertionError('Failed write published an unexpected snapshot')
            report['real_full_destination_failure_last_good_preserved']=True
            # Bound rate so the new random payload cannot complete before interruption.
            child=subprocess.Popen(['restic','--limit-upload','64','backup','--quiet','--',str(source)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            time.sleep(1)
            if child.poll() is not None:raise AssertionError('Interrupted fixture completed too early')
            child.terminate()
            try:child.wait(timeout=15)
            except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
            if child.returncode==0:raise AssertionError('Interrupted backup reported success')
            child=None
            # Only this newly owned repository; no other writer is present.
            command('unlock');verify_good('after-interruption-restore')
            if [r['id'] for r in json.loads(command('snapshots').stdout)]!=[snapshot]:raise AssertionError('Interrupted write published snapshot')
            report['interrupted_backup_last_good_restorable']=True
            saved=destination/'temporarily-unavailable';repository.rename(saved)
            missing=command('snapshots',expect=False);saved.rename(repository)
            if missing.returncode==0:raise AssertionError('Missing repository accepted')
            verify_good('after-unavailable-restore');report['unavailable_destination_recovery']=True
            # Explicit fixture-only retention keeps the newest tagged snapshot.
            second=command('backup','--quiet','--tag','freeqnap','--',str(source))
            latest=next(r['snapshot_id'] for r in map(json.loads,second.stdout.splitlines()) if r.get('message_type')=='summary')
            command('check','--read-data')
            command('forget','--keep-last','1','--tag','freeqnap','--prune')
            if [r['id'] for r in json.loads(command('snapshots').stdout)]!=[latest]:raise AssertionError('Retention did not preserve newest snapshot')
            snapshot=latest;verify_good('after-retention-restore');report['fixture_retention_keeps_verified_latest']=True
            report.update(production_configuration_changed=False,physical_data_volumes_used=False,independent_disaster_recovery_accepted=False)
        finally:
            if child and child.poll() is None:child.kill();child.wait(timeout=10)
            for mount in reversed(mounts):subprocess.run(['umount',str(mount)],check=True)
    report['temporary_ram_fixtures_removed']=True
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
