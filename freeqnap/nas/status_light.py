"""Runtime health indication through the existing serialized, ACK-checked MCU tool."""
import time

def health_mode(info):
 if not info or info.get('monitor_stale'):return 'both'
 if info.get('active_counts',{}).get('critical',0):return 'red'
 if info.get('active_total',0):return 'both'
 return 'green'

class StatusLight:
 def __init__(self,ctx):self.ctx=ctx;self.last=None
 def update(self,info):
  mode=health_mode(info)
  if mode==self.last:return
  # This tool locks the MCU for the whole transaction, sets only the status
  # light and verifies the returned mode. No fan, power or drive commands.
  self.ctx.run('/usr/bin/python3','/usr/local/share/eyeq/eyeq-hwctl.py','status-led',mode,timeout=8)
  self.ctx.state.set('physical_status_light',{'mode':mode,'verified_at':time.time(),'readback_verified':True})
  self.last=mode
