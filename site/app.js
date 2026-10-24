'use strict';

(() => {
  const byId = id => document.getElementById(id);
  const svgNS = 'http://www.w3.org/2000/svg';
  const video = byId('policy-video');
  let data;
  let displayedPiece = '';
  let displayedState = '';
  let frameRequest;
  const titleCase = value => String(value).replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function svg(tag, attributes = {}, text) {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function safeURL(value) {
    if (!value || typeof value !== 'string') return null;
    try {
      const url = new URL(value, document.baseURI);
      return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch { return null; }
  }

  function addParagraph(parent, label, value, className = 'case-step') {
    if (!value) return;
    const paragraph = element('p', className);
    if (label) paragraph.append(element('strong', '', `${label} `));
    paragraph.append(document.createTextNode(Array.isArray(value) ? value.join(' ') : String(value)));
    parent.append(paragraph);
  }

  function addLinks(parent, evidence) {
    if (!Array.isArray(evidence) || !evidence.length) return;
    const links = element('div', 'evidence-links');
    evidence.forEach(item => {
      const href = safeURL(item.href);
      if (!href) return;
      const link = element('a', '', item.label || 'Evidence');
      link.href = href;
      link.target = '_blank';
      link.rel = 'noreferrer';
      if (item.scope) link.title = item.scope;
      links.append(link);
    });
    parent.append(links);
  }

  function addMedia(parent, media) {
    if (!media || !safeURL(media.src)) return;
    const figure = element('figure', 'case-media');
    const isVideo = /\.(mp4|webm)(?:$|[?#])/i.test(media.src);
    const asset = element(isVideo ? 'video' : 'img');
    asset.src = safeURL(media.src);
    if (isVideo) {
      asset.controls = true;
      asset.playsInline = true;
      asset.preload = 'none';
      if (safeURL(media.poster)) asset.poster = safeURL(media.poster);
      asset.setAttribute('aria-label', media.alt || media.caption || 'Recorded experiment');
    } else {
      asset.alt = media.alt || '';
      asset.loading = 'eager';
    }
    figure.append(asset);
    if (media.caption) figure.append(element('figcaption', '', media.caption));
    parent.append(figure);
  }

  function renderStories() {
    const cases = byId('refinement-examples');
    cases.replaceChildren();
    data.refinement.forEach(item => {
      const article = element('article', 'refinement-case');
      const heading = element('div', 'case-heading');
      heading.append(element('h3', '', item.title));
      if (item.scope) heading.append(element('p', 'evidence-scope', item.scope));
      article.append(heading);
      addParagraph(article, 'Problem.', item.problem);
      if (Array.isArray(item.attempts) && item.attempts.length) {
        const attempts = element('ol', 'case-attempts');
        item.attempts.forEach((attempt, index) => {
          const step = element('li', 'case-attempt');
          step.append(element('strong', 'case-attempt-label', attempt.label || `Round ${index + 1}`));
          addParagraph(step, '', attempt.attempt);
          addParagraph(step, 'Diagnosis.', attempt.diagnosis);
          addParagraph(step, 'Change.', attempt.change);
          addParagraph(step, 'Outcome.', attempt.outcome);
          attempts.append(step);
        });
        article.append(attempts);
      } else {
        addParagraph(article, 'Diagnosis.', item.diagnosis);
        addParagraph(article, 'Refinement.', item.change);
      }
      addParagraph(article, 'Result.', item.result);
      addMedia(article, item.media);
      if (Array.isArray(item.evidence) && item.evidence.length) {
        const details = element('details', 'case-evidence');
        details.append(element('summary', '', 'Inspect evidence'));
        addLinks(details, item.evidence);
        article.append(details);
      }
      cases.append(article);
    });
    const method = byId('refinement-method');
    const alignment = data.methodAlignment;
    if (method && alignment && (alignment.description || alignment.steps?.length)) {
      method.replaceChildren();
      if (alignment.title) method.append(element('strong', '', alignment.title));
      addParagraph(method, '', alignment.description, '');
      const details = element('details', 'case-evidence');
      details.append(element('summary', '', 'How the workflow is applied'));
      if (Array.isArray(alignment.steps)) {
        const steps = element('ol');
        alignment.steps.forEach(item => {
          const step = element('li');
          addParagraph(step, item.title ? `${item.title}.` : '', item.description, '');
          steps.append(step);
        });
        details.append(steps);
      }
      addLinks(details, alignment.evidence);
      method.append(details);
      method.hidden = false;
      method.style.display = 'block';
    }
    const generalization = byId('generalization-evidence');
    generalization.replaceChildren();
    data.generalization.forEach(item => {
      const article = element('article', 'generalization-item');
      article.append(element('h3', '', item.title));
      addParagraph(article, '', item.claim, '');
      addParagraph(article, '', item.observed, '');
      addParagraph(article, '', item.scope, 'evidence-scope');
      addMedia(article, item.media);
      addLinks(article, item.evidence);
      generalization.append(article);
    });
  }

  function simulationTime(videoTime) {
    const mapping = data.media.mapping;
    if (!mapping.length) return 0;
    let low = 0;
    let high = mapping.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (mapping[middle].videoTime <= videoTime + 0.00001) low = middle + 1;
      else high = middle;
    }
    const index = Math.max(0, low - 1);
    const point = mapping[index];
    if (data.media.mappingMode === 'step' || index === mapping.length - 1) return point.simTime;
    const next = mapping[index + 1];
    const fraction = Math.max(0, Math.min(1, (videoTime - point.videoTime) / (next.videoTime - point.videoTime)));
    return point.simTime + fraction * (next.simTime - point.simTime);
  }

  function seek(time) {
    if (!Number.isFinite(time)) return;
    video.currentTime = Math.max(0, Math.min(time, Number.isFinite(video.duration) ? video.duration : time));
    synchronize();
  }

  function nodeState(nodeId, simTime) {
    const stage = data.timeline.find(item => item.nodeId === nodeId);
    if (!stage || simTime < stage.simStart) return 'is-pending';
    if (simTime < stage.simEnd || stage.passed === null) return 'is-current';
    return stage.passed ? 'is-complete' : 'is-failed';
  }

  function renderPieceButtons() {
    const selector = byId('piece-selector');
    selector.replaceChildren();
    data.pieces.forEach((piece, index) => {
      const button = element('button', 'piece-button');
      button.type = 'button';
      button.dataset.piece = piece.name;
      button.style.setProperty('--piece-color', piece.color);
      button.setAttribute('aria-pressed', 'false');
      button.disabled = !Number.isFinite(piece.videoStart);
      button.title = button.disabled ? 'No recorded observations for this piece yet.' : `Jump to ${titleCase(piece.name)}`;
      const dot = element('span', 'piece-dot');
      dot.setAttribute('aria-hidden', 'true');
      button.append(dot, document.createTextNode(`${String(index + 1).padStart(2, '0')} ${titleCase(piece.name)}`));
      button.addEventListener('click', () => seek(piece.videoStart));
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const buttons = Array.from(selector.querySelectorAll('button:not(:disabled)'));
        const current = buttons.indexOf(button);
        const target = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
          (current + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
        buttons[target].focus();
        buttons[target].click();
      });
      selector.append(button);
    });
  }

  function drawGraph(pieceName, simTime, activeStage) {
    const container = byId('policy-graph');
    const nodes = data.graph.nodes.filter(node => node.piece === pieceName && node.type !== 'end');
    if (!nodes.length) return;
    const columns = window.matchMedia('(max-width: 720px)').matches ? 2 : 3;
    const width = columns * 188 + 44;
    const nodeWidth = 164;
    const nodeHeight = 56;
    const stepX = 188;
    const stepY = 83;
    const rows = Math.ceil(nodes.length / columns);
    const footerY = 18 + rows * stepY + 7;
    const height = footerY + 61;
    const positions = new Map();
    nodes.forEach((node, index) => {
      const row = Math.floor(index / columns);
      const column = row % 2 ? columns - 1 - index % columns : index % columns;
      positions.set(node.nodeId, {x: 18 + column * stepX, y: 16 + row * stepY});
    });
    const canvas = svg('svg', {viewBox: `0 0 ${width} ${height}`, class: 'policy-graph-svg',
      role: 'group', 'aria-labelledby': 'graph-title graph-description'});
    canvas.append(svg('title', {id: 'graph-title'}, `${pieceName === 'all12' ? 'Final' : titleCase(pieceName)} executable policy graph`));
    canvas.append(svg('desc', {id: 'graph-description'},
      'Solid arrows show executable transitions. Dashed routes lead to the shared abort state. Node colors follow recorded checkpoint windows. Select a recorded node to seek.'));
    const defs = svg('defs');
    const arrow = svg('marker', {id: 'graph-arrow', viewBox: '0 0 8 8', refX: 7, refY: 4,
      markerWidth: 5, markerHeight: 5, orient: 'auto-start-reverse'});
    arrow.append(svg('path', {d: 'M 0 0 L 8 4 L 0 8 z', fill: '#a6b5aa'}));
    defs.append(arrow);
    canvas.append(defs);
    const terminal = {x: 18, y: footerY};
    const abort = {x: 18 + (columns - 1) * stepX, y: footerY};
    const failedTerminal = activeStage?.terminalStatus && simTime >= activeStage.simEnd;
    const edgeLayer = svg('g', {'aria-hidden': 'true'});
    const errorRows = new Set();
    const edgeDescriptions = [];
    data.graph.edges.filter(edge => positions.has(edge.source)).forEach(edge => {
      const from = positions.get(edge.source);
      if (edge.kind === 'error') {
        const railY = from.y + nodeHeight + 10;
        const path = svg('path', {d: `M ${from.x + nodeWidth / 2} ${from.y + nodeHeight} V ${railY} H ${width - 19}`, class: 'graph-error-edge'});
        path.append(svg('title', {}, `${edge.source}: ${edge.conditions.join(', ')} → ${edge.target}`));
        edgeLayer.append(path);
        errorRows.add(railY);
        return;
      }
      const to = positions.get(edge.target) || terminal;
      let path;
      if (from.y === to.y) {
        const forward = to.x > from.x;
        path = `M ${from.x + (forward ? nodeWidth : 0)} ${from.y + nodeHeight / 2} H ${to.x + (forward ? 0 : nodeWidth)}`;
      } else if (positions.has(edge.target)) {
        path = `M ${from.x + nodeWidth / 2} ${from.y + nodeHeight} V ${to.y}`;
      } else {
        const y = from.y + nodeHeight + 18;
        path = `M ${from.x + nodeWidth / 2} ${from.y + nodeHeight} V ${y} H ${to.x + nodeWidth / 2} V ${to.y}`;
      }
      const state = nodeState(edge.source, simTime);
      const line = svg('path', {d: path, class: `graph-edge ${state}`, 'marker-end': 'url(#graph-arrow)'});
      line.append(svg('title', {}, `${edge.source}: ${edge.conditions.join(', ')} → ${edge.target}`));
      edgeLayer.append(line);
      if (!positions.has(edge.target)) edgeDescriptions.push(edge.target);
    });
    if (errorRows.size) {
      edgeLayer.append(svg('path', {d: `M ${width - 19} ${Math.min(...errorRows)} V ${footerY + nodeHeight / 2} H ${abort.x + nodeWidth}`,
        class: 'graph-error-edge', 'marker-end': 'url(#graph-arrow)'}));
    }
    canvas.append(edgeLayer);
    nodes.forEach((node, index) => {
      const position = positions.get(node.nodeId);
      const stage = data.timeline.find(item => item.nodeId === node.nodeId);
      const state = nodeState(node.nodeId, simTime);
      const group = svg('g', {class: state, 'data-node-id': node.nodeId});
      const canSeek = stage && Number.isFinite(stage.videoStart) &&
        data.media.mapping.some(point => point.simTime >= stage.simStart && point.simTime < stage.simEnd);
      if (canSeek) {
        group.setAttribute('role', 'button');
        group.setAttribute('tabindex', '0');
        group.setAttribute('aria-label', `Jump to ${node.label}`);
        group.style.cursor = 'pointer';
        group.addEventListener('click', () => seek(stage.videoStart));
        group.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            seek(stage.videoStart);
          }
        });
      }
      const checkpointText = stage?.terminalStatus ? 'Terminal scope verification refused; no checkpoint earned' :
        stage && stage.checkpoint ? `Independent CP ${stage.checkpoint.number}: ${stage.passed ? 'passed' : 'failed'}` : 'Checkpoint not yet recorded';
      group.append(svg('title', {}, `${node.nodeId}\nSubgraph: ${node.ref}\n${checkpointText}`));
      group.append(svg('rect', {x: position.x, y: position.y, width: nodeWidth, height: nodeHeight, rx: 6, class: 'graph-node'}));
      group.append(svg('text', {x: position.x + 12, y: position.y + 23, class: 'graph-label'}, node.label));
      group.append(svg('text', {x: position.x + 12, y: position.y + 42, class: 'graph-phase'},
        `${String(index + 1).padStart(2, '0')} / ${state === 'is-current' ? 'current' : state === 'is-complete' ? 'passed' : state === 'is-failed' ? 'failed' : 'pending'}`));
      canvas.append(group);
    });
    const nextTarget = edgeDescriptions[0] || 'done';
    const nextPiece = data.pieces.find(piece => piece.nodeIds.includes(nextTarget));
    const nextLabel = nextPiece ? `Next: ${titleCase(nextPiece.name)}` : nextTarget === 'finish_all12' ? 'Final check' : 'Complete';
    [[terminal, nextLabel], [abort, 'Abort on error']].forEach(([position, label]) => {
      canvas.append(svg('rect', {x: position.x, y: position.y, width: nodeWidth, height: nodeHeight - 8, rx: 6,
        class: `graph-node-terminal${position === abort && failedTerminal ? ' graph-node is-failed' : ''}`}));
      canvas.append(svg('text', {x: position.x + 12, y: position.y + 29, class: 'graph-phase'}, label));
    });
    const description = element('p', 'graph-description');
    description.textContent = activeStage ? `${activeStage.nodeId} · ${failedTerminal ? 'terminal scope verification refused' : activeStage.terminalStatus ? 'terminal verification' : activeStage.passed === null ? 'checkpoint not yet recorded' : `native checkpoint window ${activeStage.simStart.toFixed(2)}–${activeStage.simEnd.toFixed(2)} s`}.` :
      'Topology comes from the executable workflow. Dashed lines share the abort route.';
    const links = element('p', 'evidence-links');
    [['Workflow', data.evidence.workflow], ['Physical checks', data.evidence.checkpoints], ['Recording timing', data.evidence.media],
      ...(data.evidence.audit ? [['Final audit', data.evidence.audit]] : [])].forEach(([label, href]) => {
      const link = element('a', '', label);
      link.href = href;
      link.target = '_blank';
      link.rel = 'noreferrer';
      links.append(link);
    });
    container.replaceChildren(canvas, description, links);
  }

  function synchronize() {
    if (!data || !data.media.mapping.length) return;
    const simTime = simulationTime(video.currentTime);
    byId('policy-sim-time').textContent = `${simTime.toFixed(2)} s`;
    let current = data.timeline.find(stage => simTime >= stage.simStart && simTime < stage.simEnd);
    if (!current) current = [...data.timeline].reverse().find(stage => simTime >= stage.simStart) || data.timeline[0];
    if (!current) return;
    const pieceName = current.piece;
    const phase = data.graph.nodes.find(node => node.nodeId === current.nodeId);
    byId('policy-current-piece').textContent = pieceName === 'all12' ? 'Final verification' : titleCase(pieceName);
    byId('policy-current-phase').textContent = current.terminalStatus && simTime >= current.simEnd ?
      'Terminal verification refused' : phase ? phase.label : titleCase(current.phase);
    const stateKey = data.graph.nodes.filter(node => node.piece === pieceName).map(node => nodeState(node.nodeId, simTime)).join('|') +
      `|${window.matchMedia('(max-width: 720px)').matches ? 2 : 3}`;
    if (pieceName !== displayedPiece || `${current.nodeId}|${stateKey}` !== displayedState) {
      drawGraph(pieceName, simTime, current);
      displayedPiece = pieceName;
      displayedState = `${current.nodeId}|${stateKey}`;
    }
    document.querySelectorAll('#piece-selector button').forEach(button => {
      const piece = data.pieces.find(item => item.name === button.dataset.piece);
      const lastStage = [...data.timeline].reverse().find(stage => stage.piece === piece.name && stage.checkpoint);
      const complete = piece.complete && lastStage && simTime >= lastStage.simEnd;
      const selected = piece.name === pieceName;
      button.classList.toggle('is-current', selected);
      button.classList.toggle('is-complete', Boolean(complete));
      button.setAttribute('aria-pressed', String(selected));
    });
  }

  function renderStatus() {
    const run = data.run;
    byId('assembly-summary').textContent = run.physicalAccepted ?
      'All twelve pieces assembled · independently verified.' : run.full12Accepted ?
      'Twelve-piece visual policy completed, with independent physical verification.' :
      `${run.completePieces} / ${run.pieceCount} piece modules verified · ${run.passedCheckpoints} / ${run.expectedCheckpoints} physical checkpoints passed in the recorded run.`;
    const speed = data.media.nominalSimulationSpeed || 1;
    const nativeReplay = data.media.kind === 'native_recorded_state_render';
    byId('policy-status').textContent = (nativeReplay ?
      `Recorded simulator replay · GPU-rendered from recorded states · ${speed}× simulation time. ` :
      `${data.media.observationCount} recorded policy RGB observations · ${speed}× simulation time. Frames are held between captures. `) +
      (run.full12Accepted ? 'The full episode passed independent verification.' :
        run.terminal ? `${run.passedCheckpoints} / ${run.expectedCheckpoints} physical checkpoints passed; terminal graph verification refused.` :
          'Final full-episode verification is pending.');
  }

  function animate() {
    synchronize();
    if (!video.paused && !video.ended) frameRequest = requestAnimationFrame(animate);
  }

  async function load() {
    try {
      const response = await fetch('data/research.json');
      if (!response.ok) throw new Error(`Research evidence unavailable (${response.status})`);
      data = await response.json();
      if (!data.graph || !Array.isArray(data.media.mapping)) throw new Error('Unsupported research data format.');
      renderStories();
      renderPieceButtons();
      renderStatus();
      if (safeURL(data.media.poster)) video.poster = safeURL(data.media.poster);
      if (safeURL(data.media.src)) video.src = safeURL(data.media.src);
      ['loadedmetadata', 'timeupdate', 'seeking', 'seeked', 'pause', 'ended', 'ratechange'].forEach(event => video.addEventListener(event, synchronize));
      video.addEventListener('play', () => { cancelAnimationFrame(frameRequest); animate(); });
      video.addEventListener('pause', () => cancelAnimationFrame(frameRequest));
      window.addEventListener('resize', synchronize);
      video.addEventListener('error', () => {
        byId('policy-status').textContent = 'The recording could not load. The graph, checkpoint evidence, and examples remain available.';
      });
      synchronize();
    } catch (error) {
      byId('policy-status').textContent = 'The execution evidence could not load. Open the source repository for the policy and recorded checks.';
      byId('policy-current-phase').textContent = 'Unavailable';
      byId('policy-graph').textContent = 'The graph needs the exported execution data.';
      console.error(error);
    }
  }

  if (video) load();
})();
