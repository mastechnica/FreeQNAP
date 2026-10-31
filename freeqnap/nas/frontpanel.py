"""Read-only front-panel snapshots; never alter hardware LED outputs."""
import json,time
from pathlib import Path

_network_counters={}

def network_snapshot():
 rows={}
 for label,iface in (('lan1','enp0s3'),('lan2','enp0s1'),('sfp','enp0s0')):
  base=Path('/sys/class/net')/iface
  try:up=(base/'carrier').read_text().strip()=='1'
  except OSError:up=None
  try:
   speed=int((base/'speed').read_text())
   if speed<=0:speed=None
  except (OSError,ValueError):speed=None
  activity=None
  try:
   counter=int((base/'statistics/rx_packets').read_text())+int((base/'statistics/tx_packets').read_text())
   previous=_network_counters.get(iface);activity=previous is not None and counter>previous
   _network_counters[iface]=counter
  except (OSError,ValueError):pass
  rows[label]={'interface':iface,'up':up,'speed_mbps':speed,'activity':activity}
 return rows

def snapshot():
 try:
  value=json.loads(Path('/run/eyeq-disk-leds.json').read_text());age=time.monotonic()-value['updated_monotonic']
  if not 0<=age<3:raise ValueError('LED telemetry stale')
  ports=[]
  for row in value['ports']:
   bay=row['bay']
   if bay not in (1,2,3,4):raise ValueError('Invalid bay')
   raw=int((Path('/sys/class/leds')/('eyeq:green:disk'+str(bay))/'brightness').read_text())
   ports.append({'bay':bay,'disk':row['disk'],'present':row['present'],'activity':row['recent_activity'],'green':bool(raw) if row['kernel_active_low'] else not bool(raw)})
  if sorted(p['bay'] for p in ports)!=[1,2,3,4]:raise ValueError('Missing bay')
  return {'network':network_snapshot(),'available':True,'sampled_at':time.time(),'age_seconds':age,'test_in_progress':value.get('test_in_progress',False),'ports':ports,'red_available':False,'timing':'Sampled green hardware output; browser latency may miss short pulses. MCU red/status LEDs unavailable in this feed.'}
 except (OSError,ValueError,KeyError,TypeError):return {'network':network_snapshot(),'available':False,'ports':[],'red_available':False,'timing':'Front-panel telemetry unavailable'}
