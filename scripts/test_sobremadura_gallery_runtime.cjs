// DOM contract test in plain Node. No browser, network, or UI automation.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(process.argv[2]);
const elements=new Map();let context;
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.attrs={};this.value='';this.checked=false;this.textContent='';this.dataset={};this.hidden=false;}
  append(...nodes){for(const n of nodes){this.children.push(n);if(n.tagName==='script'&&n.src){vm.runInContext(fs.readFileSync(path.join(root,n.src),'utf8'),context);queueMicrotask(()=>n.onload());}}}
  appendChild(n){this.append(n);return n;}
  replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  setAttribute(k,v){this.attrs[k]=String(v);}
  scrollIntoView(){}
}
const document={getElementById(id){if(!elements.has(id))elements.set(id,new Element('div'));return elements.get(id);},createElement:t=>new Element(t),createElementNS:(_,t)=>new Element(t),body:new Element('body'),addEventListener(){}};
const box={document,console,URLSearchParams,queueMicrotask,location:{search:'',pathname:'/index.html'},history:{replaceState(){}}};box.window=box;context=vm.createContext(box);
const el=id=>document.getElementById(id);
el('filter').value='labelled';el('group').value='all';el('showGT').checked=true;el('showPred').checked=true;
const walk=e=>[e,...e.children.flatMap(walk)];
const texts=()=>walk(el('models')).filter(n=>n.tagName==='text').map(n=>n.textContent);
const tick=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  vm.runInContext(fs.readFileSync(path.join(root,'gallery_data.js'),'utf8'),context);
  await vm.runInContext(fs.readFileSync(path.join(root,'gallery.js'),'utf8'),context);
  assert.equal(box.GALLERY_READY,true);assert.equal(el('models').children.length,4);assert.equal(el('photoList').children.length,28);
  assert.match(el('photoTitle').textContent,/113/);assert.ok(texts().some(t=>t.startsWith('GT ')));
  el('showPred').checked=false;el('showPred').onchange();assert.ok(texts().every(t=>t.startsWith('GT ')));
  el('showPred').checked=true;el('showPred').onchange();assert.ok(texts().some(t=>!t.startsWith('GT ')));
  el('showGT').checked=false;el('showGT').onchange();assert.ok(texts().every(t=>!t.startsWith('GT ')));el('showGT').checked=true;
  el('filter').value='unlabelled';el('filter').onchange();await tick();assert.ok(el('photoList').children.length>0);
  assert.match(el('photoTitle').textContent,/0 etiquetas/);assert.match(el('absence').textContent,/no demuestra ausencia/);
  el('filter').value='unmatched';el('filter').onchange();await tick();assert.ok(el('photoList').children.length>0);
  assert.ok(walk(el('candidateTable')).some(n=>n.textContent==='Sin etiqueta cercana'));
  el('search').value='9999999';el('search').oninput();await tick();assert.match(el('photoTitle').textContent,/No hay fotos/);assert.equal(el('originalLink').hidden,true);
  await el('cases').children[1].onclick();assert.match(el('photoTitle').textContent,/183/);assert.equal(el('seed').value,'20261022');assert.equal(el('photoList').children.length,94);
  const views=walk(el('models')).filter(n=>n.tagName==='svg').map(n=>n.attrs.viewBox);assert.equal(new Set(views).size,1);
  el('fullPhoto').onclick();const viewsFull=walk(el('models')).filter(n=>n.tagName==='svg').map(n=>n.attrs.viewBox);assert.notEqual(views[0],viewsFull[0]);
  el('seed').value='20261024';el('seed').onchange();await tick();assert.ok(box.MODEL_DATA[20261024]);
  el('filter').value='regression';el('search').value='';el('filter').onchange();await tick();
  const shown=el('photoList').children.length;assert.ok(shown>0);
  console.log(JSON.stringify({passed:true,behaviors:['initial four panels','28 labelled photos','ground truth toggle','prediction toggle','unlabelled candidates','unannotated-region candidates','empty search clears stale photo','case changes seed and row','shared crop','reset crop','three seeds','regression filter'],real_photos:94,gt_sobre_photos:28,models:4,seeds_loaded:3,regression_photos_seed24:shown,browser_visual_check:false,method:'Plain Node DOM contract; no browser action'},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
