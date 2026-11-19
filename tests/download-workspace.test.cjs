const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
const browser=process.env.FREEQNAP_TEST_CHROMIUM;
for(const [width,member] of [[1280,false],[390,true]]){
 test('compact Downloads workspace at '+width+'px',{skip:!browser},()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'freeqnap-download-ui-'));
  try{
   const app=fs.readFileSync('web/app.js','utf8'),helpers=['el','size','field','panel','choices','action','submit','message','clearMessages','empty'];
   const source=helpers.map(name=>app.split('\n').find(line=>line.startsWith('function '+name+'('))).join('\n')+
    '\n'+app.slice(app.indexOf("let downloadsTab="),app.indexOf('function dlnaOptions('))+
    '\n'+app.slice(app.indexOf('function downloadFileInfo('));
   const fixture=`
    const $=id=>document.getElementById(id),demo=false,nasAvailable=true,currentUser={id:'fixture'};
    const canPersonal=()=>true,familyMember=()=>${member},state={nas:{downloads:{settings:{pool:'fixture',options:{}}},pools:[]}};
    const jobs=Array.from({length:523},(_,i)=>({id:String(i),label:'File '+i,category:i===0?'active':i===500?'complete':'waiting',state:i===0?'active':i===500?'complete':'paused',desired:'running'}));
    async function nas(method,query){
     if(method!=='downloads.status')throw Error('Unexpected operation '+method);
     const t=jobs.filter(j=>(query.filter==='all'||j.category===query.filter)&&j.label.toLowerCase().includes(query.search.toLowerCase())),offset=query.offset||0;
     return {items:t.slice(offset,offset+50),matching:t.length,next_offset:offset+50<t.length?offset+50:null,counts:{active:1,complete:1,waiting:521}};
    }
   `;
   const checks=`
    function check(condition,message){if(!condition)throw Error(message);}
    const pause=(ms=10)=>new Promise(resolve=>setTimeout(resolve,ms));
    (async()=>{
     downloads($('workspace'));await pause();
     const queue=$('download-jobs'),outer=queue.querySelector('details'),rows=queue.querySelector('.download-rows'),direct=$('download-urls'),mode=$('download-source-mode');
     check(!outer.open&&!rows.children.length&&queue.textContent.includes('521 waiting'),'initial collapsed counts');
     check($('downloads-queue-panel').firstChild.querySelector('h2').textContent==='Add downloads','add panel first');
     direct.value='https://example.org/file';mode.value='linked';mode.dispatchEvent(new Event('change'));
     check(direct.closest('[hidden]')&&document.querySelector('input[type=url]').offsetWidth>0,'source mode');
     $('downloads-settings-tab').click();
     check($('downloads-queue-panel').hidden&&$('downloads-settings-panel').innerText.includes('Default save folder')&&$('downloads-settings-panel').innerText.includes('My download limits'),'settings grouped');
     check($('downloads-settings-panel').innerText.includes('NAS-wide download limits')===!${member},'administrator settings visibility');
     $('downloads-queue-tab').click();mode.value='direct';mode.dispatchEvent(new Event('change'));check(direct.value.includes('example.org'),'draft preserved');
     outer.open=true;await pause(100);check(rows.children.length===50&&rows.scrollHeight>rows.clientHeight,'bounded rows');
     const initialHeight=document.documentElement.scrollHeight;
     queue.querySelector('button.quiet').click();await pause(100);check(rows.children.length===100,'show more');
     check(document.documentElement.scrollHeight<=initialHeight+5,'list did not grow the page');
     rows.firstChild.querySelector('details').open=true;await pause();await queue.refreshQueue();
     check(rows.firstChild.querySelector('details').open&&rows.firstChild.innerText.includes('Show files'),'expanded row preserved during refresh');
     const search=queue.querySelector('[type=search]');search.value='File 500';search.dispatchEvent(new Event('input'));await pause(240);
     check(rows.children.length===1&&rows.innerText.includes('Finished'),'search beyond loaded window');
     check(document.documentElement.scrollWidth<=window.innerWidth,'fits viewport width');
     $('result').textContent='PASS';
    })().catch(error=>{$('result').textContent='FAIL '+error.message;});
   `;
   fs.copyFileSync('web/style.css',path.join(dir,'style.css'));
   fs.writeFileSync(path.join(dir,'index.html'),'<meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="style.css"><div id="workspace"></div><div id="message" hidden></div><div id="error" hidden></div><pre id="result">pending</pre><script>'+fixture+source+checks+'</script>');
   const result=spawnSync(browser,['--headless','--disable-gpu','--disable-background-networking','--no-first-run','--user-data-dir='+path.join(dir,'profile'),'--window-size='+width+',800','--virtual-time-budget=4500','--dump-dom','file://'+path.join(dir,'index.html')],{encoding:'utf8',timeout:30000,maxBuffer:4*1024*1024});
   assert.equal(result.status,0,result.error?.message||result.stderr.slice(-400));
   assert.equal(/<pre id="result">([^<]*)/.exec(result.stdout)?.[1],'PASS');
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
 });
}
