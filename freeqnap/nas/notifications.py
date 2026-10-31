"""Local-first notification settings and independent durable outbound attempts."""
import hashlib,importlib.util,json,os,re,secrets,smtplib,ssl,threading,time
from email.message import EmailMessage
from email.utils import formatdate,make_msgid
from pathlib import Path
from . import push
from .alert_rules import AlertRules
from ..state import atomic

KEY='notifications_config';SUBS='push_subscriptions'
DEFAULT={'smtp':{'enabled':False,'host':'','port':587,'protocol':'starttls','username':'','sender':'','recipients':[],'ca_certificate':''},'push':{'enabled':False,'contact':''}}

def mailbox(value):
    if not isinstance(value,str) or len(value)>254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?",value):raise ValueError('Use a plain email address without display names or control characters')
    return value

def config(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT):raise ValueError('Choose SMTP and push settings')
    smtp=value['smtp'];p=value['push']
    if not isinstance(smtp,dict) or set(smtp)!=set(DEFAULT['smtp']) or not isinstance(p,dict) or set(p)!=set(DEFAULT['push']):raise ValueError('Unknown notification setting')
    if type(smtp['enabled']) is not bool or type(p['enabled']) is not bool:raise ValueError('Choose explicit notification enable settings')
    if not isinstance(smtp['host'],str) or len(smtp['host'])>253 or smtp['host'] and not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.:-]*[A-Za-z0-9])?',smtp['host']):raise ValueError('Use an SMTP hostname or address without a URL or options')
    if type(smtp['port']) is not int or not 1<=smtp['port']<=65535 or smtp['protocol'] not in ('starttls','tls'):raise ValueError('Choose verified STARTTLS or implicit TLS and a valid port')
    if not isinstance(smtp['username'],str) or len(smtp['username'])>254 or any(ord(c)<32 for c in smtp['username']):raise ValueError('Invalid SMTP username')
    if not isinstance(smtp['recipients'],list) or len(smtp['recipients'])>5 or len(set(smtp['recipients']))!=len(smtp['recipients']):raise ValueError('Choose at most five distinct email recipients')
    for address in smtp['recipients']:mailbox(address)
    if smtp['sender']:mailbox(smtp['sender'])
    if smtp['enabled'] and (not smtp['host'] or not smtp['sender'] or not smtp['recipients']):raise ValueError('Enabled email needs a server, sender and recipient')
    ca=smtp['ca_certificate']
    if not isinstance(ca,str) or len(ca)>16384 or 'PRIVATE KEY' in ca:raise ValueError('Use only a public SMTP CA certificate')
    if ca:ssl.create_default_context(cadata=ca)
    if not isinstance(p['contact'],str) or len(p['contact'])>254:raise ValueError('Invalid Web Push contact')
    if p['contact']:mailbox(p['contact'])
    if p['enabled'] and not p['contact']:raise ValueError('Web Push requires a contact email for VAPID')
    return {'smtp':dict(smtp),'push':dict(p)}

class Notifications:
    def __init__(self,ctx,smtp_sender=None,push_sender=None):
        self.ctx=ctx;self.lock=threading.Lock();self.smtp_sender=smtp_sender or self.send_smtp;self.push_sender=push_sender or self.send_push
        with ctx.state.connect() as db:db.executescript('''CREATE TABLE IF NOT EXISTS notification_outbox(id TEXT PRIMARY KEY,event_id INTEGER NOT NULL,target TEXT NOT NULL,revision TEXT NOT NULL,channel TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,next_attempt REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,accepted_at REAL,test INTEGER NOT NULL DEFAULT 0,UNIQUE(event_id,target,revision));''')
    def current(self):return self.ctx.state.setting(KEY,{'config':DEFAULT,'revision':'unconfigured','enabled_at':time.time(),'after_event_id':0,'credential_file':None})
    def status(self,request=None):
        value=self.current();c=config(value['config']);subs=self.ctx.state.setting(SUBS,{})
        with self.ctx.state.connect() as db:
            counts={r['status']:r['count'] for r in db.execute('SELECT status,count(*) AS count FROM notification_outbox GROUP BY status')};rows=[dict(r) for r in db.execute('SELECT id,event_id,channel,status,created,next_attempt,attempts,last_error,accepted_at FROM notification_outbox ORDER BY created DESC LIMIT 100')]
        return {'config':c,'smtp_password_saved':bool(value.get('credential_file')),'subscriptions':[{'id':k,'label':v['label'],'enabled':v['enabled'],'provider':push.endpoint(v['subscription']['endpoint']).hostname,'created_at':v['created_at'],'expired':v.get('expired',False)} for k,v in subs.items()],'outbox':rows,'outbox_counts':counts,'requires_review':counts.get('needs-review',0),'default_local_only':True,'push_dependencies_available':all(importlib.util.find_spec(x) is not None for x in ('cryptography','http_ece','py_vapid')),'relay_acceptance_is_device_receipt':False}
    def save(self,request):
        if not isinstance(request,dict) or set(request)-{'config','smtp_password'} or 'config' not in request:raise ValueError('Choose notification settings')
        c=config(request['config'])
        with self.lock:
            old=self.current();credential_file=old.get('credential_file')
            if 'smtp_password' in request:
                password=request['smtp_password']
                if not isinstance(password,str) or not 1<=len(password)<=1024 or any(ord(x)<32 for x in password):raise ValueError('Invalid private SMTP password')
                credential_file='smtp-'+secrets.token_hex(16)+'.json';atomic(self.ctx.directory/'secrets'/credential_file,{'password':password})
            if c['smtp']['username'] and c['smtp']['enabled'] and not credential_file:raise ValueError('Authenticated SMTP needs its private password')
            if old['config']['smtp']['host']!=c['smtp']['host'] or old['config']['smtp']['username']!=c['smtp']['username']:
                if c['smtp']['username'] and c['smtp']['enabled'] and 'smtp_password' not in request:raise ValueError('Enter the password again when changing the authenticated SMTP server/account')
            now=time.time()
            with self.ctx.state.connect() as db:watermark=db.execute('SELECT coalesce(max(id),0) FROM health_events').fetchone()[0]
            self.ctx.state.set(KEY,{'config':c,'revision':secrets.token_hex(16),'enabled_at':now,'after_event_id':watermark,'credential_file':credential_file})
            # Never silently replay an earlier destination/configuration backlog.
            with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='needs-review',last_error='Notification settings changed; retained for explicit reconciliation' WHERE status IN ('pending','retrying','sending')")
        return self.status()
    def require_push(self):
        if not all(importlib.util.find_spec(x) is not None for x in ('cryptography','http_ece','py_vapid')):raise ValueError('Install the optional Web Push crypto dependencies first')
    def public_key(self,request=None):
        self.require_push()
        with self.lock:_,key=push.vapid_key(self.ctx.directory/'secrets')
        return {'application_server_key':key,'permission_required':True,'browser_provider_relay_required':True}
    def subscribe(self,request):
        self.require_push()
        if not isinstance(request,dict) or set(request)!={'id','label','subscription'} or not isinstance(request['id'],str) or not re.fullmatch('[a-f0-9]{32}',request['id']):raise ValueError('Use this browser installation identifier')
        label=request['label']
        if not isinstance(label,str) or not 1<=len(label)<=80 or any(ord(x)<32 for x in label):raise ValueError('Choose a short device label')
        sub=push.subscription(request['subscription'])
        with self.lock:
            push.vapid_key(self.ctx.directory/'secrets');rows=self.ctx.state.setting(SUBS,{})
            if request['id'] not in rows and len(rows)>=32:raise ValueError('At most 32 push devices can be registered')
            with self.ctx.state.connect() as db:watermark=db.execute('SELECT coalesce(max(id),0) FROM health_events').fetchone()[0]
            revision=secrets.token_hex(16);rows[request['id']]={'label':label,'subscription':sub,'enabled':True,'expired':False,'revision':revision,'created_at':time.time(),'after_event_id':watermark};self.ctx.state.set(SUBS,rows)
            with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='needs-review',last_error='Browser subscription changed; retained for review' WHERE target=? AND status IN ('pending','retrying','sending')",('push:'+request['id'],))
        return {'subscribed':request['id'],'relay_delivery_not_yet_verified':True}
    def unsubscribe(self,request):
        ident=request.get('id')
        with self.lock:
            rows=self.ctx.state.setting(SUBS,{})
            if ident not in rows:raise ValueError('Unknown push device')
            rows[ident]['enabled']=False;self.ctx.state.set(SUBS,rows)
            with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='needs-review',last_error='Push device disabled; retained for review' WHERE target=? AND status IN ('pending','retrying','sending')",('push:'+ident,))
        return {'disabled':ident,'browser_permission_must_be_removed_on_device':True}
    def routes(self,current,test_channel=None,test_subscription=None):
        c=current['config'];out=[]
        if c['smtp']['enabled'] or test_channel=='smtp':
            if not c['smtp']['host'] or not c['smtp']['sender'] or not c['smtp']['recipients']:raise ValueError('Configure email before sending a test')
            for recipient in c['smtp']['recipients']:out.append(('smtp','smtp:'+hashlib.sha256(recipient.encode()).hexdigest(),current['revision'],recipient))
        if c['push']['enabled'] or test_channel=='push':
            if not c['push']['contact']:raise ValueError('Configure the Web Push contact before sending a test')
            for ident,row in self.ctx.state.setting(SUBS,{}).items():
                if row['enabled'] and not row.get('expired') and (test_channel!='push' or ident==test_subscription):out.append(('push','push:'+ident,current['revision']+':'+row['revision'],ident))
        if test_channel:return [r for r in out if r[0]==test_channel]
        return out
    def queue(self,event,routes,test=False):
        message=json.dumps({'title':'FreeQNAP health notification','body':event['title'][:200],'kind':event['kind'],'event_id':event['id']})
        with self.ctx.state.connect() as db:
            for channel,target,revision,destination in routes:
                if channel=='push' and not test and event['id']<=self.ctx.state.setting(SUBS,{}).get(destination,{}).get('after_event_id',0):continue
                db.execute('INSERT OR IGNORE INTO notification_outbox(id,event_id,target,revision,channel,message,status,created,next_attempt,test) VALUES(?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),event['id'],target,revision,channel,message,'pending',time.time(),time.time(),int(test)))
    def test(self,request):
        if request.get('confirmation')!='SEND TEST NOTIFICATION' or request.get('channel') not in ('smtp','push'):raise ValueError('Explicitly confirm SEND TEST NOTIFICATION')
        with self.lock:
            current=self.current();routes=self.routes(current,request['channel'],request.get('subscription_id'))
            if not routes:raise ValueError('No opted-in destination selected for this test')
            now=time.time()
            with self.ctx.state.connect() as db:
                cur=db.execute('INSERT INTO health_events(alert_id,kind,severity,title,created) VALUES(?,?,?,?,?)',('test-'+secrets.token_hex(16),'test','info','Explicitly requested FreeQNAP test notification',now));ident=cur.lastrowid
            self.queue({'id':ident,'title':'Explicitly requested FreeQNAP test notification','kind':'test'},routes,True)
        return {'queued_destinations':len(routes),'delivered':False}
    def send_smtp(self,current,destination,message):
        c=current['config']['smtp'];context=ssl.create_default_context(cadata=c['ca_certificate'] or None);context.verify_flags|=ssl.VERIFY_X509_STRICT;context.minimum_version=ssl.TLSVersion.TLSv1_2
        client=smtplib.SMTP_SSL(c['host'],c['port'],timeout=10,context=context) if c['protocol']=='tls' else smtplib.SMTP(c['host'],c['port'],timeout=10)
        try:
            client.ehlo()
            if c['protocol']=='starttls':client.starttls(context=context);client.ehlo()
            if c['username']:
                file=self.ctx.directory/'secrets'/current['credential_file']
                if file.is_symlink() or file.stat().st_size>4096:raise ValueError('Invalid SMTP credential')
                client.login(c['username'],json.loads(file.read_text())['password'])
            msg=EmailMessage();msg['From']=c['sender'];msg['To']=destination;msg['Subject']=message['title'];msg['Date']=formatdate(localtime=False);msg['Message-ID']='<freeqnap-'+message['notification_id']+'@localhost>';msg.set_content(message['body']+'\n\nOpen your trusted FreeQNAP dashboard to review the incident. SMTP acceptance does not prove inbox delivery.\n')
            if client.send_message(msg,from_addr=c['sender'],to_addrs=[destination]):raise ValueError('SMTP recipient was refused')
            return 'smtp-accepted'
        finally:
            try:client.quit()
            except (OSError,smtplib.SMTPException):client.close()
    def send_push(self,current,destination,message):
        row=self.ctx.state.setting(SUBS,{})[destination];key,_=push.vapid_key(self.ctx.directory/'secrets')
        return push.send(key,row['subscription'],'mailto:'+current['config']['push']['contact'],message)
    def reconcile_sending(self):
        with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='retrying',last_error='Interrupted send; acceptance is ambiguous and a retry may duplicate it',next_attempt=? WHERE status='sending'",(time.time(),))
    def tick(self,now=None):
        if not self.lock.acquire(blocking=False):return
        try:
            explicit_clock=now is not None;now=time.time() if now is None else now;current=self.current();routes=self.routes(current);active={r[1]:r for r in routes}
            cursor=max(self.ctx.state.setting('notification_cursor:'+current['revision'],0),current.get('after_event_id',0))
            if routes:
                with self.ctx.state.connect() as db:events=[dict(r) for r in db.execute("SELECT e.id,e.kind,e.title,e.severity,a.scope FROM health_events e LEFT JOIN health_alerts a ON a.id=e.alert_id WHERE e.id>? AND kind IN ('opened','escalated','resolved') ORDER BY e.id LIMIT 128",(cursor,))]
                for event in events:self.queue(event,AlertRules(self.ctx).routes(event,routes))
                if events:self.ctx.state.set('notification_cursor:'+current['revision'],events[-1]['id'])
            if not explicit_clock:now=time.time()
            # Explicit tests may run while routine sending is disabled.
            with self.ctx.state.connect() as db:row=db.execute("SELECT * FROM notification_outbox WHERE status IN ('pending','retrying') AND next_attempt<=? ORDER BY next_attempt,created,id LIMIT 1",(now,)).fetchone()
            if row is None:return
            row=dict(row);matched=active.get(row['target'])
            if row['test']:
                tests=self.routes(current,row['channel'],row['target'][5:] if row['channel']=='push' else None);matched=next((r for r in tests if r[1]==row['target']),None)
            if not matched or matched[2]!=row['revision']:
                with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='needs-review',last_error='Destination disabled or changed; retained for review' WHERE id=?",(row['id'],))
                return
            with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='sending',attempts=attempts+1 WHERE id=?",(row['id'],))
            try:
                result=(self.smtp_sender if row['channel']=='smtp' else self.push_sender)(current,matched[3],{**json.loads(row['message']),'notification_id':row['id']})
                if result=='expired':
                    if row['channel']=='push':
                        subs=self.ctx.state.setting(SUBS,{});subs[matched[3]]['expired']=True;self.ctx.state.set(SUBS,subs)
                    with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='needs-review',last_error='Push subscription expired; re-enroll this device. Item retained.' WHERE id=?",(row['id'],))
                elif result in ('smtp-accepted','relay-accepted'):
                    with self.ctx.state.connect() as db:db.execute('UPDATE notification_outbox SET status=?,accepted_at=?,last_error=NULL WHERE id=?',(result,now,row['id']))
                else:raise ValueError('No positive transport acceptance')
            except Exception:
                delay=min(3600,30*2**min(row['attempts'],7))
                with self.ctx.state.connect() as db:db.execute("UPDATE notification_outbox SET status='retrying',next_attempt=?,last_error='Send failed or acceptance was ambiguous; retained for retry. Possible duplicate delivery is not excluded.' WHERE id=?",(now+delay,row['id']))
        finally:self.lock.release()

    def retry_plan(self,request):
        ident=request.get('id')
        with self.ctx.state.connect() as db:row=db.execute('SELECT * FROM notification_outbox WHERE id=?',(ident,)).fetchone()
        if row is None or row['status'] not in ('retrying','needs-review'):raise ValueError('Choose a retained unsuccessful notification')
        routes=self.routes(self.current());target=next((r for r in routes if r[1]==row['target']),None)
        if not target:raise ValueError('The original destination must be enabled and valid before retry review; notifications are never silently retargeted')
        return self.ctx.plan('notification-retry',{'id':ident,'before_status':row['status'],'attempts':row['attempts'],'target':row['target'],'route_revision':target[2],'channel':row['channel'],'destination':target[3],'original_created_at':row['created'],'review':'Replay this retained, possibly old health notification to its original currently enabled destination. It may duplicate an ambiguous earlier acceptance. No other notification or incident is replayed.'},'RETRY NOTIFICATION '+ident)
    def retry(self,request):
        with self.lock,self.ctx.lock():
            path,plan=self.ctx.reviewed(request,'notification-retry');b=plan['body'];target=next((r for r in self.routes(self.current()) if r[1]==b['target']),None)
            if not target or target[2]!=b['route_revision']:raise ValueError('Notification destination changed after review')
            with self.ctx.state.connect() as db:
                row=db.execute('SELECT status,attempts FROM notification_outbox WHERE id=?',(b['id'],)).fetchone()
                if row is None or row['status']!=b['before_status'] or row['attempts']!=b['attempts']:raise ValueError('Notification changed after review')
                self.ctx.consume(path,plan);db.execute("UPDATE notification_outbox SET revision=?,status='pending',next_attempt=?,last_error='Explicitly reviewed replay; duplicate acceptance remains possible' WHERE id=?",(target[2],time.time(),b['id']))
        return {'queued':b['id'],'delivered':False}
    def discard(self,request):
        ident=request.get('id')
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident) or request.get('confirmation')!='DISCARD NOTIFICATION '+ident:raise ValueError('Type DISCARD NOTIFICATION followed by the exact ID')
        with self.lock,self.ctx.state.connect() as db:
            row=db.execute('SELECT status FROM notification_outbox WHERE id=?',(ident,)).fetchone()
            if row is None or row['status'] not in ('pending','retrying','needs-review'):raise ValueError('Only an unsuccessful retained notification can be discarded')
            db.execute("UPDATE notification_outbox SET status='operator-discarded',last_error='Explicitly reconciled by administrator' WHERE id=?",(ident,))
        return {'discarded':ident,'incident_unchanged':True}

    def health(self):
        from .health import fault
        with self.ctx.state.connect() as db:
            retries=db.execute("SELECT count(*) FROM notification_outbox WHERE status='retrying'").fetchone()[0]
            review=db.execute("SELECT count(*) FROM notification_outbox WHERE status='needs-review'").fetchone()[0]
        out=[]
        if retries:out.append(fault('retrying','warning','Outbound notifications are failing or awaiting retry',{'retained_sends':retries}))
        if review:out.append(fault('review','warning','Retained notifications need operator review',{'retained_sends':review}))
        return out
