'use strict';
const G=window.GALLERY, $=id=>document.getElementById(id), NS='http://www.w3.org/2000/svg';
window.MODEL_DATA=window.MODEL_DATA||{};
const query=new URLSearchParams(location.search);
const state={seed:Number(query.get('seed'))||20261023,id:Number(query.get('row'))||113,focus:null,visible:[]};
if(!G.seeds.includes(state.seed))state.seed=20261023;
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const svgNode=(tag,attrs,text)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs||{}))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
const data=()=>window.MODEL_DATA[state.seed];
const rowData=(model,id)=>data()[model][String(id)];
const above=p=>p[5]>=G.threshold;
const anySobre=row=>G.models.some(m=>rowData(m.id,row.id).predictions.some(p=>p[4]===2&&above(p)));

function loadSeed(seed){
  if(window.MODEL_DATA[seed])return Promise.resolve();
  return new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=`data/seed_${seed}.js`;s.onload=resolve;s.onerror=()=>reject(new Error('No se pudo cargar el archivo de esta semilla.'));document.body.appendChild(s);});
}
function filteredRows(){
  const filter=$('filter').value,group=$('group').value,search=$('search').value.trim().toLowerCase();
  return G.rows.filter(r=>{
    if(group!=='all'&&r.group!==group)return false;
    if(search&&!(`${r.id} ${r.file}`.toLowerCase().includes(search)))return false;
    if(filter==='labelled')return r.gt_sobre>0;
    if(filter==='unlabelled')return r.gt_sobre===0&&anySobre(r);
    if(filter==='unmatched')return G.models.some(m=>rowData(m.id,r.id).candidate_regions.some(p=>p.kind==='no_nearby_annotation'));
    if(filter==='regression')return rowData('hybrid',r.id).tp<rowData('classical',r.id).tp;
    if(filter==='gain')return rowData('hybrid',r.id).tp>rowData('classical',r.id).tp;
    return true;
  });
}
function renderList(){
  state.visible=filteredRows();
  $('listCount').textContent=`${state.visible.length} fotos en esta vista · 28 con etiqueta Sobre en todo el test`;
  if(!state.visible.some(r=>r.id===state.id)){state.id=state.visible[0]?.id;state.focus=null;}
  $('photoList').replaceChildren();
  for(const r of state.visible){
    const b=node('button',undefined,'photo-button'+(r.id===state.id?' selected':''));b.type='button';b.setAttribute('aria-label',`Fila ${r.id}, ${r.gt_sobre} etiquetas Sobremadura`);
    const image=document.createElement('img');image.src=r.thumb;image.alt='';image.loading='lazy';
    const text=node('span');text.append(node('strong',`Fila ${r.id}`));
    text.append(node('small',r.gt_sobre?`${r.gt_sobre} etiqueta${r.gt_sobre>1?'s':''} Sobre`:'Sin etiqueta Sobre',r.gt_sobre?'':'zero'));
    const count=G.models.filter(m=>rowData(m.id,r.id).predictions.some(p=>p[4]===2&&above(p))).length;
    text.append(node('small',`Candidatos en ${count}/4 modelos`,'candidate'));b.append(image,text);
    b.onclick=()=>{state.id=r.id;state.focus=null;renderList();renderPhoto();};$('photoList').append(b);
  }
}
function cropBox(row,box){
  if(!box)return[0,0,row.w,row.h];
  const pad=Math.max(30,.65*Math.max(box[2]-box[0],box[3]-box[1]));
  const x=Math.max(0,box[0]-pad),y=Math.max(0,box[1]-pad);
  return[x,y,Math.min(row.w,box[2]+pad)-x,Math.min(row.h,box[3]+pad)-y];
}
function intersects(b,v){return b[2]>=v[0]&&b[0]<=v[0]+v[2]&&b[3]>=v[1]&&b[1]<=v[1]+v[3];}
function overlayLabel(svg,b,text,color,font,v,offset=0,ground=false){
  const width=Math.min(text.length*.57*font,v[2]-.02*font);
  const x=Math.max(v[0]+font*.05,Math.min(b[0],v[0]+v[2]-width-font*.2));
  let y=ground?b[3]-font*.2:b[1]+font*(1.12+offset*1.15);
  y=Math.max(v[1]+font,Math.min(y,v[1]+v[3]-font*.1));
  svg.append(svgNode('rect',{x,y:y-font*.92,width:width+font*.2,height:font*1.1,fill:ground?'#14271f':color,opacity:ground?.9:.88}));
  svg.append(svgNode('text',{x:x+font*.1,y,'font-size':font,'font-family':'system-ui,sans-serif',fill:ground?'white':'#12251e'},text));
}
function makeView(row,model){
  const v=cropBox(row,state.focus),font=Math.max(v[2],v[3])/45;
  const svg=svgNode('svg',{viewBox:v.join(' '),role:'img','aria-label':`Fila ${row.id}, ${model.title}, etiquetas y predicciones`});
  svg.append(svgNode('image',{href:row.image,x:0,y:0,width:row.w,height:row.h}));
  if($('showGT').checked){
    for(const t of row.truth){if(!intersects(t.bbox,v))continue;const b=t.bbox;
      svg.append(svgNode('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'none',stroke:'#10241b','stroke-width':4,'vector-effect':'non-scaling-stroke'}));
      svg.append(svgNode('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'none',stroke:'white','stroke-width':2,'stroke-dasharray':'6 4','vector-effect':'non-scaling-stroke'}));
      overlayLabel(svg,b,`GT ${G.names[t.class_id]}`,null,font,v,0,true);
    }
  }
  const predictions=rowData(model.id,row.id).predictions.filter(p=>{
    if(!$('showPred').checked)return false;
    if($('onlySobre').checked&&p[4]!==2)return false;
    return above(p)||($('lowScores').checked&&p[4]===2);
  }).sort((a,b)=>a[5]-b[5]);
  for(const p of predictions){const b=p.slice(0,4);if(!intersects(b,v))continue;
    const low=!above(p),color=G.class_colors[p[4]];
    const rect=svgNode('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'none',stroke:color,'stroke-width':low?1:2,'stroke-dasharray':low?'3 5':'none',opacity:low?.6:1,'vector-effect':'non-scaling-stroke'});
    rect.append(svgNode('title',{},`${G.names[p[4]]} ${p[5].toFixed(6)}${low?' · bajo umbral':''}`));svg.append(rect);
    overlayLabel(svg,b,`${G.names[p[4]]} ${p[5].toFixed(3)}${low?' ↓':''}`,color,font,v,p[4]);
  }
  return svg;
}
function renderPhoto(){
  const row=G.rows.find(r=>r.id===state.id);
  if(!row){$('photoTitle').textContent='No hay fotos con estos filtros.';$('photoMeta').textContent='';$('absence').textContent='';$('originalLink').hidden=true;$('focusSobre').disabled=true;$('models').replaceChildren(node('p','Prueba otro filtro o búsqueda.','loading'));$('targetTable').replaceChildren();$('candidateTable').replaceChildren();return;}
  $('originalLink').hidden=false;
  $('photoTitle').textContent=`Fila ${row.id} · ${row.gt_sobre} etiqueta${row.gt_sobre===1?'':'s'} Sobremadura`;
  const counts=G.names.map((n,i)=>`${n}: ${row.truth.filter(t=>t.class_id===i).length}`).join(' · ');
  $('photoMeta').textContent=`${row.group} · ${row.w}×${row.h} px · ${counts}${state.focus?' · Recorte compartido entre los cuatro paneles':''}`;
  $('originalLink').href=row.original;$('focusSobre').disabled=!row.gt_sobre;
  $('absence').textContent=row.gt_sobre?'':G.annotation_warning+' Se mantienen visibles las etiquetas de las otras clases.';
  $('thresholdText').textContent=`Umbral común ${G.threshold.toFixed(6)}, fijado en val del control reciente; TP/FP/FN Sobre de la foto completa.`;
  $('models').replaceChildren();
  for(const model of G.models){
    const r=rowData(model.id,row.id),count=r.predictions.filter(p=>p[4]===2&&above(p)).length;
    const card=node('article',undefined,'model-card');card.dataset.model=model.id;
    const head=node('div',undefined,'model-head'),title=node('div',undefined,'model-title');
    title.append(node('h3',model.title),node('span',model.date,'badge'+(model.historical?' history':'')));
    head.append(title,node('p',model.detail));
    const stats=node('div',undefined,'model-stats');stats.append(node('strong',`Sobre: ${count} predicción${count===1?'':'es'}`));
    stats.append(node('span',`TP ${r.tp} · FP ${r.fp} · FN ${r.fn}`));if(!count)stats.append(node('span','Sin detección Sobre al umbral','empty-sobre'));
    head.append(stats);const frame=node('div',undefined,'viewport');frame.append(makeView(row,model));
    card.append(head,frame,node('div',`Semilla ${state.seed} · cajas sólidas: predicciones · discontinuas blancas: etiquetas`,'model-footer'));$('models').append(card);
  }
  renderTargets(row);
  renderCandidateRegions(row);
  try{history.replaceState(null,'',`${location.pathname}?row=${state.id}&seed=${state.seed}`);}catch{}
}
function renderCandidateRegions(row){
  const table=$('candidateTable');table.replaceChildren();const h=node('tr');
  for(const label of ['Modelo','Score Sobre','Relación geométrica con etiquetas','Revisar'])h.append(node('th',label));
  const head=node('thead');head.append(h);table.append(head);const body=node('tbody');let total=0;
  for(const model of G.models)for(const c of rowData(model.id,row.id).candidate_regions){
    total++;const tr=node('tr');tr.append(node('td',model.title),node('td',c.confidence.toFixed(3)));
    const text=c.kind==='no_nearby_annotation'?'Sin etiqueta cercana':c.kind==='partial_overlap'?'Solapamiento parcial con '+G.names[c.nearest_truth_class]:'Solapa etiqueta '+G.names[c.nearest_truth_class];
    const relation=node('td',text);relation.append(node('small',`IoU máximo ${c.max_iou.toFixed(3)} · no adjudica la etiqueta`));tr.append(relation);
    const td=node('td'),button=node('button','Acercar','target-focus');button.onclick=()=>{state.focus=c.bbox;renderPhoto();};td.append(button);tr.append(td);body.append(tr);
  }
  if(!total){const tr=node('tr'),td=node('td','Ningún modelo propone Sobre sobre el umbral en esta foto.');td.colSpan=4;tr.append(td);body.append(tr);}
  table.append(body);$('candidateReview').open=!row.gt_sobre;
}
function renderTargets(row){
  const table=$('targetTable');table.replaceChildren();
  const header=node('tr');header.append(node('th','Etiqueta original'));
  G.models.forEach(m=>header.append(node('th',m.title)));const thead=node('thead');thead.append(header);table.append(thead);
  const body=node('tbody');
  row.truth.forEach((t,index)=>{if(t.class_id!==2)return;const tr=node('tr'),first=node('td');
    const button=node('button',`Sobre ${index+1} · acercar`,'target-focus');button.onclick=()=>{state.focus=t.bbox;renderPhoto();};first.append(button);tr.append(first);
    for(const m of G.models){
      const cell=node('td'),candidates=rowData(m.id,row.id).candidates[String(index)]||{};
      const list=Object.values(candidates).sort((a,b)=>b.confidence-a.confidence),top=list[0],sobre=candidates['2'];
      if(top)cell.append(node('span',`${G.names[top.class_id]} ${top.confidence.toFixed(3)}`,top.class_id===2?'candidate-good':'candidate-other'));
      else cell.append(node('span','Sin caja guardada con IoU ≥0,5'));
      cell.append(node('small',sobre?`Sobre ${sobre.confidence.toFixed(3)}${sobre.above_threshold?' · sobre umbral':' · bajo umbral'}`:'Sobre: sin candidato guardado',sobre?.above_threshold?'':'candidate-low'));tr.append(cell);
    }
    body.append(tr);
  });
  if(!row.gt_sobre){const tr=node('tr'),td=node('td','No hay etiquetas Sobre en esta foto. Revisar los candidatos contra el resto de etiquetas y el RGB, sin añadir etiquetas automáticamente.','target-none');td.colSpan=5;tr.append(td);body.append(tr);}
  table.append(body);
}
async function refresh(load=true){
  try{if(load)await loadSeed(state.seed);renderList();renderPhoto();}
  catch(error){$('photoTitle').textContent=error.message;console.error(error);}
}
function move(delta){const index=state.visible.findIndex(r=>r.id===state.id);const row=state.visible[index+delta];if(row){state.id=row.id;state.focus=null;refresh(false);}}
async function start(){
  $('seed').value=String(state.seed);$('campaignNotice').textContent=G.comparison_warning;
  for(const group of [...new Set(G.rows.map(r=>r.group))].sort()){const o=node('option',group);o.value=group;$('group').append(o);}
  for(const m of G.models){const tr=node('tr');tr.append(node('td',m.title),node('td',m.detail),node('td',m.date+(m.historical?' · histórico':' · reciente')));$('modelRegistry').append(tr);}
  for(const c of G.cases){const button=node('button',`Fila ${c.row} · ${c.label}`);button.onclick=async()=>{
    state.seed=c.seed;state.id=c.row;state.focus=c.bbox||null;$('seed').value=String(c.seed);$('filter').value='all';$('group').value='all';$('search').value='';await refresh();$('photoTitle').scrollIntoView({block:'start',behavior:'smooth'});
  };$('cases').append(button);}
  $('seed').onchange=()=>{state.seed=Number($('seed').value);refresh();};
  for(const id of ['filter','group'])$(id).onchange=()=>refresh(false);
  $('search').oninput=()=>refresh(false);
  for(const id of ['showGT','showPred','onlySobre','lowScores'])$(id).onchange=renderPhoto;
  $('previous').onclick=()=>move(-1);$('next').onclick=()=>move(1);
  $('fullPhoto').onclick=()=>{state.focus=null;renderPhoto();};
  $('focusSobre').onclick=()=>{const r=G.rows.find(r=>r.id===state.id),boxes=r.truth.filter(t=>t.class_id===2).map(t=>t.bbox);if(boxes.length){state.focus=[Math.min(...boxes.map(b=>b[0])),Math.min(...boxes.map(b=>b[1])),Math.max(...boxes.map(b=>b[2])),Math.max(...boxes.map(b=>b[3]))];renderPhoto();}};
  document.addEventListener('keydown',e=>{if(e.target.matches('input,select,textarea'))return;if(e.key==='ArrowRight')move(1);if(e.key==='ArrowLeft')move(-1);});
  await refresh();window.GALLERY_READY=true;
}
start();
