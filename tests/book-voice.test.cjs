const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/myradio.js','utf8');
test('voice preferences have safe bounds and defaults',()=>{const c=vm.createContext({});vm.runInContext(source,c);const settings=value=>JSON.parse(vm.runInContext('JSON.stringify(bookVoiceSettings('+JSON.stringify(value)+'))',c));assert.deepEqual(settings({}),{voice:'',rate:1,pitch:1});assert.equal(settings({rate:99,pitch:-1}).rate,2);assert.equal(settings({rate:99,pitch:-1}).pitch,.5);assert.equal(settings({rate:'bad'}).rate,1);});
test('book reader passes selected local voice, speed and pitch to speech',async()=>{
 const nodes=[],buttons=[],spoken=[],store=new Map();
 const voices=[{voiceURI:'local-a',name:'A',lang:'en-US',localService:true},{voiceURI:'local-b',name:'B',lang:'en-CA',localService:true},{voiceURI:'remote',name:'Remote',lang:'en-US',localService:false}];
 const speech={getVoices:()=>voices,addEventListener(){},cancel(){},speak:u=>spoken.push(u)};
 const c=vm.createContext({window:{speechSynthesis:speech},speechSynthesis:speech,SpeechSynthesisUtterance:function(t){this.text=t;},localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},document:{body:{append(){}}},nas:async op=>op==='myradio.book-text'?{text:'A local reading test.',offset:0,total_characters:21,next_offset:null,chapters:[]}:{},message:()=>{},el:(tag,text,attrs={})=>{const n={tag,text,attrs,value:'',options:[],style:{},append(){},addEventListener(){},showModal(){},close(){},remove(){}};nodes.push(n);return n;},choices:(n,list)=>{n.options=list;n.value=list[0]?.value||'';},action:(label,fn)=>{buttons.push({label,fn});return {};}});
 vm.runInContext(source,c);await vm.runInContext("radioReadBook({id:'test',metadata:{title:'Test'}})",c);
 const select=nodes.find(n=>n.attrs['aria-label']==='Local reading voice'),rate=nodes.find(n=>n.attrs['aria-label']==='Reading speed'),pitch=nodes.find(n=>n.attrs['aria-label']==='Voice pitch');
 assert.equal(select.options.length,2);select.value='local-b';rate.value='1.6';pitch.value='.8';select.onchange();await buttons.find(b=>b.label==='▶ Read aloud').fn();assert.equal(spoken[0].voice.voiceURI,'local-b');assert.equal(spoken[0].rate,1.6);assert.equal(spoken[0].pitch,.8);assert.equal(JSON.parse(store.get('freeqnap-book-voice')).voice,'local-b');
});
