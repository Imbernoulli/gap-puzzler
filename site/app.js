'use strict';
const repository = 'https://github.com/Imbernoulli/gap-puzzler';
const modes = {
  pyramid: {version: 'PYRAMID V40', title: 'A five-layer pyramid.', description: 'Oracle object poses, twelve pieces, original YAM grippers, and a support-aware placement order.', time: '339.86', error: '2.76', note: '244 frames at 1 fps · 339.86 s of simulation', retries: 'Two failed attempt checks were recovered by graph retries. All sixteen historical records are retained.'},
  flat: {version: 'FLAT V10', title: 'The complete flat layout.', description: 'Using oracle object poses, all twelve pieces are placed into the empty case in the reference flat packing.', time: '246.24', error: '0.97', note: 'Native RSS recording · 246.24 s of simulation', retries: 'All fourteen checkpoint invocations passed. Both arms released the puzzle and returned home.'}
};
const byId = id => document.getElementById(id);
const video = byId('assembly-video');
function setMode(mode) {
  const current = modes[mode];
  if (!current) return;
  video.pause();
  video.poster = `media/${mode}_live_success_final.png`;
  video.querySelector('source').src = `media/${mode}_live_success.mp4`;
  video.setAttribute('aria-label', `${mode === 'flat' ? 'Flat layout' : 'Pyramid'} assembly recording`);
  video.load();
  video.playbackRate = Number(byId('playback-rate').value);
  for (const [id, field] of [['take-version','version'],['take-title','title'],['take-description','description'],['video-note','note'],['take-retries','retries']]) byId(id).textContent = current[field];
  byId('take-time').replaceChildren(document.createTextNode(`${current.time} `), Object.assign(document.createElement('small'), {textContent:'s'}));
  byId('take-error').replaceChildren(document.createTextNode(`${current.error} `), Object.assign(document.createElement('small'), {textContent:'mm'}));
  byId('take-json').href = `data/${mode}_live_result.json`;
  byId('take-download').href = `media/${mode}_live_success.mp4`;
  byId('assembly-panel').setAttribute('aria-labelledby', `tab-${mode}`);
  document.querySelectorAll('[data-mode]').forEach(button => {
    const selected = button.dataset.mode === mode;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
}
document.querySelectorAll('[data-mode]').forEach(button => {
  button.addEventListener('click', () => setMode(button.dataset.mode));
  button.addEventListener('keydown', event => {
    if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();
      const mode = event.key === 'Home' ? 'pyramid' : event.key === 'End' ? 'flat' : button.dataset.mode === 'pyramid' ? 'flat' : 'pyramid';
      setMode(mode); byId(`tab-${mode}`).focus();
    }
  });
});
byId('playback-rate').addEventListener('change', event => { video.playbackRate = Number(event.target.value); });
video.addEventListener('loadedmetadata', () => { video.playbackRate = Number(byId('playback-rate').value); });
byId('copy-command').addEventListener('click', async () => {
  const button = byId('copy-command');
  const command = byId('setup-command').textContent;
  try {
    await navigator.clipboard.writeText(command);
    button.textContent = 'Copied';
    byId('app-message').textContent = 'Setup commands copied to clipboard.';
    setTimeout(() => {button.textContent = 'Copy';}, 1800);
  } catch {
    const selection = window.getSelection();
    const range = document.createRange(); range.selectNodeContents(byId('setup-command'));
    selection.removeAllRanges(); selection.addRange(range);
    button.textContent = 'Selected';
    byId('app-message').textContent = 'Commands selected. Press Control C or Command C to copy.';
  }
});
function renderPiece(piece, index, count) {
  byId('piece-order').textContent = `PIECE ${String(index+1).padStart(2,'0')} / ${count}`;
  byId('piece-name').textContent = piece.name[0].toUpperCase()+piece.name.slice(1);
  byId('piece-note').textContent = piece.note;
  byId('piece-source').href = `${repository}/blob/main/graphs/pyramid_v40/scripts/${piece.name}.py`;
  const attempts = byId('checkpoint-attempts'); attempts.replaceChildren();
  piece.attempts.forEach((attempt, i) => {
    const row = document.createElement('div'); row.className = 'attempt';
    const label = document.createElement('span'); label.textContent = `ATTEMPT ${i+1}`;
    const value = document.createElement('span'); value.className = attempt.passed ? 'attempt-pass' : 'attempt-fail';
    value.textContent = `${attempt.error_mm.toFixed(2)} mm / ${attempt.passed ? 'PASS' : 'RETRY'}`;
    row.append(label, value); attempts.append(row);
  });
  document.querySelectorAll('.piece-button').forEach(button => {
    const active = button.dataset.piece === piece.name;
    button.classList.toggle('active',active); button.setAttribute('aria-pressed',String(active));
  });
}
async function loadEvidence() {
  try {
    const response = await fetch('data/project.json');
    if (!response.ok) throw new Error(`Evidence unavailable: ${response.status}`);
    const data = await response.json();
    const selector = byId('piece-selector');
    data.pieces.forEach((piece,index) => {
      const button = document.createElement('button'); button.className='piece-button'; button.dataset.piece=piece.name;
      button.setAttribute('aria-pressed', 'false'); button.style.setProperty('--piece-color',piece.color);
      const dot=document.createElement('span');dot.className='piece-dot';dot.setAttribute('aria-hidden','true');
      button.append(dot,document.createTextNode(piece.name[0].toUpperCase()+piece.name.slice(1)));
      button.addEventListener('click',()=>renderPiece(piece,index,data.pieces.length)); selector.append(button);
    });
    renderPiece(data.pieces[0],0,data.pieces.length);
    const body=byId('results-body');body.replaceChildren();
    data.formal.forEach(task=>{
      const row=document.createElement('tr'); const name=document.createElement('th');name.scope='row';
      const link=document.createElement('a');link.href=`${repository}/blob/main/${task.evidence}`;link.target='_blank';link.rel='noreferrer';link.textContent=task.label;
      const graph=document.createElement('span');graph.className='result-graph';graph.textContent=task.graph;name.append(link,graph);row.append(name);
      [`${task.successes} / ${task.runs.length}`,task.runs.map(r=>r.sim_time_s.toFixed(2)).join(' / ')+' s',task.runs.map(r=>r.max_error_mm.toFixed(2)).join(' / ')+' mm','4.6 s, both runs'].forEach(text=>{const cell=document.createElement('td');cell.textContent=text;row.append(cell);});body.append(row);
    });
  } catch (error) {
    byId('piece-selector').textContent='The checkpoint explorer could not load. Open the source workflow on GitHub to inspect all records.';
    byId('piece-note').textContent='Recordings and summary results remain available above.';
    console.error(error);
  }
}
loadEvidence();
