'use strict';
const data = JSON.parse(document.getElementById('page-data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
const compare = document.getElementById('compare');
if (compare) {
  const range = document.getElementById('compare-range');
  const set = () => compare.style.setProperty('--x', `${range.value}%`);
  range.addEventListener('input', set); set();
}
function el(name, attrs = {}, text) {
  const node = document.createElementNS(NS, name);
  Object.entries(attrs).forEach(([k,v]) => node.setAttribute(k,v));
  if (text != null) node.textContent = text;
  return node;
}
function initPlayer(root, run) {
  const q = key => root.querySelector(`[data-k="${key}"]`);
  const video = q('video'), svg = q('graph'), pieces = run.pieces;
  const rate = run.video.steps_per_second;
  let shown = null, columns = 0;
  function seek(step) {
    const go = () => { video.currentTime = Math.min((step + 1) / rate, video.duration || Infinity); update(); };
    if (video.readyState >= 1) go();
    else { video.addEventListener('loadedmetadata', go, {once:true}); video.load(); }
  }
  pieces.forEach((piece, index) => {
    const button = document.createElement('button');
    button.type = 'button'; button.dataset.piece = piece.name;
    button.title = piece.name === 'finish' ? 'Finish' : `${index + 1}. ${cap(piece.name)}`;
    button.setAttribute('aria-label', `Jump to ${button.title}`);
    if (piece.shapeSrc) {
      const img = document.createElement('img'); img.src = piece.shapeSrc; img.alt = ''; img.width = 36; img.height = 36; button.append(img);
    } else {
      const check = document.createElement('span'); check.className = 'finish-icon'; check.textContent = '✓'; button.append(check);
    }
    const label = document.createElement('span'); label.textContent = index < 12 ? index + 1 : 'End'; button.append(label);
    button.addEventListener('click', () => seek(piece.start));
    q('track').append(button); piece.button = button;
  });

  // The recorded dispatch graph, folded horizontally. Only routes present in
  // workflow.json are drawn; the relook mark denotes a bounded routine inside a
  // node, not an invented dispatcher edge.
  function drawGraph(piece) {
    const n = piece.nodes.length;
    const cols = Math.min(n, q('graph').getBoundingClientRect().width >= 420 ? 3 : 2);
    columns = cols;
    const boxW = 176, boxH = 34, dx = 30, dy = 34, margin = 10;
    const rows = Math.ceil(n / cols), W = cols * (boxW + dx) + 8;
    const H = rows * (boxH + dy) + 32;
    const at = i => {
      const row = Math.floor(i / cols), col = row % 2 ? cols - 1 - i % cols : i % cols;
      return {x:margin + col * (boxW + dx), y:margin + row * (boxH + dy), row};
    };
    const arrow = `arrow-${root.dataset.rig}`, fail = `fail-${root.dataset.rig}`;
    svg.replaceChildren(); svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const defs = el('defs');
    for (const [id, cls] of [[arrow,'arrowhead'], [fail,'failhead']]) {
      const marker = el('marker',{id,viewBox:'0 0 8 8',refX:7,refY:4,markerWidth:6,markerHeight:6,orient:'auto'});
      marker.append(el('path',{d:'M0,0 L8,4 L0,8 z',class:cls})); defs.append(marker);
    }
    svg.append(defs);
    const byId = new Map(piece.nodes.map((node,i) => [node.id,i]));
    const rail = W - 7;
    svg.append(el('path',{d:`M${rail},${boxH + margin + 11} V${H-12} H${W/2+62}`,class:'abort-rail','marker-end':`url(#${fail})`}));
    piece.nodes.forEach((node, i) => {
      const p = at(i);
      const routes = Object.entries(node.routes || {});
      const targets = [...new Set(routes.filter(([,v])=>v!=='abort').map(([,v])=>v))];
      targets.forEach(target => {
        const j = byId.get(target);
        if (j == null) return; // the next piece is connected in the shape strip
        const next = at(j), names = routes.filter(([,v])=>v===target).map(([k])=>k);
        names.forEach((name,k) => {
          const offset = (k - (names.length-1)/2) * 5;
          let d;
          if (next.row === p.row) {
            const right = next.x > p.x, sx = p.x + (right ? boxW : 0), tx = next.x + (right ? -2 : boxW+2);
            d = `M${sx},${p.y+boxH/2+offset} C${(sx+tx)/2},${p.y+boxH/2+offset} ${(sx+tx)/2},${next.y+boxH/2+offset} ${tx},${next.y+boxH/2+offset}`;
          } else {
            d = `M${p.x+boxW/2+offset},${p.y+boxH} V${next.y-2}`;
          }
          const path=el('path',{d,class:'edge','marker-end':`url(#${arrow})`});
          path.append(el('title',{},name)); svg.append(path);
        });
      });
      const errors = routes.filter(([,v])=>v==='abort').map(([k])=>k);
      if (errors.length) {
        const line = el('path',{d:`M${p.x+boxW-12},${p.y+boxH} v11 H${rail}`,class:'abort-edge'});
        line.append(el('title',{},`${errors.join(' / ')} → stop`)); svg.append(line);
      }
    });
    piece.nodes.forEach((node,i) => {
      const {x,y} = at(i);
      const g=el('g',{class:'node',tabindex:0,role:'button','data-node':node.id,'aria-label':`${node.label}: jump to this step`});
      g.append(el('title',{},`${node.detail}\n${Object.entries(node.routes||{}).map(([a,b])=>`${a} → ${b}`).join('\n')}${node.relook?'\n↻ Bounded re-observation inside this node':''}`));
      g.append(el('rect',{x,y,width:boxW,height:boxH,rx:6}));
      g.append(el('text',{x:x+9,y:y+22,class:'node-label'},(node.relook?'↻ ':'')+node.label));
      g.addEventListener('click',()=>seek(node.start));
      g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();seek(node.start);}});
      svg.append(g); node.group=g;
    });
    svg.append(el('rect',{x:W/2-62,y:H-22,width:124,height:21,rx:5,class:'stop-box'}));
    svg.append(el('text',{x:W/2,y:H-7,'text-anchor':'middle',class:'abort-label'},'error / unknown → stop'));
  }
  function showPiece(piece) {
    if(shown===piece) return;
    shown=piece;
    q('swatch').replaceChildren();
    if(piece.shapeSrc){const img=document.createElement('img');img.src=piece.shapeSrc;img.alt='';q('swatch').append(img);}
    else q('swatch').textContent='✓';
    q('piece').textContent=piece.name==='finish'?'Finish':cap(piece.name);
    q('index').textContent=piece.name==='finish'?'12 pieces placed':`${pieces.indexOf(piece)+1} / 12 · ${piece.nodes.length} nodes`;
    drawGraph(piece);
  }
  function update() {
    const step=video.currentTime*rate;
    const current=pieces.find(p=>p.end==null||step<p.end)||pieces[pieces.length-1];
    showPiece(current);
    pieces.forEach(p=>{p.button.classList.toggle('done',p.end!=null&&step>=p.end);p.button.classList.toggle('now',p===current);p.button.setAttribute('aria-current',String(p===current));});
    let active=null;
    current.nodes.forEach(node=>{
      const done=node.end!=null&&step>=node.end&&node.passed;
      const now=!active&&!done&&step>=node.start;
      if(now)active=node;
      node.group.classList.toggle('done',done);node.group.classList.toggle('now',now);
    });
    const detail=active||current.nodes[current.nodes.length-1];
    q('detail').textContent=detail.detail;
    q('time').textContent=`t = ${(step/run.control_hz).toFixed(1)} s`;
  }
  q('speed').textContent=`${Math.round(rate/run.control_hz)}× playback · 12/12 · 84/84 checks`;
  ['timeupdate','seeked','loadedmetadata','ended'].forEach(n=>video.addEventListener(n,update));
  let frame=null;
  const loop=()=>{update();frame=video.paused?null:requestAnimationFrame(loop);};
  video.addEventListener('play',()=>{if(!frame)frame=requestAnimationFrame(loop);});
  const start=Number(new URLSearchParams(location.search).get('t'));
  if(start>0)seek(start*run.control_hz);
  update();
  if('ResizeObserver' in window)new ResizeObserver(()=>{
    const cols=Math.min(shown.nodes.length,svg.getBoundingClientRect().width>=420?3:2);
    if(cols!==columns){drawGraph(shown);update();}
  }).observe(svg.parentElement);
}
document.querySelectorAll('.player[data-rig]').forEach(root=>initPlayer(root,data.rigs[root.dataset.rig]));

const clips=[...document.querySelectorAll('video[data-autoplay]')], onScreen=new Set();
clips.forEach(v=>{v.muted=true;v.playsInline=true;});
const visible=v=>v.offsetParent!==null;
const play=v=>{if(!visible(v)||document.hidden)return;const promise=v.play();if(promise)promise.catch(()=>{});};
if('IntersectionObserver' in window){
  const watch=new IntersectionObserver(entries=>entries.forEach(e=>{
    if(e.isIntersecting){onScreen.add(e.target);play(e.target);}else{onScreen.delete(e.target);e.target.pause();}
  }),{threshold:.2});clips.forEach(v=>watch.observe(v));
}else{clips.forEach(v=>onScreen.add(v));clips.forEach(play);}
document.addEventListener('visibilitychange',()=>clips.forEach(v=>document.hidden?v.pause():onScreen.has(v)&&play(v)));
const tabs=[...document.querySelectorAll('[data-rig-tab]')];
function selectRig(rig){
  document.body.dataset.rig=rig;
  tabs.forEach(t=>{const selected=t.dataset.rigTab===rig;t.setAttribute('aria-selected',String(selected));t.tabIndex=selected?0:-1;});
  clips.forEach(v=>visible(v)?onScreen.has(v)&&play(v):v.pause());
}
tabs.forEach((tab,i)=>{
  tab.addEventListener('click',()=>selectRig(tab.dataset.rigTab));
  tab.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){
    e.preventDefault();const j=e.key==='Home'?0:e.key==='End'?tabs.length-1:(i+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    selectRig(tabs[j].dataset.rigTab);tabs[j].focus();
  }});
});
selectRig(location.hash==='#custom'?'custom':'official');
