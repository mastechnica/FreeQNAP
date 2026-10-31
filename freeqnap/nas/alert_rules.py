"""Explicit future-event routing and independent local buzzer policy."""
import time
SCOPES=['raid','smart','space','temperature','jobs','schedules','services','inventory','notifications','ddns','workers','https']
def defaults():return [{'scope':'*','severity':'warning','enabled':True,'smtp':True,'push':True,'buzzer':False}]
def matches(rule,event):return rule['enabled'] and rule['scope'] in ('*',event.get('scope')) and (rule['severity']=='warning' or event.get('severity')=='critical')
class AlertRules:
 def __init__(self,ctx):self.ctx=ctx
 def status(self,request=None):return {'rules':self.ctx.state.setting('alert_rules',defaults()),'scopes':SCOPES,'buzzer':self.ctx.state.setting('buzzer_policy',{'enabled':False,'mute_until':0,'interval_seconds':60}),'last_beep':self.ctx.state.setting('buzzer_last'),'affects':'New email/push events only; existing queued sends are retained. Buzzer follows current active incidents.'}
 def save(self,request):
  rules=request.get('rules')
  if not isinstance(rules,list) or not 1<=len(rules)<=40:raise ValueError('Choose 1–40 rules')
  for r in rules:
   if not isinstance(r,dict) or set(r)!={'scope','severity','enabled','smtp','push','buzzer'} or r['scope'] not in ['*']+SCOPES or r['severity'] not in ('warning','critical') or any(type(r[k]) is not bool for k in ('enabled','smtp','push','buzzer')):raise ValueError('Invalid alert rule')
  self.ctx.state.set('alert_rules',rules);return self.status()
 def routes(self,event,routes):
  rules=self.ctx.state.setting('alert_rules',defaults())
  return [r for r in routes if any(matches(rule,event) and rule[r[0]] for rule in rules)]
 def sound(self,request):
  action=request.get('action');p=self.status()['buzzer'];now=time.time()
  if action=='enable':p.update(enabled=True,mute_until=0)
  elif action=='disable':p.update(enabled=False,mute_until=0)
  elif action=='mute':
   minutes=request.get('minutes')
   if type(minutes) is not int or not 1<=minutes<=10080:raise ValueError('Choose 1 minute to 7 days')
   p['mute_until']=now+minutes*60
  else:raise ValueError('Choose enable, disable or timed mute')
  self.ctx.state.set('buzzer_policy',p);return self.status()
 def tick(self):
  now=time.time();s=self.status();p=s['buzzer']
  if not p['enabled'] or now<p['mute_until'] or now-self.ctx.state.setting('buzzer_attempt',0)<p['interval_seconds']:return
  with self.ctx.state.connect() as db:active=[dict(r) for r in db.execute('SELECT scope,severity FROM health_alerts WHERE resolved_at IS NULL')]
  if not any(matches(rule,event) and rule['buzzer'] for rule in s['rules'] for event in active):return
  self.ctx.state.set('buzzer_attempt',now)
  self.ctx.run('/usr/bin/python3','/usr/local/share/eyeq/eyeq-hwctl.py','beep',timeout=8)
  self.ctx.state.set('buzzer_last',{'acknowledged_at':now,'physical_sound_verified':False})
