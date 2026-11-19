"""Member views of shared hardware and account-scoped download jobs."""
import time

def health(backend):
 info=backend.alerts.list();allowed={'inventory','raid','smart','space','temperature','services','cooling','watchdog','workers','https'}
 rows=[]
 for item in info['items']:
  if item['scope'].removeprefix('monitor-') not in allowed:continue
  row={k:item[k] for k in ('id','scope','severity','title','first_seen','last_seen','resolved_at','acknowledged_at')}
  row['details']={k:v for k,v in item['details'].items() if k in ('celsius','used_percent','missing_or_rebuilding','operation','state')};rows.append(row)
 counts={}
 for row in rows:
  if row['resolved_at'] is None:counts[row['severity']]=counts.get(row['severity'],0)+1
 return {'items':rows,'active_counts':counts,'active_total':sum(counts.values()),'monitor':{'checked_at':info['monitor'].get('checked_at')},'monitor_stale':info['monitor_stale'],'read_only':True}

def downloads(manager,owner,action,payload):
 actor='user:'+owner
 def owned(row):return row.get('actor')==actor
 if action=='downloads.status':
  return {**manager.status(payload,actor=actor),'member_view':True}
 if action=='downloads.limits':
  from ..access_scope import current
  if current()!=actor:raise ValueError('Download account identity mismatch')
  if payload.get('scope')!='account':raise ValueError('Global download limits require an administrator')
  return manager.limits(payload)
 if action=='downloads.discover':
  from .download_discovery import discover
  return discover(payload)
 if action=='downloads.destination':
  from ..access_scope import current
  if current()!=actor:raise ValueError('Download account identity mismatch')
  return manager.choose_destination(payload)
 if action=='downloads.add':
  from ..access_scope import current
  if current()!=actor:raise ValueError('Download account identity mismatch')
  return manager.add(payload)
 if action not in ('downloads.control','downloads.files','downloads.read'):raise ValueError('Shared download settings require an administrator')
 row=manager.jobs().get(payload.get('id')) or manager.ctx.state.setting('downloads_retained_files',{}).get(payload.get('id'))
 if not row or not owned(row):raise ValueError('Download not available to this account')
 return {'downloads.control':manager.control,'downloads.files':manager.list_files,'downloads.read':manager.read_file}[action](payload)
