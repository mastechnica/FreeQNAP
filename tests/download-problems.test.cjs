const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');const app=fs.readFileSync('web/app.js','utf8'),source=app.slice(app.indexOf('function downloadProblemDetails('));
class Node{constructor(tag,text,attrs){this.tag=tag;this.textContent=text;this.attrs=attrs||{};this.children=[];}append(...nodes){this.children.push(...nodes);}}
function draw(job){const c={URL,el:(tag,text,attrs)=>new Node(tag,text,attrs)};vm.createContext(c);vm.runInContext(source,c);const card=new Node('article');c.downloadProblemDetails(card,job);return card;}
test('failed cards show the reason, next step, stopped retry and attempt count',()=>{const card=draw({state:'error',attempts:155,problem:{reason:'File not found at the source',next_step:'Find files again from the original listing.',automatic_retry:false,code:'3'}});const text=card.children[0].children.map(v=>v.textContent).join(' ');assert.match(text,/File not found/);assert.match(text,/Find files again/);assert.match(text,/Automatic retries stopped/);assert.match(text,/155 submission attempts/);});
test('manual retry and manual pause are distinguished from automatic retry',()=>{const problem={reason:'Network',next_step:'Check connection',automatic_retry:true};let card=draw({problem,manual_retry:true});assert.match(card.children[0].children[2].textContent,/Retry requested/);card=draw({problem,desired:'paused'});assert.match(card.children[0].children[2].textContent,/Paused by you/);});
test('original source page links are safe and preserve the actual page URL',()=>{const card=draw({source_page:'https://archive.org/download/fixture'});assert.equal(card.children[0].attrs.href,'https://archive.org/download/fixture');assert.equal(card.children[0].attrs.rel,'noopener noreferrer');assert.equal(draw({source_page:'javascript:alert(1)'}).children.length,0);assert.equal(draw({source_page:'https://user:pass@example.org/'}).children.length,0);});
function queueFixture(jobs,filter='all'){
 const calls=[],out=new Node('div');Node.prototype.replaceChildren=function(...nodes){this.children=nodes;};Node.prototype.setAttribute=function(k,v){this.attrs[k]=v;};
 const c={URL,demo:false,downloadOffset:0,downloadFilter:filter,currentUser:{id:'a'},state:{nas:{downloads:{jobs,filter}}},$:id=>id==='download-jobs'?out:null,canPersonal:()=>false,el:(tag,text,attrs)=>new Node(tag,text,attrs),size:String,stat:(label,value)=>new Node('stat',label+value),empty:(node,text)=>node.append(new Node('p',text)),action:(label,fn)=>{const n=new Node('button',label);n.click=fn;return n;},nas:async(...args)=>calls.push(args),refresh:async()=>{},confirm:()=>true};vm.createContext(c);vm.runInContext(app.slice(app.indexOf('function downloadView('),app.indexOf('function dlnaOptions('))+source,c);c.renderDownloadJobs();const all=[];function walk(n){all.push(n);for(const child of n.children)walk(child);}walk(out);return {calls,all};
}
test('failed queue cards provide a working explicit retry action',async()=>{const f=queueFixture([{id:'failed',actor:'user:a',label:'Missing.zip',state:'error',problem:{reason:'File not found',next_step:'Find files again',automatic_retry:false}}]);const retry=f.all.find(n=>n.tag==='button'&&n.textContent==='Retry now');assert.ok(retry);await retry.click();assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[['downloads.control',{id:'failed',action:'resume'}]]);});
test('attention filter includes save failures and hides unsafe damaged-resume actions',()=>{const f=queueFixture([{id:'damaged',label:'Partial',state:'error',recovery_required:true},{id:'save',label:'Complete',state:'complete',delivery:{state:'needs-attention',message:'Destination unavailable'}}],'error');assert.equal(f.all.filter(n=>n.attrs.class==='download-card').length,2);assert.equal(f.all.filter(n=>n.tag==='button'&&['Retry now','Resume'].includes(n.textContent)).length,0);});
test('Next page requests the matching queue page and renders its records',async()=>{
 const out=new Node('section'),retained=new Node('section'),calls=[];
 const first={offset:0,filter:'all',jobs:[],page_size:50,matching:513,total_jobs:513},second={...first,offset:50,jobs:[{id:'later',label:'Later file',state:'paused',desired:'running'}]};
 const c={URL,demo:false,currentUser:{},state:{nas:{downloads:first}},$:id=>id==='download-jobs'?out:retained,
  routeName:()=> 'downloads',canPersonal:()=>false,el:(tag,text,attrs)=>new Node(tag,text,attrs),size:String,
  stat:(name,value)=>new Node('stat',name+value),empty:()=>{},action:(text,click)=>Object.assign(new Node('button',text),{click}),
  nas:async(method,payload)=>{calls.push([method,payload]);return second;}};
 vm.createContext(c);vm.runInContext(app.slice(app.indexOf("let downloadFilter="),app.indexOf('function dlnaOptions('))+source,c);
 c.renderDownloadJobs();const nodes=node=>[node,...node.children.flatMap(nodes)];
 await nodes(out).find(n=>n.textContent==='Next page').click();
 assert.deepEqual(JSON.parse(JSON.stringify(calls)),[['downloads.status',{offset:50,filter:'all'}]]);
 assert.ok(nodes(out).some(n=>n.textContent==='Later file'));
 assert.ok(nodes(out).some(n=>n.textContent==='Page 2 of 11'));
});
