const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');const app=fs.readFileSync('web/app.js','utf8'),source=app.slice(app.indexOf('function downloadProblemDetails('));
class Node{constructor(tag,text,attrs){this.tag=tag;this.textContent=text;this.attrs=attrs||{};this.children=[];}append(...nodes){this.children.push(...nodes);}}
function draw(job){const c={URL,el:(tag,text,attrs)=>new Node(tag,text,attrs)};vm.createContext(c);vm.runInContext(source,c);const card=new Node('article');c.downloadProblemDetails(card,job);return card;}
test('failed cards show the reason, next step, stopped retry and attempt count',()=>{const card=draw({state:'error',attempts:155,problem:{reason:'File not found at the source',next_step:'Find files again from the original listing.',automatic_retry:false,code:'3'}});const text=card.children[0].children.map(v=>v.textContent).join(' ');assert.match(text,/File not found/);assert.match(text,/Find files again/);assert.match(text,/Automatic retries stopped/);assert.match(text,/155 submission attempts/);});
test('manual retry and manual pause are distinguished from automatic retry',()=>{const problem={reason:'Network',next_step:'Check connection',automatic_retry:true};let card=draw({problem,manual_retry:true});assert.match(card.children[0].children[2].textContent,/Retry requested/);card=draw({problem,desired:'paused'});assert.match(card.children[0].children[2].textContent,/Paused by you/);});
test('original source page links are safe and preserve the actual page URL',()=>{const card=draw({source_page:'https://archive.org/download/fixture'});assert.equal(card.children[0].attrs.href,'https://archive.org/download/fixture');assert.equal(card.children[0].attrs.rel,'noopener noreferrer');assert.equal(draw({source_page:'javascript:alert(1)'}).children.length,0);assert.equal(draw({source_page:'https://user:pass@example.org/'}).children.length,0);});
function detailFixture(job){
 const calls=[],card=new Node('div');
 const c={URL,currentUser:{id:'a'},canPersonal:()=>false,el:(tag,text,attrs)=>new Node(tag,text,attrs),size:String,
  action:(text,click)=>Object.assign(new Node('button',text),{click}),nas:async(...args)=>calls.push(args),refresh:async()=>{}};
 vm.createContext(c);vm.runInContext(app.slice(app.indexOf('function downloadView('),app.indexOf('function dlnaOptions('))+source,c);
 c.downloadRowDetails(card,job);const nodes=node=>[node,...node.children.flatMap(nodes)];
 return {calls,buttons:nodes(card).filter(n=>n.tag==='button')};
}
test('expanded failed row offers an explicit retry',async()=>{
 const f=detailFixture({id:'failed',state:'error',actor:'user:a'});
 await f.buttons.find(b=>b.textContent==='Retry now').click();
 assert.deepEqual(JSON.parse(JSON.stringify(f.calls)),[['downloads.control',{id:'failed',action:'resume'}]]);
});
test('retained files can be browsed without queue controls and damaged data cannot be retried',()=>{
 const kept=detailFixture({id:'kept',retained:true,state:'paused'});
 assert.deepEqual(kept.buttons.map(b=>b.textContent),['Show files']);
 const damaged=detailFixture({id:'damaged',state:'error',recovery_required:true});
 assert.ok(!damaged.buttons.some(b=>['Resume','Retry now'].includes(b.textContent)));
});
