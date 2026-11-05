/* Small local-only folder-window geometry and selection helpers. */
(function(root){
 'use strict';
 const finite=(n,f)=>Number.isFinite(n)?n:f;
 function fit(box,g={}){const width=Math.max(1,finite(box.width,900)),height=Math.max(1,finite(box.height,680));const w=Math.min(width,Math.max(Math.min(360,width),finite(g.width,640))),h=Math.min(height,Math.max(Math.min(240,height),finite(g.height,500)));return {x:Math.max(0,Math.min(width-w,finite(g.x,18))),y:Math.max(0,Math.min(height-h,finite(g.y,18))),width:w,height:h};}
 function tiles(box,count){if(!count)return [];const columns=box.width<720?1:Math.min(Math.max(1,Math.floor((box.width-10)/370)),Math.ceil(Math.sqrt(count*box.width/box.height))),rows=Math.ceil(count/columns),gap=10,w=(box.width-gap*(columns+1))/columns,h=(box.height-gap*(rows+1))/rows;return Array.from({length:count},(_,i)=>fit(box,{x:gap+(i%columns)*(w+gap),y:gap+Math.floor(i/columns)*(h+gap),width:w,height:h}));}
 function select(names,current,name,{toggle=false,range=false,anchor=null}={}){if(!names.includes(name))return new Set(current);if(range&&names.includes(anchor)){const a=names.indexOf(anchor),b=names.indexOf(name);return new Set(names.slice(Math.min(a,b),Math.max(a,b)+1));}const next=toggle?new Set(current):new Set();if(toggle&&next.has(name))next.delete(name);else next.add(name);return next;}
 function attach(node,bar,pane,desk,focus){let dragging=null;function bounds(){return {width:desk.clientWidth,height:desk.clientHeight};}function apply(g=pane.geometry){pane.geometry=fit(bounds(),g);Object.assign(node.style,{left:pane.geometry.x+'px',top:pane.geometry.y+'px',width:pane.geometry.width+'px',height:pane.geometry.height+'px'});}apply();node.addEventListener('pointerdown',()=>focus(pane),{capture:true});
  function start(event,resize){if(event.button!==0||(!resize&&event.target.closest('button,input,select')))return;event.preventDefault();focus(pane);dragging={x:event.clientX,y:event.clientY,g:{...pane.geometry},resize};event.currentTarget.setPointerCapture(event.pointerId);node.classList.add('window-dragging');}
  function move(event){if(!dragging)return;const dx=event.clientX-dragging.x,dy=event.clientY-dragging.y,g=dragging.g;apply(dragging.resize?{...g,width:g.width+dx,height:g.height+dy}:{...g,x:g.x+dx,y:g.y+dy});}
  function stop(){dragging=null;node.classList.remove('window-dragging');}
  const handle=node.querySelector('.window-resize');for(const target of [bar,handle]){target.addEventListener('pointerdown',e=>start(e,target===handle));target.addEventListener('pointermove',move);target.addEventListener('pointerup',stop);target.addEventListener('pointercancel',stop);target.addEventListener('lostpointercapture',stop);}
  handle.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();apply({...pane.geometry,width:pane.geometry.width+(e.key==='ArrowRight'?24:e.key==='ArrowLeft'?-24:0),height:pane.geometry.height+(e.key==='ArrowDown'?24:e.key==='ArrowUp'?-24:0)});});return {apply};
 }
 function pages(total,offset,size=100){total=Math.max(0,Math.floor(finite(total,0)));size=Math.max(1,Math.floor(finite(size,100)));const count=Math.max(1,Math.ceil(total/size)),current=Math.min(count,Math.max(1,Math.floor(finite(offset,0)/size)+1)),numbers=[...new Set([1,count,...Array.from({length:5},(_,i)=>current+i-2).filter(n=>n>=1&&n<=count)])].sort((a,b)=>a-b),items=[];for(const n of numbers){if(items.length&&n-items[items.length-1]>1)items.push(null);items.push(n);}return {count,current,items,first:0,last:(count-1)*size,previous:Math.max(0,(current-2)*size),next:Math.min((count-1)*size,current*size)};}
 function pageSize(value){return value==='all'?'all':[100,500,1000].includes(Number(value))?Number(value):100;}
 async function listing(fetchPage,request,{current=()=>true,progress=()=>{}}={}){
  if(request.limit!=='all')return fetchPage({...request,limit:pageSize(request.limit)});
  const entries=[],seen=new Set();let offset=0,total=null;
  while(true){const page=await fetchPage({...request,offset,limit:1000});if(!current())return null;
   if(total===null)total=page.total_entries;else if(total!==page.total_entries)throw Error('This folder changed while loading All Files. Refresh to load the current list.');
   if(total>200000)throw Error('This folder exceeds the 200,000-item All Files limit. Use a search filter or a paged view.');
   for(const entry of page.entries){if(seen.has(entry.name))throw Error('This folder changed while loading. Refresh the list.');seen.add(entry.name);entries.push(entry);}
   progress(entries.length,total);if(page.next_offset===null||page.next_offset===undefined)return {...page,entries,total_entries:entries.length,offset:0,limit:'all',next_offset:null,truncated:false};
   if(!Number.isInteger(page.next_offset)||page.next_offset<=offset)throw Error('Folder listing did not advance. Refresh the folder.');offset=page.next_offset;
  }
 }
 const api={fit,tiles,select,attach,pages,pageSize,listing};if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.FreeQNAPDesktop=api;
})(typeof window==='undefined'?globalThis:window);
