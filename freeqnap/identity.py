"""Optional OIDC authorization-code login: explicit local links, PKCE, nonce and JWKS."""
import base64,hashlib,json,secrets,time,urllib.parse,urllib.request
from . import accounts

def https_url(value):
 if not isinstance(value,str) or len(value)>2000 or any(ord(c)<33 for c in value):raise ValueError('Enter a trusted HTTPS URL')
 p=urllib.parse.urlsplit(value)
 if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment:raise ValueError('Use HTTPS without embedded credentials or fragments')
 return p

def origin(value):
 p=https_url(value);return p.scheme+'://'+p.netloc

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('Identity provider redirects are refused for back-channel requests')

def fetch(url,data=None,headers=None):
 https_url(url);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 request=urllib.request.Request(url,data=data,headers={'Accept':'application/json',**(headers or {})})
 try:
  with opener.open(request,timeout=10) as response:
   raw=response.read(1024*1024+1)
   if len(raw)>1024*1024:raise ValueError('Identity response exceeds limit')
   result=json.loads(raw)
   if not isinstance(result,dict):raise ValueError('Invalid identity response')
   return result
 except (OSError,ValueError) as e:raise ValueError('Identity provider unavailable or returned an invalid response; local login remains available') from e

class Identity:
 def __init__(self,state,origins):self.state=state;self.origins=set(origins)
 def config(self):return self.state.setting('oidc-provider',{'enabled':False})
 def status(self):
  cfg=self.config();return {k:v for k,v in cfg.items() if k!='client_secret'}|{'client_secret_set':bool(cfg.get('client_secret')),'local_login_always_available':True,'callback_path':'/auth/oidc/callback','supported_signing_algorithm':'RS256'}
 def discovery(self,cfg):
  url=cfg['issuer'].rstrip('/')+'/.well-known/openid-configuration';d=fetch(url)
  if d.get('issuer','').rstrip('/')!=cfg['issuer'].rstrip('/'):raise ValueError('Identity issuer does not match discovery')
  for key in ('authorization_endpoint','token_endpoint','jwks_uri'):
   if origin(d.get(key))!=origin(cfg['issuer']):raise ValueError('Identity endpoints must use the configured issuer origin')
  if 'RS256' not in d.get('id_token_signing_alg_values_supported',[]):raise ValueError('Select an RSA signing key (RS256) on the provider')
  return d
 def save(self,user,r):
  if user['role']!='administrator':raise PermissionError('Administrator access required')
  if set(r)-{'enabled','issuer','client_id','client_secret','redirect_uri','required_group','session_minutes'}:raise ValueError('Unknown identity setting')
  old=self.config();enabled=r.get('enabled',False)
  if type(enabled)is not bool:raise ValueError('Choose enabled or disabled')
  if not enabled:
   cfg={**old,'enabled':False}
  else:
   cfg={**old,**r,'enabled':True};cfg['issuer']=str(cfg.get('issuer','')).strip();https_url(cfg['issuer'])
   if not isinstance(cfg.get('client_id'),str) or not 1<=len(cfg['client_id'])<=500:raise ValueError('Enter the client ID')
   if not r.get('client_secret'):cfg['client_secret']=old.get('client_secret','')
   if not isinstance(cfg['client_secret'],str) or not 1<=len(cfg['client_secret'])<=4000:raise ValueError('Enter the confidential client secret')
   callback=https_url(cfg.get('redirect_uri',''))
   if origin(cfg['redirect_uri']) not in self.origins or callback.path!='/auth/oidc/callback' or callback.query:raise ValueError('Use this NAS trusted HTTPS origin followed by /auth/oidc/callback')
   minutes=cfg.get('session_minutes',60)
   if type(minutes)is not int or not 15<=minutes<=240:raise ValueError('Cloud sessions must be 15–240 minutes')
   cfg['session_minutes']=minutes;cfg['required_group']=str(cfg.get('required_group','')).strip()
   if len(cfg['required_group'])>200:raise ValueError('Group name is too long')
   try:import jwt
   except ImportError:raise ValueError('Install python3-jwt and python3-cryptography before enabling OIDC') from None
   self.discovery(cfg)
  self.state.set('oidc-provider',cfg)
  with self.state.connect() as db:
   db.execute("DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM account_sessions WHERE source='oidc')");db.execute("DELETE FROM account_sessions WHERE source='oidc'");db.execute('DELETE FROM oidc_transactions');accounts.audit(db,user['id'],'identity-settings', 'provider')
  return self.status()
 def begin(self,user=None):
  cfg=self.config()
  if not cfg.get('enabled'):raise ValueError('Cloud sign-in is not enabled; use local login')
  d=self.discovery(cfg);state=secrets.token_urlsafe(32);binding=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(48)
  payload={'nonce':nonce,'verifier':verifier,'link_user':user['id'] if user else None,'link_version':self.user_version(user['id']) if user else None,'config_hash':hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest()}
  with self.state.connect() as db:
   db.execute('DELETE FROM oidc_transactions WHERE expires<?',(time.time(),))
   if db.execute('SELECT count(*) FROM oidc_transactions').fetchone()[0]>=64:raise ValueError('Too many pending cloud logins; wait a few minutes')
   db.execute('INSERT INTO oidc_transactions VALUES(?,?,?,?)',(hashlib.sha256(state.encode()).hexdigest(),hashlib.sha256(binding.encode()).hexdigest(),json.dumps(payload),time.time()+300))
  query={'client_id':cfg['client_id'],'redirect_uri':cfg['redirect_uri'],'response_type':'code','scope':'openid profile email','state':state,'nonce':nonce,'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256'}
  return d['authorization_endpoint']+'?'+urllib.parse.urlencode(query),binding
 def finish(self,state,code,binding,current_user=None):
  if not all(isinstance(x,str) and 1<=len(x)<=4096 for x in (state,code,binding)):raise ValueError('Cloud login is invalid or expired')
  with self.state.connect() as db:
   db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT * FROM oidc_transactions WHERE state_hash=?',(hashlib.sha256(state.encode()).hexdigest(),)).fetchone()
   if not row or row['expires']<time.time() or not secrets.compare_digest(row['binding_hash'],hashlib.sha256(binding.encode()).hexdigest()):raise ValueError('Cloud login is invalid or expired')
   db.execute('DELETE FROM oidc_transactions WHERE state_hash=?',(row['state_hash'],));pending=json.loads(row['payload'])
  cfg=self.config()
  if not cfg.get('enabled') or pending['config_hash']!=hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest():raise ValueError('Identity configuration changed; start again')
  if pending['link_user'] and (current_user and current_user['id']!=pending['link_user'] or self.user_version(pending['link_user'])!=pending['link_version']):raise ValueError('Sign in locally before linking this identity')
  d=self.discovery(cfg);basic=base64.b64encode((urllib.parse.quote(cfg['client_id'],safe='')+':'+urllib.parse.quote(cfg['client_secret'],safe='')).encode()).decode()
  result=fetch(d['token_endpoint'],urllib.parse.urlencode({'grant_type':'authorization_code','code':code,'redirect_uri':cfg['redirect_uri'],'code_verifier':pending['verifier']}).encode(),{'Authorization':'Basic '+basic,'Content-Type':'application/x-www-form-urlencoded'})
  claims=self.validate_token(result.get('id_token'),d,cfg,pending['nonce'])
  if cfg.get('required_group') and (not isinstance(claims.get('groups'),list) or cfg['required_group'] not in claims['groups']):raise ValueError('The identity is not in the required provider group')
  with self.state.connect() as db:
   db.execute('BEGIN IMMEDIATE');link=db.execute('SELECT user_id FROM external_identities WHERE issuer=? AND subject=?',(d['issuer'],claims['sub'])).fetchone()
   if pending['link_user']:
    if link and link['user_id']!=pending['link_user']:raise ValueError('This cloud identity is already linked to another local account')
    account=db.execute('SELECT * FROM local_accounts WHERE id=? AND enabled=1',(pending['link_user'],)).fetchone()
    if not account:raise ValueError('Local account is unavailable')
    db.execute('INSERT OR IGNORE INTO external_identities VALUES(?,?,?)',(d['issuer'],claims['sub'],pending['link_user']));accounts.audit(db,pending['link_user'],'link-cloud-identity',pending['link_user'])
    return {'linked':True}
   if not link:raise ValueError('No local account is linked to this identity. Sign in locally and choose Link my Authentik login.')
   account=db.execute('SELECT * FROM local_accounts WHERE id=? AND enabled=1',(link['user_id'],)).fetchone()
   if not account or account['must_change']:raise ValueError('Complete local password setup before cloud login')
   accounts.audit(db,account['id'],'cloud-login',account['id'])
  token,csrf=accounts.create_session(self.state,account,'oidc',cfg.get('session_minutes',60)*60)
  return {'token':token,'csrf':csrf}
 def user_version(self,ident):
  with self.state.connect() as db:r=db.execute('SELECT version FROM local_accounts WHERE id=? AND enabled=1',(ident,)).fetchone()
  return r[0] if r else None
 def validate_token(self,token,discovery,cfg,nonce):
  try:
   import jwt
   if not isinstance(token,str) or len(token)>32768:raise ValueError('Invalid token size')
   header=jwt.get_unverified_header(token)
   if header.get('alg')!='RS256' or not isinstance(header.get('kid'),str):raise ValueError('Unaccepted signing algorithm/key')
   keys=fetch(discovery['jwks_uri']).get('keys',[])
   if not isinstance(keys,list) or len(keys)>50:raise ValueError('Invalid signing key set')
   matching=[k for k in keys if k.get('kid')==header['kid'] and k.get('kty')=='RSA' and k.get('use','sig')=='sig' and k.get('alg','RS256')=='RS256']
   if len(matching)!=1:raise ValueError('No unique accepted signing key')
   key=jwt.PyJWK.from_dict(matching[0]).key
   if key.key_size<2048:raise ValueError('RSA signing key must be at least 2048 bits')
   claims=jwt.decode(token,key,algorithms=['RS256'],issuer=discovery['issuer'],audience=cfg['client_id'],leeway=30,options={'require':['exp','iat','iss','aud','sub','nonce']})
   if not isinstance(claims['sub'],str) or not 1<=len(claims['sub'])<=1000 or claims['nonce']!=nonce:raise ValueError('Subject or nonce mismatch')
   if (isinstance(claims['aud'],list) and len(claims['aud'])>1 or 'azp' in claims) and claims.get('azp')!=cfg['client_id']:raise ValueError('Authorized party mismatch')
   return claims
  except Exception as e:raise ValueError('Cloud identity token validation failed') from e
 def unlink(self,user,r):
  with self.state.connect() as db:
   row=db.execute('SELECT * FROM local_accounts WHERE id=?',(user['id'],)).fetchone()
   if not row or not accounts.verify(row,r.get('current_password')):raise ValueError('Confirm your local password')
   db.execute('DELETE FROM external_identities WHERE user_id=? AND issuer=? AND subject=?',(user['id'],r.get('issuer'),r.get('subject')));db.execute("DELETE FROM sessions WHERE token_hash IN (SELECT token_hash FROM account_sessions WHERE user_id=? AND source='oidc')",(user['id'],));db.execute("DELETE FROM account_sessions WHERE user_id=? AND source='oidc'",(user['id'],));accounts.audit(db,user['id'],'unlink-cloud-identity',user['id'])
  return {'unlinked':True,'local_login_available':True}
