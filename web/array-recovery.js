'use strict';
function arrayRecoveryPanel(w){
 const box=panel('Recover an interrupted array','Inspect safely first. Bringing an array back read-only and allowing rebuild writes are separate, confirmed steps.');
 const out=el('div',null,{class:'array-recovery-cards'});box.append(out);w.append(box);
 async function load(){
  if(demo){empty(out,'Guided recovery is available on the NAS. The preview cannot inspect disks.');return;}
  const result=await api('/api/nas/raid.recovery-status',{});out.replaceChildren();
  for(const group of result.arrays){
   const a=el('article',null,{class:'array-recovery-card '+(['stopped','needs-attention','degraded'].includes(group.state)?'critical':group.state==='online'?'good':'watch')});
   const labels={stopped:'Stopped · recovery available','read-only':'Safe inspection · read-only',rebuilding:'Rebuilding · keep the NAS running',degraded:'Reduced protection',online:'Online', 'needs-attention':'Needs inspection'};
   a.append(el('h3',group.name),el('span',labels[group.state]||group.state,{class:'badge'}));
   for(const volume of group.volumes)a.append(el('p',volume.name+' · '+(volume.mounted?'Available':'Not mounted'),{class:volume.mounted?'status-good':'muted'}));
   if(group.array?.sync_progress){const n=group.array.sync_progress.percent;a.append(el('progress',null,{max:100,value:n,'aria-label':'Rebuild progress'}),el('small',n.toFixed(1)+'% rebuilt'));}
   if(group.error)a.append(el('p',group.error,{class:'notice error'}));
   const buttons=el('div',null,{class:'actions'});
   for(const mode of group.available_actions){
    if(mode==='mount'&&group.volumes.every(v=>v.mounted))continue;
    const prefix={readonly:'inspect',resume:'resume',mount:'mount'}[mode],label={readonly:'Recover read-only…',resume:'Resume rebuild & mount…',mount:'Bring volumes online…'}[mode];
    buttons.append(action(label,async()=>{const plan=await api('/api/nas/raid.'+prefix+'-plan',{pool:group.pool,mount_volumes:true});reviewPlan(plan,'raid.'+prefix+'-apply');},false));
   }
   a.append(buttons);
   const operation=group.last_operation;
   if(operation){a.append(el('small','Last recovery: '+operation.phase.replaceAll('-',' ')));if(operation.error)a.append(el('p',operation.error,{class:'notice warning'}));if(operation.backup)a.append(el('a','Download recovery metadata backup',{href:'/api/raid-backup?id='+encodeURIComponent(operation.backup.id),class:'button quiet',download:''}));}
   out.append(a);
  }
  if(!result.arrays.length)empty(out,'No registered internal data array. Add existing storage or create a reviewed layout below.');
 }
 const backups=el('details');backups.append(el('summary','Recovery metadata backups'));const list=el('div');backups.append(list,action('Show saved backups',async()=>{const value=await api('/api/nas/raid.backups',{});list.replaceChildren(el('p',value.retention,{class:'note'}));for(const v of value.items){const row=el('article');row.append(el('strong',v.group+' · '+humanTime(v.created_at)),el('a','Download metadata backup',{href:'/api/raid-backup?id='+v.id,class:'button quiet',download:''}));if(!v.protected)row.append(action('Delete older backup…',async()=>{if(!confirm('Have you downloaded and independently saved this older metadata backup? The latest backup will be kept.'))return;const phrase=prompt('Type DELETE METADATA '+v.id);if(!phrase)return;await api('/api/nas/raid.backup-remove',{id:v.id,backup_copied:true,confirmation:phrase});message('Older metadata backup deleted; latest backup retained.');},false,true));list.append(row);}},false,true));box.append(backups);
 box.append(action('Refresh recovery status',load,false,true));load().catch(e=>{out.replaceChildren(el('p',e.message,{class:'notice warning'}));});
}
function describeArrayRecovery(plan){
 const b=plan.body,s=b.snapshot,out=$('review-detail');out.replaceChildren();
 const names={readonly:'Recover this array read-only?',resume:'Resume rebuilding and restore access?',mount:'Bring existing volumes online?'};
 $('review-title').textContent=names[b.mode];
 out.append(el('p',b.mode==='readonly'?'A verified metadata backup has been saved. The NAS will open only this existing data array read-only. It will not mount your files or start rebuilding.':'The NAS will use this existing array and its recorded original members. Mounting can replay the filesystem journal; a large-volume check may take several minutes.'));
 row(out,'Array',s.group);row(out,'Volumes',s.volumes.map(v=>v.name).join(', '));row(out,'Disk writes',b.writes);
 if(s.checkpoint_sectors!==null)row(out,'Saved rebuild position',Math.floor(s.checkpoint_sectors/s.members[0].metadata.component_sectors*1000)/10+'%');
 const t=table(['Original disk','Member role','Identity']);for(const m of s.members){const r=el('tr');[m.disk.serial,'Bay member '+(m.metadata.role+1),'Verified'].forEach(v=>r.append(el('td',v)));t.body.append(r);}out.append(t.wrap);
 if(s.force_required&&b.mode==='readonly')out.append(el('p','Recovery override: Linux has refused this unclean, incomplete array. Continuing may mark RAID metadata clean to allow read-only inspection; this does not repair or validate parity.',{class:'notice warning'}));
 if(b.metadata_backup){out.append(el('a','Download verified recovery metadata',{href:'/api/raid-backup?id='+encodeURIComponent(b.metadata_backup.id),class:'button',download:''}));const label=el('label',null,{class:'check'}),ack=el('input',null,{type:'checkbox',id:'raid-backup-ack',required:''});label.append(ack,document.createTextNode('I have reviewed the saved metadata backup and understand it is not a backup of my files.'));out.append(label);}
 out.append(el('p',b.risk,{class:'notice warning'}),el('p','Your OS, USB drives and partition layout are excluded. Interrupted steps are retained for inspection and are never automatically repeated.',{class:'note'}));
}
