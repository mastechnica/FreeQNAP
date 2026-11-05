"""Trusted local broker principals. Never accept this envelope from a public API."""
import contextlib,contextvars,re
_current=contextvars.ContextVar('nas_principal',default=None)
_metadata=contextvars.ContextVar('nas_metadata_only',default=False)
def current():return _current.get()
@contextlib.contextmanager
def using(actor):
 if actor is not None and (not isinstance(actor,str) or not re.fullmatch(r'(?:user:[a-f0-9]{32}|agent:[a-f0-9]{24})',actor)):raise ValueError('Invalid access identity')
 token=_current.set(actor)
 try:yield
 finally:_current.reset(token)
@contextlib.contextmanager
def metadata():
 token=_metadata.set(True)
 try:yield
 finally:_metadata.reset(token)
def check(ctx,pool,content=False):
 if not pool.get('encrypted'):return
 lease=ctx.state.setting('volume-owner:'+pool['name'],{})
 if lease.get('identity')!=pool.get('luks_uuid') or not lease.get('actor') or lease['actor']!=current():
  if _metadata.get() and not content:return
  raise ValueError('This encrypted volume is private to the account that unlocked it. Lock and unlock it with your own credentials to change ownership.')
def claim(ctx,pool):
 if not pool.get('encrypted'):return
 if not current():raise ValueError('Sign in to unlock a private encrypted volume')
 ctx.state.set('volume-owner:'+pool['name'],{'actor':current(),'identity':pool.get('luks_uuid')})
class Broker:
 def __init__(self,base,actor):self.base=base;self.actor=actor
 def request(self,action,payload=None):return self.base.request('access.invoke',{'actor':self.actor,'action':action,'payload':payload or {}})
