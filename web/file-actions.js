"use strict";
async function copyMoveTo(pane,mode){
 const paths=selectedPane(pane);if(mode==='move')requirePaneWritable(pane);const source=paneLocation(pane);if(!['share','pool','foreign'].includes(source.kind))throw Error('Choose a mounted source folder.');
 const other=filePanes.find(p=>p.id!==pane.id),picked=await selectNasLocation({title:(mode==='move'?'Move':'Copy')+' '+paths.length+' selected item(s) to…',writable:true,initial:other?{share:other.share,path:other.path}:null});if(!picked)return;
 reviewPlan(await nas('files.transfer-plan',{share:pane.share,paths,target_share:picked.share,target_path:picked.path,mode}),'files.transfer');
}
function chooseDropTransfer(payload,pane,path){return new Promise(resolve=>{const d=el('dialog',null,{class:'file-destination-dialog'}),source=fileLocationRows().find(v=>v.value===payload.share);d.append(el('h2','Move or copy these items?'),el('p',(payload.paths?.length||0)+' item(s) → '+(fileLocationRows().find(v=>v.value===pane.share)?.label||pane.share)+' / '+path),el('p','Copy keeps the originals. Move changes their location; across volumes the originals remain recoverable in Recycle bin.'));const done=mode=>{d.close();d.remove();resolve(mode);},buttons=el('div',null,{class:'actions'}),move=action('Move to this folder',()=>done('move'),false),copy=action('Copy to this folder',()=>done('copy'),false);move.disabled=!source||source.readOnly;buttons.append(move,copy,action('Cancel',()=>done(null),false,true));d.append(buttons);document.body.append(d);d.addEventListener('cancel',e=>{e.preventDefault();done(null);});d.showModal();});}

async function importFolderTo(pane,entry=null){
 let source={share:pane.share,path:[pane.path,entry?.directory?entry.name:''].filter(Boolean).join('/')};

 const destination=await selectNasLocation({title:'Import to… Choose destination folder',writable:true});if(!destination)return;
 if(source.path){reviewPlan(await nas('files.transfer-plan',{share:source.share,paths:[source.path],target_share:destination.share,target_path:destination.path,mode:'copy'}),'files.transfer');return;}
 message('Reading the drive contents and preparing your copy…');
 const listing=await FreeQNAPDesktop.listing(payload=>nas('files.list',payload),{share:source.share,path:'',query:'',offset:0,limit:'all'});
 const entries=listing.entries.filter(v=>!v.symlink),excluded=listing.entries.length-entries.length;
 if(!entries.length)throw Error('This drive has no copyable contents.');
 if(entries.length>10000)throw Error('This drive has more than 10,000 top-level items. Import its folders separately. No copy was started.');
 const plans=[];for(let offset=0;offset<entries.length;offset+=200)plans.push(await nas('files.transfer-plan',{share:source.share,paths:entries.slice(offset,offset+200).map(v=>v.name),target_share:destination.share,target_path:destination.path,mode:'copy'}));
 reviewDriveImport(plans,{source:paneLocation(pane).label||pane.share,destination:destination.label+' / '+(destination.path||''),count:entries.length,excluded});
}
function showPlaceMenu(pane,place,x,y){
 closeFileContext();focusFileWindow(pane);const source={...pane,share:place.value,path:'',selected:new Set()},menu=el('div',null,{class:'file-context-menu',role:'menu','aria-label':'Drive actions'});fileContext=menu;
 for(const [label,fn]of [['Import to…',()=>importFolderTo(source)],['Import folder to My Radio…',()=>importPaneLibrary(source,'radio')],['Import folder to Personal Photos & Videos…',()=>importPaneLibrary(source,'photos')],['Refresh',()=>refreshFileLocations()]])menu.append(action(label,async()=>{closeFileContext();await fn();},false,true));
 document.body.append(menu);menu.style.left=Math.max(8,Math.min(x,window.innerWidth-menu.offsetWidth-8))+'px';menu.style.top=Math.max(8,Math.min(y,window.innerHeight-menu.offsetHeight-8))+'px';menu.querySelector('button')?.focus();
}

function reviewDriveImport(plans,summary){
 reviewPlan(plans[0],'files.transfer');currentPlan.transferPlans=plans;currentPlan.submitted=[];
 $('review-title').textContent='Import entire drive contents';const detail=$('review-detail');detail.replaceChildren(el('p','From: '+summary.source),el('p','To: '+summary.destination),el('p',summary.count+' top-level files and folders, including their contents. '+plans.length+' verified copy job(s) will be queued.'),el('p','Source files stay on the drive. Existing destination files are never overwritten. FreeQNAP’s private system folders are excluded; unreadable or unsupported contents stop the affected job and remain on the source.'));
 if(summary.excluded)detail.append(el('p',summary.excluded+' symbolic link(s) excluded; links are not followed.',{class:'notice warning'}));
}
async function submitDriveImport(review,invoke){
 if(review.submissionFailed||review.submitted.length)throw Error('This submission has already started. Check Files and Activity before preparing another import.');
 let pending=false;try{for(const plan of review.transferPlans){if(review.cancelRequested)throw Error('Further submissions canceled. Already queued copies continue.');pending=true;const result=await invoke('files.transfer',{plan_id:plan.id,digest:plan.digest,confirmation:plan.confirmation});if(!result?.job_id)throw Error('No job receipt returned');review.submitted.push(result.job_id);pending=false;}return {job_id:review.submitted[0],job_ids:[...review.submitted]};}
 catch(error){review.submissionFailed=true;throw Error('Submission stopped after '+review.submitted.length+' confirmed job(s). '+(pending?'The last request may have reached the NAS. ':'')+'Check Files and Activity before starting another import. No automatic retry was made. '+error.message);}
}
