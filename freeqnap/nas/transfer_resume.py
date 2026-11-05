"""Resume only an exact, unpublished copy stage; originals are never overwritten."""
import json
import os
from pathlib import Path
import re
import stat
from .common import canonical
from ..state import atomic


def retained(manager, ident):
    if not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident):
        raise ValueError('Choose one retained transfer')
    from ..access_scope import current
    with manager.ctx.state.connect() as db:
        job = db.execute('SELECT j.*,p.actor FROM jobs j LEFT JOIN job_principals p ON p.id=j.id WHERE j.id=?', (ident,)).fetchone()
    if not job or job['kind'] != 'files.transfer' or job['status'] != 'retryable':
        raise ValueError('Only an interrupted inactive copy can be resumed')
    if current() and job['actor'] != current():
        raise ValueError('This copy belongs to another account')
    record = json.loads((manager.ctx.directory / 'operations' / (ident+'.json')).read_text())
    if record.get('resumed_by'):
        raise ValueError('This retained copy already has a continuation')
    token = record.get('partial_stage', '')
    if not re.fullmatch('[a-f0-9]{32}', token) or record.get('published'):
        raise ValueError('Only one wholly unpublished copy stage can be resumed')
    old_id = json.loads(job['payload'])['plan_id']
    if not re.fullmatch('[a-f0-9]{32}', old_id):
        raise ValueError('Invalid saved transfer plan')
    body = json.loads((manager.ctx.directory / 'plans' / (old_id+'.json')).read_text())['body']
    if body['mode'] != 'copy' or len(body['items']) != 1:
        raise ValueError('Resume currently supports one copied folder or file, without moving its source')
    pool, mount = manager.ctx.volume(record['stage_pool'])
    if pool['filesystem_uuid'] != record['stage_uuid']:
        raise ValueError('Retained destination filesystem changed')
    stage = mount / '.freeqnap' / 'transfers' / token
    info = stage.lstat()
    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)) or info.st_dev != mount.stat().st_dev:
        raise ValueError('Retained stage identity is unsafe')
    from .fileops import fingerprint
    return record, body, {'job_id': ident, 'token': token, 'stage_pool': record['stage_pool'], 'stage_uuid': record['stage_uuid'], 'identity': fingerprint(info)}


def plan(manager, request):
    if set(request) != {'id'}:
        raise ValueError('Choose one interrupted transfer')
    record, old, stage = retained(manager, request['id'])
    item = old['items'][0]
    request = {'share': old['share'], 'paths': [item['path']], 'target_share': old['target_share'], 'target_path': old['target_path'], 'mode': 'copy'}
    if item['name'] != Path(item['path']).name:
        request['new_name'] = item['name']
    fresh = manager.transfer_plan(request)['body']
    for key in ('share', 'items', 'target_share', 'target_path', 'target_identity', 'target_uuid', 'mode'):
        if canonical(fresh[key]) != canonical(old[key]):
            raise ValueError('Source or destination changed since the original copy; retained data was kept')
    fresh['resume'] = stage
    fresh['review'] = 'Continue this exact retained, unpublished copy. Existing staged bytes are compared against the original source before reuse; mismatches are retained and stop the copy. Original files and existing destination files are never overwritten.'
    return manager.ctx.plan('file-transfer', fresh, 'RESUME COPY')


def claim(manager, body, job_id):
    if not body.get('resume'):
        return
    saved = body['resume']
    record, _, actual = retained(manager, saved['job_id'])
    if actual != saved:
        raise ValueError('Retained copy stage changed since review')
    # Publish the continuation's recovery pointer before linking the prior job.
    # An interruption during validation/scanning must not orphan retained bytes.
    next_record = manager.ctx.directory / 'operations' / (job_id+'.json')
    if next_record.exists():
        raise ValueError('Continuation checkpoint already exists')
    atomic(next_record, {'id': job_id, 'continued_from': saved['job_id'], 'stage_pool': saved['stage_pool'], 'stage_uuid': saved['stage_uuid'], 'partial_stage': saved['token'], 'published': [], 'mode': 'copy', 'target_share': body['target_share'], 'target_path': body['target_path'], 'staging_retained_on_failure': True})
    record['resumed_by'] = job_id
    atomic(manager.ctx.directory / 'operations' / (saved['job_id']+'.json'), record)
