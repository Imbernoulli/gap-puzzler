'use strict';

(() => {
  const byId = id => document.getElementById(id);
  const svgNS = 'http://www.w3.org/2000/svg';
  const video = byId('policy-video');
  let data;
  let displayedPiece = '';
  let displayedState = '';
  let frameRequest;
  let inspectedStage = null;
  let overviewEdges = [];
  let overviewRenderKey = '';
  let pendingSeek = null;
  const titleCase = value => String(value).replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
  const pieceNumber = name => String(data.pieces.findIndex(piece => piece.name === name) + 1).padStart(2, '0');
  const pieceLabel = name => `Piece ${pieceNumber(name)}`;

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

  function addMedia(parent, media, options = {}) {
    if (!media || !safeURL(media.src)) return;
    const figure = element('figure', 'case-media');
    const isVideo = media.type === 'video' || /\.(mp4|webm)(?:$|[?#])/i.test(media.src);
    const asset = element(isVideo ? 'video' : 'img');
    asset.src = safeURL(media.src);
    if (Number.isFinite(media.width)) asset.width = media.width;
    if (Number.isFinite(media.height)) asset.height = media.height;
    if (isVideo) {
      asset.controls = true;
      asset.playsInline = true;
      asset.preload = 'none';
      if (safeURL(media.poster)) asset.poster = safeURL(media.poster);
      asset.setAttribute('aria-label', media.alt || media.caption || 'Recorded experiment');
      if (options.loop) {
        asset.muted = true;
        asset.loop = true;
        asset.preload = 'metadata';
        if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
          if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver(entries => entries.forEach(entry => {
              if (entry.isIntersecting) asset.play().catch(() => {});
              else asset.pause();
            }), {threshold: .2});
            observer.observe(asset);
          }
        }
      }
    } else {
      asset.alt = media.alt || '';
      asset.loading = 'eager';
    }
    figure.append(asset);
    if (media.caption) figure.append(element('figcaption', '', media.caption));
    parent.append(figure);
    return figure;
  }

  function initializeComparison() {
    const comparison = byId('real2sim-comparison');
    const slider = byId('comparison-slider');
    if (!comparison || !slider) return;
    const update = () => {
      const position = Math.max(0, Math.min(100, Number(slider.value)));
      comparison.style.setProperty('--comparison-split', `${position}%`);
      slider.setAttribute('aria-valuetext', `Real ${position}%, simulation ${100 - position}%`);
    };
    slider.addEventListener('input', update);
    slider.addEventListener('change', update);
    configureComparison({ready: comparison.dataset.ready === 'true'});
    update();
  }

  function configureComparison(record = {}) {
    const comparison = byId('real2sim-comparison');
    if (!comparison) return;
    const ready = record.ready === true;
    comparison.dataset.ready = String(ready);
    comparison.querySelectorAll('.comparison-sim, .comparison-label-sim, .comparison-divider, #comparison-slider').forEach(node => {
      node.hidden = !ready;
      node.style.display = ready ? '' : 'none';
    });
    const slider = byId('comparison-slider');
    if (slider) slider.disabled = !ready;
    const real = byId('comparison-real');
    const sim = byId('comparison-sim');
    if (real && safeURL(record.realSrc || record.real?.src)) real.src = safeURL(record.realSrc || record.real.src);
    if (ready && sim && safeURL(record.simSrc || record.sim?.src)) sim.src = safeURL(record.simSrc || record.sim.src);
    const caption = byId('comparison-caption');
    if (caption) caption.textContent = ready ? record.caption || 'Real and reconstructed scene' : 'Original demonstration';
  }

  function renderAttemptHistory(parent, item) {
    addParagraph(parent, 'Problem.', item.problem);
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
      parent.append(attempts);
    } else {
      addParagraph(parent, 'Diagnosis.', item.diagnosis);
      addParagraph(parent, 'Refinement.', item.change);
    }
    addParagraph(parent, 'Result.', item.result);
  }

  function renderStories() {
    const cases = byId('refinement-examples');
    cases.replaceChildren();
    data.refinement.forEach(item => {
      const article = element('article', 'refinement-case');
      const heading = element('div', 'case-heading');
      heading.append(element('h3', '', item.title));
      article.append(heading);
      const visual = Array.isArray(item.visualSteps) && item.visualSteps.length;
      if (visual) {
        addParagraph(article, '', item.caption, 'case-caption');
        const steps = element('ol', 'case-visual-steps');
        item.visualSteps.forEach((item, index) => {
          const step = element('li', 'case-visual-step');
          step.append(element('span', 'visual-step-label', item.label || String(index + 1).padStart(2, '0')));
          if (item.title) step.append(element('h4', '', item.title));
          addMedia(step, item.media);
          addParagraph(step, '', item.description, 'visual-step-description');
          steps.append(step);
        });
        article.append(steps);
      } else {
        renderAttemptHistory(article, item);
        addMedia(article, item.media);
      }
      if (visual || item.evidence?.length) {
        const details = element('details', 'case-evidence');
        details.append(element('summary', '', 'Trials and evidence'));
        if (visual) renderAttemptHistory(details, item);
        addParagraph(details, '', item.scope, 'evidence-scope');
        addLinks(details, item.evidence);
        article.append(details);
      }
      cases.append(article);
    });
    if (data.additionalRefinement?.length) {
      const details = element('details', 'case-evidence additional-refinement');
      details.append(element('summary', '', 'More refinements and evidence'));
      data.additionalRefinement.forEach(item => {
        const group = element('div', 'additional-refinement-item');
        group.append(element('strong', '', item.title));
        addLinks(group, item.evidence);
        details.append(group);
      });
      cases.append(details);
    }
    const bimanual = data.bimanualShowcase;
    const bimanualContainer = byId('bimanual-showcase');
    if (bimanualContainer && bimanual?.media) {
      bimanualContainer.replaceChildren();
      bimanualContainer.append(element('h3', '', bimanual.title));
      addParagraph(bimanualContainer, '', bimanual.caption, 'case-caption');
      const grid = element('div', 'bimanual-media-grid');
      addMedia(grid, bimanual.media, {loop: true});
      addMedia(grid, bimanual.geometryMedia);
      bimanualContainer.append(grid);
      addParagraph(bimanualContainer, '', bimanual.reason, 'bimanual-reason');
      if (bimanual.evidence?.length) {
        const details = element('details', 'case-evidence');
        details.append(element('summary', '', 'Geometry and execution evidence'));
        addLinks(details, bimanual.evidence);
        bimanualContainer.append(details);
      }
    }
    const method = byId('refinement-method');
    const alignment = data.methodAlignment;
    if (method && alignment && (alignment.description || alignment.steps?.length)) {
      method.replaceChildren();
      if (Array.isArray(alignment.flow)) {
        const flow = element('ol', 'refinement-flow');
        alignment.flow.forEach(step => flow.append(element('li', '', step.label)));
        method.append(flow);
      }
      const details = element('details', 'case-evidence');
      details.append(element('summary', '', 'Method and evidence'));
      if (alignment.title) details.append(element('strong', '', alignment.title));
      addParagraph(details, '', alignment.description, '');
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
    if (!generalization) return;
    generalization.replaceChildren();
    const gallery = data.generalizationGallery;
    const galleryContainer = byId('generalization-gallery');
    let evidenceContainer = generalization;
    if (galleryContainer && gallery?.cases?.length) {
      galleryContainer.replaceChildren();
      if (gallery.title) galleryContainer.append(element('h3', '', gallery.title));
      addParagraph(galleryContainer, '', gallery.caption, 'gallery-caption');
      const grid = element('div', 'generalization-grid');
      const runLinks = element('div', 'evidence-links gallery-run-links');
      if (gallery.gridVideo) addLinks(runLinks, gallery.individualVideos || gallery.cases.map(item =>
        ({label: item.title, href: item.media.src, scope: item.scope})));
      gallery.cases.forEach(item => {
        if (gallery.gridVideo) return;
        const card = element('article', 'generalization-case');
        card.append(element('h4', '', item.title));
        addMedia(card, item.media, {loop: !gallery.gridVideo});
        addParagraph(card, '', item.scope, 'evidence-scope');
        grid.append(card);
      });
      const details = element('details', 'case-evidence generalization-details');
      details.append(element('summary', '', 'Individual runs and evidence'));
      evidenceContainer = element('div', 'generalization-evidence-grid');
      if (gallery.gridVideo) {
        addMedia(galleryContainer, gallery.gridVideo, {loop: true})?.classList.add('generalization-grid-media');
        details.append(runLinks);
      } else galleryContainer.append(grid);
      addParagraph(details, '', gallery.scope, 'evidence-scope');
      addLinks(details, gallery.evidence);
      details.append(evidenceContainer);
      generalization.append(details);
    }
    data.generalization.forEach(item => {
      const article = element('article', 'generalization-item');
      article.append(element('h3', '', item.title));
      addParagraph(article, '', item.claim, '');
      addParagraph(article, '', item.observed, '');
      addParagraph(article, '', item.scope, 'evidence-scope');
      addMedia(article, item.media);
      addLinks(article, item.evidence);
      evidenceContainer.append(article);
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

  function seek(time, stage = null) {
    if (!Number.isFinite(time)) return;
    if (video.readyState < 1) {
      pendingSeek = {time, stage};
      video.preload = 'auto';
      return;
    }
    pendingSeek = null;
    inspectedStage = stage;
    video.currentTime = Math.max(0, Math.min(time, Number.isFinite(video.duration) ? video.duration : time));
    synchronize();
  }

  function seekNode(node, restoreFocus = false) {
    const stage = data.timeline.find(item => item.nodeId === node.nodeId);
    if (!stage || !node.seek?.available) return;
    seek(node.seek.videoTime, stage);
    if (restoreFocus) requestAnimationFrame(() =>
      byId('policy-graph').querySelector(`[data-node-id="${node.nodeId}"]`)?.focus({preventScroll: true}));
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
    selector.classList.add('policy-overview');
    selector.append(element('p', 'assembly-overview-heading', 'Assembly policy'));
    const grid = element('div', 'assembly-overview-grid');
    const edgeCanvas = svg('svg', {class: 'assembly-overview-edges', 'aria-hidden': 'true'});
    grid.append(edgeCanvas);
    const start = element('span', 'assembly-terminal assembly-start', 'Start');
    start.dataset.overviewId = 'START';
    grid.append(start);
    data.pieces.forEach((piece, index) => {
      const button = element('button', 'piece-button assembly-node');
      button.type = 'button';
      button.dataset.piece = piece.name;
      button.dataset.overviewId = piece.name;
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-label', `${pieceLabel(piece.name)} (${piece.name}), inspect its subgraph`);
      button.disabled = !Number.isFinite(piece.videoStart);
      button.title = button.disabled ? 'No recorded observations for this piece yet.' : pieceLabel(piece.name);
      if (piece.shapeSrc) {
        const shape = element('img', 'piece-shape');
        shape.src = piece.shapeSrc;
        shape.alt = '';
        shape.setAttribute('aria-hidden', 'true');
        button.append(shape);
      }
      button.append(element('span', 'piece-number', String(index + 1).padStart(2, '0')));
      button.addEventListener('click', () => seek(piece.videoStart));
      button.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const buttons = Array.from(selector.querySelectorAll('button[data-piece]:not(:disabled)'));
        const current = buttons.indexOf(button);
        const target = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
          (current + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
        buttons[target].focus();
        buttons[target].click();
      });
      grid.append(button);
    });
    const finish = data.graph.nodes.find(node => node.phase === 'finish');
    const finalButton = element('button', 'assembly-terminal', 'Final verify');
    finalButton.type = 'button';
    finalButton.dataset.overviewId = finish.nodeId;
    finalButton.dataset.finalNodeId = finish.nodeId;
    finalButton.disabled = !finish.seek?.available;
    finalButton.title = finish.seek?.reason || 'Jump to final verification';
    if (finish.seek?.available) finalButton.addEventListener('click', () => seekNode(finish));
    grid.append(finalButton);
    selector.append(grid);

    const owner = nodeId => {
      if (nodeId === 'START' || nodeId === finish.nodeId) return nodeId;
      return data.pieces.find(piece => piece.nodeIds.includes(nodeId))?.name;
    };
    const seen = new Set();
    overviewEdges = data.graph.edges.flatMap(edge => {
      const source = owner(edge.source);
      const target = owner(edge.target);
      const key = `${source}:${target}`;
      if (!source || !target || source === target || seen.has(key)) return [];
      seen.add(key);
      return [{source, target}];
    });
    drawAssemblyOverview(0, null);
  }

  function drawAssemblyOverview(simTime, actualStage) {
    const grid = byId('piece-selector').querySelector('.assembly-overview-grid');
    if (!grid) return;
    const columns = window.matchMedia('(max-width: 720px)').matches ? 3 : 7;
    const lastStage = name => [...data.timeline].reverse().find(stage => stage.piece === name && stage.checkpoint);
    const completedNames = data.pieces.filter(piece => piece.complete && simTime >= lastStage(piece.name)?.simEnd).map(piece => piece.name).join(',');
    const renderKey = `${columns}|${grid.clientWidth}|${grid.clientHeight}|${completedNames}|${actualStage?.piece}`;
    if (renderKey === overviewRenderKey) return;
    overviewRenderKey = renderKey;
    grid.style.setProperty('--overview-columns', columns);
    const nodes = Array.from(grid.querySelectorAll('[data-overview-id]'));
    nodes.forEach((node, index) => {
      const row = Math.floor(index / columns);
      const column = row % 2 ? columns - 1 - index % columns : index % columns;
      node.style.gridRow = row + 1;
      node.style.gridColumn = column + 1;
    });
    const bounds = grid.getBoundingClientRect();
    const canvas = grid.querySelector('svg');
    canvas.setAttribute('viewBox', `0 0 ${bounds.width} ${bounds.height}`);
    const defs = svg('defs');
    const arrow = svg('marker', {id: 'assembly-arrow', viewBox: '0 0 8 8', refX: 7, refY: 4,
      markerWidth: 5, markerHeight: 5, orient: 'auto'});
    arrow.append(svg('path', {d: 'M 0 0 L 8 4 L 0 8 z', fill: '#a6b5aa'}));
    defs.append(arrow);
    canvas.replaceChildren(defs);
    overviewEdges.forEach(edge => {
      const source = nodes.find(node => node.dataset.overviewId === edge.source).getBoundingClientRect();
      const target = nodes.find(node => node.dataset.overviewId === edge.target).getBoundingClientRect();
      const sameRow = Math.abs(source.y - target.y) < 3;
      const forward = target.x > source.x;
      const path = sameRow ?
        `M ${source.x - bounds.x + (forward ? source.width : 0)} ${source.y - bounds.y + source.height / 2} H ${target.x - bounds.x + (forward ? 0 : target.width)}` :
        `M ${source.x - bounds.x + source.width / 2} ${source.bottom - bounds.y} V ${target.y - bounds.y}`;
      const sourcePiece = data.pieces.find(piece => piece.name === edge.source);
      const completed = edge.source === 'START' || sourcePiece?.complete && simTime >= lastStage(edge.source)?.simEnd;
      const current = actualStage?.piece === edge.source;
      canvas.append(svg('path', {d: path, class: `assembly-edge${completed ? ' is-complete' : current ? ' is-current' : ''}`,
        'data-source': edge.source, 'data-target': edge.target, 'marker-end': 'url(#assembly-arrow)'}));
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
      const canSeek = node.seek?.available;
      if (canSeek) {
        group.setAttribute('role', 'button');
        group.setAttribute('tabindex', '0');
        group.setAttribute('aria-label', `Jump to ${node.label}${node.seek.mode === 'checkpoint_boundary' ? ', recorded checkpoint boundary' : ''}`);
        group.setAttribute('data-seek-mode', node.seek.mode);
        group.style.cursor = 'pointer';
        group.addEventListener('click', () => seekNode(node));
        group.addEventListener('keydown', event => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            seekNode(node, true);
          }
        });
      } else {
        group.setAttribute('aria-disabled', 'true');
        group.setAttribute('data-disabled-reason', node.seek?.reason || 'Not recorded.');
      }
      if (inspectedStage?.nodeId === node.nodeId) group.classList.add('is-inspected');
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
    const nextLabel = nextPiece ? `Next: ${pieceLabel(nextPiece.name)}` : nextTarget === 'finish_all12' ? 'Final check' : 'Complete';
    [[terminal, nextLabel], [abort, 'Abort on error']].forEach(([position, label]) => {
      const group = svg('g');
      const targetNode = position === terminal ? data.graph.nodes.find(node => node.nodeId === nextTarget) : null;
      if (targetNode && targetNode.type !== 'end') {
        group.setAttribute('data-next-node-id', targetNode.nodeId);
        if (targetNode.nodeId === 'finish_all12') group.setAttribute('data-node-id', targetNode.nodeId);
        group.setAttribute('aria-label', targetNode.label);
        if (targetNode.seek?.available) {
          group.setAttribute('role', 'button');
          group.setAttribute('tabindex', '0');
          group.style.cursor = 'pointer';
          group.addEventListener('click', () => seekNode(targetNode));
          group.addEventListener('keydown', event => {
            if (['Enter', ' '].includes(event.key)) { event.preventDefault(); seekNode(targetNode, true); }
          });
        } else {
          group.setAttribute('aria-disabled', 'true');
          group.setAttribute('data-disabled-reason', targetNode.seek?.reason || 'Not executed.');
          group.append(svg('title', {}, targetNode.seek?.reason || 'Not executed.'));
          label = `${label} · not run`;
        }
      }
      group.append(svg('rect', {x: position.x, y: position.y, width: nodeWidth, height: nodeHeight - 8, rx: 6,
        class: `graph-node-terminal${position === abort && failedTerminal ? ' graph-node is-failed' : ''}`}));
      group.append(svg('text', {x: position.x + 12, y: position.y + 29, class: 'graph-phase'}, label));
      canvas.append(group);
    });
    const description = element('p', 'graph-description');
    const boundary = inspectedStage?.nodeId === activeStage?.nodeId && activeStage.seek?.mode === 'checkpoint_boundary';
    description.textContent = boundary ?
      `Checkpoint at ${activeStage.simEnd.toFixed(2)} s; nearest recorded completion frame ${activeStage.seek.simTime.toFixed(2)} s. No separate sampled motion frame.` :
      activeStage ? `${failedTerminal ? 'Terminal scope verification refused' : activeStage.terminalStatus ? 'Terminal verification' : activeStage.passed === null ? 'Checkpoint not yet recorded' : `Native checkpoint window ${activeStage.simStart.toFixed(2)}–${activeStage.simEnd.toFixed(2)} s`}.` :
      'Topology comes from the executable workflow. Dashed lines share the abort route.';
    const links = element('p', 'evidence-links');
    [['Physical checks', data.evidence.checkpoints], ['Recording timing', data.evidence.media],
      ...(data.evidence.audit ? [['Final audit', data.evidence.audit]] : [])].forEach(([label, href]) => {
      const link = element('a', '', label);
      link.href = href;
      link.target = '_blank';
      link.rel = 'noreferrer';
      links.append(link);
    });
    const details = element('details', 'case-evidence graph-source-details');
    details.append(element('summary', '', 'Execution evidence'));
    if (activeStage) details.append(element('p', '', `Source node: ${activeStage.nodeId}`));
    details.append(links);
    container.replaceChildren(canvas, description, details);
  }

  function synchronize() {
    if (!data || !data.media.mapping.length) return;
    const simTime = simulationTime(video.currentTime);
    byId('policy-sim-time').textContent = `${simTime.toFixed(2)} s`;
    if (inspectedStage && (!video.paused || Math.abs(video.currentTime - inspectedStage.seek.videoTime) > .02)) inspectedStage = null;
    let actualCurrent = data.timeline.find(stage => simTime >= stage.simStart && simTime < stage.simEnd);
    if (!actualCurrent) actualCurrent = [...data.timeline].reverse().find(stage => simTime >= stage.simStart) || data.timeline[0];
    const current = inspectedStage || actualCurrent;
    if (!current) return;
    const pieceName = current.piece;
    const phase = data.graph.nodes.find(node => node.nodeId === current.nodeId);
    const pieceHeading = byId('policy-current-piece');
    if (pieceHeading.dataset.currentPiece !== pieceName) {
      pieceHeading.replaceChildren();
      const piece = data.pieces.find(item => item.name === pieceName);
      if (piece?.shapeSrc) {
        const shape = element('img', 'piece-shape');
        shape.src = piece.shapeSrc;
        shape.alt = '';
        pieceHeading.append(shape);
      }
      pieceHeading.append(element('span', '', pieceName === 'all12' ? 'Final verification' : pieceLabel(pieceName)));
      pieceHeading.dataset.currentPiece = pieceName;
    }
    byId('policy-current-phase').textContent = current.terminalStatus && simTime >= current.simEnd ?
      'Terminal verification refused' : `${phase ? phase.label : titleCase(current.phase)}${inspectedStage?.seek.mode === 'checkpoint_boundary' ? ' · checkpoint boundary' : ''}`;
    const stateKey = data.graph.nodes.filter(node => node.piece === pieceName).map(node => nodeState(node.nodeId, simTime)).join('|') +
      `|${window.matchMedia('(max-width: 720px)').matches ? 2 : 3}|${inspectedStage?.nodeId || ''}`;
    if (pieceName !== displayedPiece || `${current.nodeId}|${stateKey}` !== displayedState) {
      drawGraph(pieceName, simTime, current);
      displayedPiece = pieceName;
      displayedState = `${current.nodeId}|${stateKey}`;
    }
    document.querySelectorAll('#piece-selector button[data-piece]').forEach(button => {
      const piece = data.pieces.find(item => item.name === button.dataset.piece);
      const lastStage = [...data.timeline].reverse().find(stage => stage.piece === piece.name && stage.checkpoint);
      const complete = piece.complete && lastStage && simTime >= lastStage.simEnd;
      const selected = piece.name === pieceName;
      button.classList.toggle('is-current', selected);
      button.classList.toggle('is-complete', Boolean(complete));
      button.setAttribute('aria-pressed', String(selected));
    });
    drawAssemblyOverview(simTime, actualCurrent);
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
      const response = await fetch('data/research.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`Research evidence unavailable (${response.status})`);
      data = await response.json();
      if (!data.graph || !Array.isArray(data.media.mapping)) throw new Error('Unsupported research data format.');
      configureComparison(data.real2sim?.comparison);
      renderStories();
      renderPieceButtons();
      renderStatus();
      if (safeURL(data.media.poster)) video.poster = safeURL(data.media.poster);
      if (safeURL(data.media.src)) video.src = safeURL(data.media.src);
      ['loadedmetadata', 'timeupdate', 'seeking', 'seeked', 'pause', 'ended', 'ratechange'].forEach(event => video.addEventListener(event, synchronize));
      video.addEventListener('loadedmetadata', () => {
        if (pendingSeek) seek(pendingSeek.time, pendingSeek.stage);
      });
      video.addEventListener('play', () => { inspectedStage = null; cancelAnimationFrame(frameRequest); animate(); });
      video.addEventListener('pause', () => cancelAnimationFrame(frameRequest));
      window.addEventListener('resize', synchronize);
      video.addEventListener('error', () => {
        byId('policy-status').textContent = 'The recording could not load. The graph, checkpoint evidence, and examples remain available.';
      });
      synchronize();
    } catch (error) {
      byId('policy-status').textContent = 'The execution evidence could not load. Reload the page to access the recording and checks.';
      byId('policy-current-phase').textContent = 'Unavailable';
      byId('policy-graph').textContent = 'The graph needs the exported execution data.';
      console.error(error);
    }
  }

  initializeComparison();
  if (video) load();
})();
