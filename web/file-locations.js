(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.FreeQNAPLocations=value;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function build({shares=[],pools=[],sessions=[],devices=[]}={}){
  const rows=[];
  for(const s of shares.filter(s=>s.enabled!==false))rows.push({value:s.name,label:({'my-photos':'Personal Photos import folder','my-radio':'My Radio import folder','my-files':'Personal files'}[s.name]||(s.personal_root?'Assigned folder · ':'Shared folder · ')+(s.label||s.name))+' — '+s.pool,kind:'share',id:s.name,readOnly:!!s.read_only});
  for(const p of pools)rows.push({value:'pool:'+p.name,label:(p.kind==='usb'?(p.encrypted?'Private encrypted USB volume':'Shared USB volume'):'NAS volume')+' · '+p.name+' — '+(p.mounted?(p.read_only?'read-only':'read/write'):p.encrypted?'locked':'offline'),kind:'pool',id:p.name,readOnly:!!p.read_only,disabled:!p.mounted||p.content_access===false});
  for(const s of sessions.filter(s=>s.active&&s.content_access!==false))rows.push({value:'foreign:'+s.id,label:(['ntfs','exfat','vfat'].includes(s.format)?'Shared mounted ':'Private unlocked ')+s.format.toUpperCase()+' · '+s.source+' — read-only',kind:'foreign',id:s.id,readOnly:true});
  for(const d of devices){const paths=new Set();function visit(n){if(n?.path)paths.add(n.path);for(const child of n?.children||[])visit(child);}visit(d.disk);if(pools.some(p=>p.external?.id===d.id)||sessions.some(s=>s.active&&s.content_access!==false&&paths.has(s.source)))continue;const model=d.usb?.product||d.disk?.model||'USB drive',tail=d.usb?.identity?.serial?.slice(-6)||'',active=sessions.some(s=>s.active&&s.source.startsWith(d.disk?.path||'!'));
   rows.push({value:'attached:'+d.id,label:'Attached · '+model+(tail?' …'+tail:'')+' — '+(active?'unlocked above':'manage/unlock in USB storage'),kind:'attached',readOnly:true,disabled:true});}
  return rows;
 }
 function folders(path,entries=[]){const rows=[{value:'',label:'/'}],seen=new Set(['']);let current='';for(const part of path.split('/').filter(Boolean)){current=[current,part].filter(Boolean).join('/');seen.add(current);rows.push({value:current,label:'/'+current});}for(const e of entries.filter(e=>e.directory&&!e.symlink)){const value=[path,e.name].filter(Boolean).join('/');if(!seen.has(value)){seen.add(value);rows.push({value,label:'/'+value});}}return rows;}
 return {build,folders};
});
