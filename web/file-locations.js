(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.FreeQNAPLocations=value;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 function build({shares=[],pools=[],sessions=[],devices=[]}={}){
  const rows=[];
  for(const s of shares.filter(s=>s.enabled!==false))rows.push({value:s.name,label:'Shared folder · '+s.name+' — '+s.pool,kind:'share',id:s.name,readOnly:!!s.read_only});
  for(const p of pools)rows.push({value:'pool:'+p.name,label:(p.kind==='usb'?'USB volume':'NAS volume')+' · '+p.name+' — '+(p.mounted?(p.read_only?'read-only':'read/write'):p.encrypted?'locked':'offline'),kind:'pool',id:p.name,readOnly:!!p.read_only,disabled:!p.mounted});
  for(const s of sessions.filter(s=>s.active))rows.push({value:'foreign:'+s.id,label:'Unlocked '+s.format.toUpperCase()+' · '+s.source+' — read-only',kind:'foreign',id:s.id,readOnly:true});
  for(const d of devices){const model=d.usb?.product||d.disk?.model||'USB drive',tail=d.usb?.identity?.serial?.slice(-6)||'',active=sessions.some(s=>s.active&&s.source.startsWith(d.disk?.path||'!'));
   rows.push({value:'attached:'+d.id,label:'Attached · '+model+(tail?' …'+tail:'')+' — '+(active?'unlocked above':'manage/unlock in USB storage'),kind:'attached',readOnly:true,disabled:true});}
  return rows;
 }
 function folders(path,entries=[]){const rows=[{value:'',label:'/'}],seen=new Set(['']);let current='';for(const part of path.split('/').filter(Boolean)){current=[current,part].filter(Boolean).join('/');seen.add(current);rows.push({value:current,label:'/'+current});}for(const e of entries.filter(e=>e.directory&&!e.symlink)){const value=[path,e.name].filter(Boolean).join('/');if(!seen.has(value)){seen.add(value);rows.push({value,label:'/'+value});}}return rows;}
 return {build,folders};
});
