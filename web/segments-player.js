/* segments-player.js — a segment timeline for any HTML5 <video>.
 *
 *   SegmentsPlayer.mount({ video, data | url, container, assetBase: '', preroll: 2 })
 *
 * Draws, top to bottom: legend with per-class toggles, the segmentation strip, a videogram strip
 * (MGT, image from data.videogram), a waveform strip (1 Hz level from data.tracks.level_db), a
 * time axis, and a detail panel for the segment under the playhead. Clicking anywhere on the strips
 * seeks; clicking a piece seeks `preroll` seconds before its start so the first note is not missed.
 * Keys: [ ] previous/next piece, p n previous/next segment. No dependencies.
 */
(function (global) {
  const COLORS = { music: '#3b82f6', speech: '#f59e0b', applause: '#10b981', silence: '#64748b', other: '#a855f7' };
  const LABELS = { music: 'Music', speech: 'Talk', applause: 'Applause', silence: 'Silence', other: 'Other' };
  const SPEAKER_COLORS = ['#e11d48', '#0ea5e9', '#84cc16', '#f97316', '#8b5cf6', '#14b8a6', '#eab308', '#ec4899', '#22c55e', '#6366f1', '#f43f5e', '#06b6d4'];
  const speakerColor = (id) => SPEAKER_COLORS[(parseInt(String(id).replace(/\D/g, ''), 10) || 0) % SPEAKER_COLORS.length];
  const speakerName = (data, id) => { const sp = data.speakers && data.speakers.speakers && data.speakers.speakers[id]; return (sp && sp.name) || id; };
  const speakerRole = (data, id) => { const sp = data.speakers && data.speakers.speakers && data.speakers.speakers[id]; return (sp && sp.role) || (data.speakers && data.speakers.roles && data.speakers.roles[id]) || ''; };

  function fmt(t) {
    t = Math.max(0, Math.floor(t)); const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(s).padStart(2, '0');
  }
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v); else if (v != null) e.setAttribute(k, v);
    }
    for (const k of kids) if (k != null && k !== false) e.append(k.nodeType ? k : document.createTextNode(String(k)));
    return e;
  }
  const pct = (v) => (v * 100).toFixed(3) + '%';
  const clean = (v) => v && v !== '–' && v !== '-' ? v : null;

  function mount(opts) {
    const start = (data) => render(data, opts);
    if (opts.data) return start(opts.data);
    return fetch(opts.url).then(r => r.json()).then(start);
  }

  function drawWave(canvas, level, segments, dur, hidden) {
    const W = canvas.width = canvas.clientWidth * (window.devicePixelRatio || 1);
    const H = canvas.height = canvas.clientHeight * (window.devicePixelRatio || 1);
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, W, H);
    if (!level || !level.length) return;
    const lo = -60, hi = Math.max(...level.filter(Number.isFinite));
    const n = level.length, hop = dur / n;
    const colorAt = (t) => { const s = segments.find(x => t >= x.start && t < x.end); return s ? [COLORS[s.kind], hidden && hidden.has(s.kind) ? 0.2 : 0.85] : ['#888', 0.5]; };
    const colPer = Math.max(1, Math.ceil(n / W));
    for (let x = 0; x < W; x++) {
      const i0 = Math.floor(x / W * n), i1 = Math.min(n, i0 + colPer);
      let v = -Infinity; for (let i = i0; i < i1; i++) if (level[i] > v) v = level[i];
      const a = Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
      const h = Math.max(1, a * H);
      const [col, alpha] = colorAt(i0 * hop); ctx.fillStyle = col; ctx.globalAlpha = alpha;
      ctx.fillRect(x, (H - h) / 2, 1, h);
    }
    ctx.globalAlpha = 1;
  }

  function detail(s, data, assetBase, tNow) {
    const piece = s.piece_index ? data.pieces[s.piece_index - 1] : null;
    const part = (data.parts || []).find(p => p.kind === 'part' && tNow >= p.start && tNow < p.end) || null;
    const turn = ((data.speakers && data.speakers.turns) || []).find(t => tNow >= t.start && tNow < t.end) || null;
    const box = el('div', { class: 'cs-detail-inner' });
    const media = s.thumbnail ? el('img', { src: assetBase + s.thumbnail, alt: '' }) : el('div', { class: 'cs-noimg', style: `background:${COLORS[s.kind]}` });
    const head = el('div', { class: 'cs-head' },
      el('span', { class: 'cs-pill', style: `background:${COLORS[s.kind]}` }, LABELS[s.kind]),
      el('span', { class: 'cs-time' }, `${fmt(s.start)} – ${fmt(s.end)}`),
      el('span', { class: 'cs-dur' }, fmt(s.end - s.start)));
    const body = el('div', { class: 'cs-body' }, head);
    if (piece) {
      const pl = piece.plan || {};
      const work = clean(pl.work), act = clean(pl.act), who = clean(pl.performers), comp = clean(pl.composer);
      body.append(el('h3', null, work || act || `Piece ${piece.index}`));
      if (who || (act && work)) body.append(el('p', { class: 'cs-who' }, [who, act && work ? act : null].filter(Boolean).join(' · ')));
      const rows = [];
      if (comp && comp !== who) rows.push(['Composer / writer', comp]);
      if (pl.nr) rows.push(['Programme', `#${pl.nr}` + (pl.match && pl.match !== 'name' ? ` · matched by ${pl.match}` : ' · named in the introduction')]);
      const perf = piece.performers;
      rows.push(['On stage', perf && perf.estimate != null ? `${perf.estimate}` + (perf.low !== perf.estimate ? ` (widest shot; closer shots show ${perf.low})` : '') : 'n/a']);
      if (piece.camera && piece.camera.shots != null) rows.push(['Camera', `${piece.camera.shots} shot${piece.camera.shots === 1 ? '' : 's'}` + (piece.camera.moving_share != null ? ` · moving ${Math.round(piece.camera.moving_share * 100)}% of the time` : '')]);
      rows.push(['Heard as', piece.ensemble + (piece.instruments.length ? ' · ' + piece.instruments.slice(0, 4).map(i => i.label).join(', ') : '')]);
      if (piece.genres && piece.genres.length) rows.push(['Genre tags', piece.genres.slice(0, 3).map(i => i.label).join(', ')]);
      if (piece.singing_p >= 0.1) rows.push(['Singing', Math.round(piece.singing_p * 100) + '%']);
      const m = piece.music || {};
      const tk = [];
      if (m.tempo_bpm != null) tk.push(`${m.tempo_bpm.toFixed(0)} bpm` + (m.tempo_reliable ? '' : ' (weak pulse)'));
      if (m.key) tk.push(m.key + (m.key_reliable ? '' : ' (uncertain)'));
      if (tk.length) rows.push(['Tempo / key', tk.join(' · ')]);
      if (piece.performer_names_guess && piece.performer_names_guess.length) rows.push(['Names heard', piece.performer_names_guess.join(', ')]);
      if (piece.internal_cues && piece.internal_cues.length) rows.push(['Changes inside', piece.internal_cues.map(c => `${fmt(c.t)} (${c.why})`).join(', ')]);
      body.append(el('dl', { class: 'cs-dl' }, ...rows.flatMap(([k, v]) => [el('dt', null, k), el('dd', null, v)])));
      if (piece.intro && piece.intro.text) body.append(el('details', null, el('summary', null, 'Introduction (transcript)'), el('p', { class: 'cs-intro' }, piece.intro.text)));
    } else if (part || turn) {
      if (part) {
        body.append(el('h3', null, `${part.index}. ${part.title || 'Part ' + part.index}`), el('p', { class: 'cs-who' }, `${fmt(part.start)} – ${fmt(part.end)} · ${fmt(part.duration)}` + (part.plan && part.plan.performers ? ` · ${part.plan.performers}` : '')));
      }
      const rows = [];
      if (turn) rows.push(['Speaking now', el('span', null, el('i', { class: 'cs-swatch', style: `background:${speakerColor(turn.speaker)}` }), ` ${speakerName(data, turn.speaker)}` + (speakerRole(data, turn.speaker) ? ` (${speakerRole(data, turn.speaker)})` : '') + ` · ${fmt(turn.start)}–${fmt(turn.end)}`)]);
      if (part && part.speakers) rows.push(['Floor in this part', Object.entries(part.speakers).slice(0, 4).map(([id, sh]) => `${speakerName(data, id)} ${Math.round(sh * 100)}%`).join(' · ')]);
      if (part && part.performers && part.performers.estimate != null) rows.push(['On stage', `${part.performers.estimate}`]);
      if (part && part.camera && part.camera.shots != null) rows.push(['Camera', `${part.camera.shots} shot${part.camera.shots === 1 ? '' : 's'} · moving ${Math.round((part.camera.moving_share || 0) * 100)}% of the time`]);
      if (s.kind !== 'speech') rows.push(['Now', LABELS[s.kind]]);
      body.append(el('dl', { class: 'cs-dl' }, ...rows.flatMap(([k, v]) => [el('dt', null, k), el('dd', null, v)])));
      if (turn && turn.text) body.append(el('p', { class: 'cs-intro' }, turn.text.length > 600 ? turn.text.slice(0, 600) + '…' : turn.text));
      else if (s.transcript) body.append(el('p', { class: 'cs-intro' }, s.transcript.length > 600 ? s.transcript.slice(0, 600) + '…' : s.transcript));
    } else {
      body.append(el('h3', null, s.kind === 'speech' ? 'Talk' : (s.title || LABELS[s.kind])));
      if (s.transcript) body.append(el('p', { class: 'cs-intro' }, s.transcript));
      else if (s.kind === 'applause') body.append(el('p', { class: 'cs-who' }, 'Applause'));
    }
    box.append(media, body);
    return box;
  }

  function fmtBytes(b) { if (b == null) return null; const u = ['B', 'kB', 'MB', 'GB']; let i = 0; while (b >= 1000 && i < u.length - 1) { b /= 1000; i++; } return `${b.toFixed(i ? 1 : 0)} ${u[i]}`; }

  function metadataBox(data) {
    const t = (data.video && data.video.tech) || {}, m = data.metadata || {};
    const rows = [
      ['File', t.file], ['Container', t.container], ['Size', fmtBytes(t.size_bytes)], ['Duration', t.duration_s != null ? fmt(t.duration_s) : null],
      ['Picture', t.width && t.height ? `${t.width} × ${t.height} px` + (t.fps ? ` · ${t.fps} fps` : '') : null],
      ['Video codec', [t.video_codec, t.profile].filter(Boolean).join(' · ') || null],
      ['Pixel format / bit depth', [t.pix_fmt, t.bit_depth ? `${t.bit_depth}-bit` : null].filter(Boolean).join(' · ') || null],
      ['Colour', t.color], ['Bitrate', [t.bitrate_kbps ? `${t.bitrate_kbps} kb/s total` : null, t.video_bitrate_kbps ? `${t.video_bitrate_kbps} kb/s video` : null, t.audio_bitrate_kbps ? `${t.audio_bitrate_kbps} kb/s audio` : null].filter(Boolean).join(' · ') || null],
      ['Audio', [t.audio_codec, t.sample_rate_hz ? `${t.sample_rate_hz} Hz` : null, t.channel_layout || (t.channels ? `${t.channels} ch` : null), t.audio_bit_depth ? `${t.audio_bit_depth}-bit` : null].filter(Boolean).join(' · ') || null],
      ['Created', t.created], ['Analysed', data.generated],
    ].filter(r => r[1]);
    const dl = el('dl', { class: 'cs-dl' }, ...rows.flatMap(([k, v]) => [el('dt', null, k), el('dd', null, v)]));
    const priv = m.privacy || {};
    const privRow = el('div', { class: 'cs-priv' },
      el('span', { class: 'cs-dot cs-dot-' + (priv.level || 'yellow') }), el('b', null, `Privacy: ${priv.level || 'not set'}`),
      priv.suggested ? el('span', { class: 'cs-muted' }, ' (suggested by the analysis, not reviewed)') : null,
      priv.reasons && priv.reasons.length ? el('span', { class: 'cs-muted' }, ' · ' + priv.reasons.join('; ')) : null,
      priv.note ? el('span', { class: 'cs-muted' }, ' · ' + priv.note) : null);
    const lic = el('p', { class: 'cs-lic' }, el('b', null, 'License: '), m.license ? (m.license_url ? el('a', { href: m.license_url, target: '_blank', rel: 'noopener' }, m.license) : m.license) : 'not stated', m.rights_holder ? ` · rights holder: ${m.rights_holder}` : '');
    const cr = (m.copyrights || []).length ? el('table', { class: 'cs-table' },
      el('thead', null, el('tr', null, ...['#', 'Work', 'Composer / writer', 'Performers', 'Status', 'Note'].map(h => el('th', null, h)))),
      el('tbody', null, ...m.copyrights.map(c => el('tr', null, el('td', null, c.nr || (c.piece ? `p${c.piece}` : '')), el('td', null, c.work || '—'), el('td', null, c.composer || '—'), el('td', null, c.performers || '—'), el('td', { class: 'cs-status cs-status-' + String(c.status || 'unknown').replace(/\W+/g, '-') }, c.status || 'unknown'), el('td', null, c.note || '')))))
      : el('p', { class: 'cs-muted' }, 'No works listed.');
    return el('details', { class: 'cs-meta' }, el('summary', null, 'Technical metadata, license and rights'),
      el('div', { class: 'cs-meta-grid' }, el('div', null, el('h4', null, 'Recording'), dl), el('div', null, el('h4', null, 'Rights'), lic, privRow, el('h4', null, 'Known copyrights'), cr, m.notes ? el('p', { class: 'cs-muted' }, m.notes) : null)));
  }

  // ---------- research view (hidden by default): generic tracks and tiers from data.research
  const TIER_COLORS = ['#e11d48', '#0ea5e9', '#84cc16', '#f97316', '#8b5cf6', '#14b8a6', '#eab308', '#ec4899'];
  function drawCurve(canvas, track, dur) {
    const W = canvas.width = canvas.clientWidth * (window.devicePixelRatio || 1), H = canvas.height = canvas.clientHeight * (window.devicePixelRatio || 1);
    const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, W, H);
    const v = track.values || []; if (!v.length) return;
    const finite = v.filter(x => x != null && Number.isFinite(x));
    const [lo, hi] = track.range || [Math.min(...finite), Math.max(...finite)];
    const hop = track.hop_s || 1, n = v.length;
    ctx.strokeStyle = getComputedStyle(canvas).getPropertyValue('--cs-fg') || '#888'; ctx.lineWidth = 1; ctx.beginPath(); let pen = false;
    for (let x = 0; x < W; x++) {
      const i = Math.min(n - 1, Math.floor(x / W * (dur / hop)));
      const y = v[i]; if (y == null || !Number.isFinite(y)) { pen = false; continue; }
      const py = H - 2 - Math.max(0, Math.min(1, (y - lo) / ((hi - lo) || 1))) * (H - 4);
      if (!pen) { ctx.moveTo(x, py); pen = true; } else ctx.lineTo(x, py);
    }
    ctx.stroke();
  }
  function stateRow(track, dur) {
    const row = el('div', { class: 'cs-lane-states' });
    const st = track.states || [], hop = track.hop_s || 1, pal = track.palette || {};
    let i = 0;
    while (i < st.length) {
      let j = i; while (j + 1 < st.length && st[j + 1] === st[i]) j++;
      if (st[i] != null) row.append(el('i', { style: `left:${pct(i * hop / dur)};width:${pct(((j - i + 1) * hop) / dur)};background:${pal[st[i]] || speakerColor(st[i])}`, title: String(st[i]) }));
      i = j + 1;
    }
    return row;
  }
  function tierRow(tier, dur, k, video) {
    const row = el('div', { class: 'cs-tier' });
    const color = TIER_COLORS[k % TIER_COLORS.length];
    (tier.items || []).forEach(it => {
      const w = Math.max(0.0008, ((it.end ?? it.start) - it.start) / dur);
      const b = el('i', { class: tier.kind === 'point' || (it.end ?? it.start) <= it.start ? 'cs-tier-pt' : 'cs-tier-iv', style: `left:${pct(it.start / dur)};width:${pct(w)};background:${color}`,
        title: `${fmt(it.start)}${(it.end ?? it.start) > it.start ? '–' + fmt(it.end) : ''} ${it.label || ''}`, onclick: (e) => { e.stopPropagation(); video.currentTime = it.start; } });
      row.append(b);
    });
    return row;
  }
  function csvOf(data, t0, t1) {
    const lines = ['tier,start_s,end_s,label'];
    for (const tier of (data.research && data.research.tiers) || []) for (const it of tier.items || []) if ((it.end ?? it.start) >= t0 && it.start <= t1) lines.push(`${tier.id},${it.start},${it.end ?? it.start},"${String(it.label || '').replace(/"/g, '""')}"`);
    for (const tr of (data.research && data.research.tracks) || []) if (tr.kind === 'curve') { const hop = tr.hop_s || 1; tr.values.forEach((v, i) => { const t = i * hop; if (t >= t0 && t <= t1) lines.push(`track:${tr.id},${t},${t},${v == null ? '' : v}`); }); }
    return lines.join('\n');
  }

  function researchPanel(data, video, dur, playheadHost) {
    const R = data.research || { tracks: [], tiers: [] };
    const box = el('details', { class: 'cs-meta cs-research' }, el('summary', null, 'Advanced view: how the analysis works'));
    const lanes = el('div', { class: 'cs-lanes' });
    const redraws = [];
    for (const t of R.tracks) {
      if (t.kind === 'image' && t.image === data.videogram) continue;                     // already in the main view
      const lane = el('div', { class: 'cs-lane' }, el('span', { class: 'cs-lane-label' }, t.label + (t.unit ? ` (${t.unit})` : '')));
      if (t.kind === 'curve') { const c = el('canvas', { class: 'cs-lane-canvas' }); lane.append(c); redraws.push(() => drawCurve(c, t, dur)); }
      else if (t.kind === 'state') lane.append(stateRow(t, dur));
      else if (t.kind === 'image') lane.append(el('img', { class: 'cs-lane-img', src: (playheadHost.assetBase || '') + t.image, alt: t.label }));
      lanes.append(lane);
    }
    R.tiers.forEach((tier, k) => {
      if (['segments'].includes(tier.id)) return;                                            // the waveform colours already show it
      const lane = el('div', { class: 'cs-lane' }, el('span', { class: 'cs-lane-label' }, `${tier.label} · ${(tier.items || []).length}` + (tier.source ? ` · ${tier.source}` : '')), tierRow(tier, dur, k, video));
      lanes.append(lane);
    });
    const ph = el('div', { class: 'cs-playhead' });
    const stack = el('div', { class: 'cs-stack cs-stack-research', onclick: (e) => { const r = stack.getBoundingClientRect(); video.currentTime = (e.clientX - r.left) / r.width * dur; } }, lanes, ph);
    const tools = el('div', { class: 'cs-tools' },
      el('button', { type: 'button', onclick: () => { const t = video.currentTime; const u = location.href.split('#')[0] + `#t=${t.toFixed(1)}`; navigator.clipboard && navigator.clipboard.writeText(u); prompt('Link to this moment', u); } }, 'Link to this moment'),
      el('button', { type: 'button', onclick: () => { const s = data.segments.find(x => video.currentTime >= x.start && video.currentTime < x.end) || { start: 0, end: dur }; const blob = new Blob([csvOf(data, s.start, s.end)], { type: 'text/csv' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${(data.title || 'recording').replace(/\W+/g, '_')}_${fmt(s.start).replace(/:/g, '-')}.csv`; a.click(); } }, 'Export this segment as CSV'),
      el('span', { class: 'cs-muted' }, ` ${R.tracks.length} tracks · ${R.tiers.length} tiers · additions via avsegmenter add-track / add-tier`));
    const inner = el('div', { class: 'cs-research-inner' },
      el('p', { class: 'cs-muted cs-research-intro' }, 'Every layer below is data from the analysis or added by a researcher; the main view is a selection of it. Click a lane to seek.'), stack, tools);
    box.append(inner);
    box.addEventListener('toggle', () => { if (box.open) redraws.forEach(f => f()); });
    return { box, redraws, playhead: ph };
  }

  function render(data, opts) {
    const video = opts.video, container = opts.container, assetBase = opts.assetBase || '';
    const preroll = opts.preroll == null ? 2 : opts.preroll;
    const dur = data.video.duration;
    const state = { hidden: new Set(), cur: null };
    container.classList.add('cs-root');

    const seek = (s) => { video.currentTime = Math.max(0, s.start - (s.kind === 'music' ? preroll : 0)); if (video.paused && video.play) video.play().catch(() => {}); };

    const spk = (data.speakers && data.speakers.speakers) ? Object.keys(data.speakers.speakers) : [];
    const speakerLegend = spk.length ? el('div', { class: 'cs-legend cs-legend-spk' }, ...spk.map(id => el('span', { class: 'cs-leg' }, el('i', { style: `background:${speakerColor(id)}` }), speakerName(data, id), el('small', null, ` ${speakerRole(data, id) ? speakerRole(data, id) + ' · ' : ''}${fmt(data.speakers.speakers[id].total_s)}`)))) : null;
    const legend = el('div', { class: 'cs-legend' }, ...Object.keys(COLORS).map(k => el('label', { class: 'cs-leg' },
      el('input', { type: 'checkbox', checked: 'checked', id: 'cs-toggle-' + k, onchange: (e) => { e.target.checked ? state.hidden.delete(k) : state.hidden.add(k); refresh(); } }),
      el('i', { style: `background:${COLORS[k]}` }), LABELS[k], data.summary ? el('small', null, ` ${fmt(data.summary[k] || 0)}`) : null)));

    const blocks = data.segments.map(s => {
      const b = el('div', { class: 'cs-block', title: `${fmt(s.start)}–${fmt(s.end)} ${s.title || LABELS[s.kind]}`,
        style: `left:${pct(s.start / dur)};width:${pct((s.end - s.start) / dur)}`, onclick: (e) => { e.stopPropagation(); seek(s); } });
      b.dataset.id = s.id; return b;
    });
    const realParts = (data.parts || []).filter(p => p.kind === 'part');
    const numbered = data.pieces.length ? data.pieces : realParts;
    const pieceMarks = numbered.map(p => el('span', { class: 'cs-num', style: `left:${pct((p.start + p.end) / 2 / dur)}`, title: p.title || '' }, p.index));
    const partMarks = (realParts.length > 1 || !data.pieces.length) ? realParts.map(p => el('i', { class: 'cs-part', style: `left:${pct(p.start / dur)};width:${pct((p.end - p.start) / dur)}`, title: `${p.index}. ${p.title || ''}` }, el('b', null, `${p.index}. ${p.title || ''}`))) : [];
    const turns = (data.speakers && data.speakers.turns) || [];
    const turnBlocks = turns.map(t => el('div', { class: 'cs-turn', title: `${fmt(t.start)}–${fmt(t.end)} ${speakerName(data, t.speaker)}`, style: `left:${pct(t.start / dur)};width:${pct(Math.max(0.0005, (t.end - t.start) / dur))};background:${speakerColor(t.speaker)}`, onclick: (e) => { e.stopPropagation(); video.currentTime = t.start; if (video.paused && video.play) video.play().catch(() => {}); } }));
    const speakerRow = turns.length ? el('div', { class: 'cs-speakers' }, ...turnBlocks) : null;
    const cutMarks = (data.camera && data.camera.cuts ? data.camera.cuts : []).map(t => el('i', { class: 'cs-cut', style: `left:${pct(t / dur)}`, title: 'camera cut ' + fmt(t) }));
    const cutRow = el('div', { class: 'cs-cuts' }, ...cutMarks);
    const vgram = data.videogram ? el('div', { class: 'cs-vgram' }, el('img', { src: assetBase + data.videogram, alt: 'videogram' })) : null;
    const wave = el('canvas', { class: 'cs-wave' });
    const waveBox = el('div', { class: 'cs-wavebox' }, wave, el('div', { class: 'cs-overlay' }, ...blocks, ...pieceMarks));
    const playhead = el('div', { class: 'cs-playhead' });
    const partRow = partMarks.length ? el('div', { class: 'cs-parts' }, ...partMarks) : null;
    const stack = el('div', { class: 'cs-stack', onclick: (e) => { const r = stack.getBoundingClientRect(); video.currentTime = (e.clientX - r.left) / r.width * dur; } }, partRow, cutRow, vgram, speakerRow, waveBox, playhead);
    const ticks = el('div', { class: 'cs-ticks' });
    const step = dur > 3600 ? 600 : 300;
    for (let t = 0; t < dur; t += step) ticks.append(el('span', { style: `left:${pct(t / dur)}` }, fmt(t)));

    const nav = el('div', { class: 'cs-nav' },
      el('button', { type: 'button', id: 'cs-prev', onclick: () => jump(-1) }, '‹ previous'),
      el('span', { class: 'cs-navlabel', id: 'cs-navlabel' }, ''),
      el('button', { type: 'button', id: 'cs-next', onclick: () => jump(1) }, 'next ›'));
    const panel = el('div', { class: 'cs-detail' });
    const research = researchPanel(data, video, dur, { assetBase });
    container.append(legend, speakerLegend, stack, ticks, nav, panel, research.box, metadataBox(data));
    if (/advanced/.test(location.hash)) research.box.open = true;
    const m = /[#&]t=([\d.]+)/.exec(location.hash); if (m) { const jump = () => { video.currentTime = parseFloat(m[1]); }; video.readyState >= 1 ? jump() : video.addEventListener('loadedmetadata', jump, { once: true }); }

    const level = data.tracks && data.tracks.level_db;
    const redraw = () => { drawWave(wave, level, data.segments, dur, state.hidden); if (research.box.open) research.redraws.forEach(f => f()); };
    redraw(); window.addEventListener('resize', redraw);

    function refresh() {
      redraw();
    }
    function current() { const t = video.currentTime || 0; return data.segments.find(x => t >= x.start && t < x.end) || null; }
    function jump(dir) {
      const t = video.currentTime || 0;
      const list = data.segments.filter(x => !state.hidden.has(x.kind));
      const s = dir > 0 ? list.find(x => x.start > t + 0.5) : [...list].reverse().find(x => x.start < t - 2);
      if (s) seek(s); else if (dir < 0) video.currentTime = 0;
    }
    function tick() {
      const t = video.currentTime || 0;
      playhead.style.left = pct(t / dur); research.playhead.style.left = pct(t / dur);
      const s = current(); const id = s ? s.id : null;
      const turn = ((data.speakers && data.speakers.turns) || []).find(x => t >= x.start && t < x.end);
      const key = id + '|' + (turn ? turn.start : '');
      if (key !== state.cur) {
        state.cur = key;
        blocks.forEach(b => b.classList.toggle('cs-on', b.dataset.id === id));
        panel.replaceChildren(s ? detail(s, data, assetBase, t) : el('p', { class: 'cs-who' }, 'Press play, or click the timeline.'));
        const i = s ? data.segments.indexOf(s) : -1;
        document.getElementById('cs-navlabel').textContent = s ? `${i + 1} / ${data.segments.length}` : '';
      }
    }
    video.addEventListener('timeupdate', tick); video.addEventListener('seeked', tick); video.addEventListener('loadedmetadata', tick); tick();

    const pieceSegs = data.pieces.length ? data.segments.filter(s => s.kind === 'music') : realParts.map(p => ({ start: p.start, end: p.end, kind: 'part' }));
    document.addEventListener('keydown', (e) => {
      if (e.target && /input|textarea|select|button/i.test(e.target.tagName)) return;
      const t = video.currentTime;
      if (e.key === ']') { const n = pieceSegs.find(x => x.start > t + 1); if (n) seek(n); }
      if (e.key === '[') { const p = [...pieceSegs].reverse().find(x => x.start < t - 3); if (p) seek(p); else video.currentTime = 0; }
      if (e.key === 'n') jump(1);
      if (e.key === 'p') jump(-1);
    });
    return { refresh, tick, seek,
      addTier(tier) { (data.research = data.research || { tracks: [], tiers: [] }).tiers.push(tier); const lanes = research.box.querySelector('.cs-lanes'); lanes.append(el('div', { class: 'cs-lane' }, el('span', { class: 'cs-lane-label' }, tier.label), tierRow(tier, dur, data.research.tiers.length - 1, video))); },
      addTrack(track) { (data.research = data.research || { tracks: [], tiers: [] }).tracks.push(track); const lanes = research.box.querySelector('.cs-lanes'); const lane = el('div', { class: 'cs-lane' }, el('span', { class: 'cs-lane-label' }, track.label)); if (track.kind === 'curve') { const c = el('canvas', { class: 'cs-lane-canvas' }); lane.append(c); research.redraws.push(() => drawCurve(c, track, dur)); } else if (track.kind === 'state') lane.append(stateRow(track, dur)); else if (track.kind === 'image') lane.append(el('img', { class: 'cs-lane-img', src: track.image })); lanes.append(lane); if (research.box.open) research.redraws.forEach(f => f()); },
      data };
  }

  const CSS = `
.cs-root{--cs-fg:#0f172a;--cs-muted:#475569;--cs-card:#ffffff;--cs-border:#e2e8f0;--cs-accent:#4c6239;--cs-accent-fg:#ffffff;--cs-mark:#b60000;color:var(--cs-fg);font:15px/1.5 Helvetica,Arial,sans-serif}
:root[data-theme="dark"] .cs-root{--cs-fg:#e2e8f0;--cs-muted:#94a3b8;--cs-card:#1e293b;--cs-border:#334155;--cs-accent:#8fae76;--cs-accent-fg:#0f172a;--cs-mark:#ff6b6b}
.cs-legend{display:flex;flex-wrap:wrap;gap:10px 18px;margin:12px 0 8px;font-size:13px}
.cs-leg{display:inline-flex;align-items:center;gap:6px;cursor:pointer;color:var(--cs-muted)}
.cs-leg i{display:inline-block;width:12px;height:12px;border-radius:3px}.cs-leg small{color:var(--cs-muted)}
.cs-stack{position:relative;border:1px solid var(--cs-border);border-radius:8px;overflow:hidden;background:var(--cs-card);cursor:crosshair}
.cs-wavebox{position:relative}
.cs-overlay{position:absolute;inset:0}
.cs-block{position:absolute;top:0;bottom:0;min-width:2px;cursor:pointer;border-bottom:3px solid transparent;box-sizing:border-box}
.cs-block:hover{background:rgba(127,127,127,.15)}
.cs-block.cs-on{border-bottom-color:var(--cs-accent)}
.cs-num{position:absolute;top:2px;transform:translateX(-50%);font-size:11px;font-weight:700;color:#fff;text-shadow:0 0 3px #000,0 0 1px #000;pointer-events:none;font-family:Helvetica,Arial,sans-serif}
.cs-parts{position:relative;height:16px;background:var(--cs-card)} .cs-part{position:absolute;top:2px;bottom:2px;background:var(--cs-accent);opacity:.3;border-radius:2px;overflow:hidden;white-space:nowrap} .cs-part b{font-size:10px;line-height:12px;padding:0 4px;color:var(--cs-card);opacity:1;font-weight:600}
.cs-speakers{position:relative;height:14px;border-top:1px solid var(--cs-border);background:var(--cs-card)} .cs-turn{position:absolute;top:2px;bottom:2px;cursor:pointer;opacity:.9} .cs-turn:hover{opacity:1;filter:brightness(1.2)}
.cs-legend-spk{margin-top:-2px} .cs-swatch{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:-1px}
.cs-cuts{position:relative;height:5px;background:var(--cs-card)}.cs-cut{position:absolute;top:0;bottom:0;width:1px;background:var(--cs-mark);opacity:.8}
.cs-vgram{height:56px;border-top:1px solid var(--cs-border)}.cs-vgram img{width:100%;height:100%;display:block;object-fit:fill;image-rendering:auto}
.cs-wave{display:block;width:100%;height:64px;border-top:1px solid var(--cs-border)}
.cs-playhead{position:absolute;top:0;bottom:0;width:2px;background:var(--cs-mark);pointer-events:none;box-shadow:0 0 4px rgba(0,0,0,.6)}
.cs-ticks{position:relative;height:18px;font-size:11px;color:var(--cs-muted)}.cs-ticks span{position:absolute;transform:translateX(-50%)}
.cs-nav{display:flex;align-items:center;gap:12px;margin:10px 0 6px}
.cs-nav button{background:var(--cs-accent);color:var(--cs-accent-fg);border:1px solid var(--cs-accent);border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit;font-size:14px}
.cs-nav button:hover{filter:brightness(1.1)}.cs-navlabel{color:var(--cs-muted);font-size:12px;font-variant-numeric:tabular-nums}
.cs-detail{background:var(--cs-card);border:1px solid var(--cs-border);border-radius:12px;padding:14px;min-height:120px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.cs-detail-inner{display:grid;grid-template-columns:220px 1fr;gap:16px}
.cs-detail img,.cs-noimg{width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:4px;display:block;background:#000}
.cs-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px;font-size:12px;color:var(--cs-muted)}
.cs-pill{color:#fff;font-weight:700;font-size:11px;letter-spacing:.04em;text-transform:uppercase;padding:2px 7px;border-radius:999px}
.cs-time{font-variant-numeric:tabular-nums;color:var(--cs-fg)}
.cs-detail h3{margin:6px 0 2px;font-size:20px;font-weight:400}
.cs-who{margin:0 0 8px;color:var(--cs-muted)}
.cs-dl{display:grid;grid-template-columns:max-content 1fr;gap:3px 12px;margin:6px 0;font-size:13px}
.cs-dl dt{color:var(--cs-muted)}.cs-dl dd{margin:0}
.cs-detail details{font-size:13px;color:var(--cs-muted);margin-top:6px}.cs-detail summary{cursor:pointer;color:var(--cs-fg)}
.cs-intro{margin:6px 0 0;font-style:italic;color:var(--cs-muted)}
.cs-research-inner{margin-top:10px} .cs-research-intro{margin:0 0 8px;font-size:13px}
.cs-stack-research{cursor:crosshair} .cs-lanes{display:grid}
.cs-lane{position:relative;border-top:1px solid var(--cs-border);padding-top:14px;min-height:30px;background:var(--cs-card)}
.cs-lane-label{position:absolute;top:1px;left:6px;font-size:10px;letter-spacing:.04em;text-transform:uppercase;color:var(--cs-muted);pointer-events:none;z-index:2}
.cs-lane-canvas{display:block;width:100%;height:44px;--cs-fg:var(--cs-fg)} .cs-lane-img{display:block;width:100%;height:56px;object-fit:fill}
.cs-lane-states{position:relative;height:14px} .cs-lane-states i{position:absolute;top:0;bottom:0}
.cs-tier{position:relative;height:16px} .cs-tier-iv{position:absolute;top:2px;bottom:2px;opacity:.85;cursor:pointer;border-radius:2px} .cs-tier-pt{position:absolute;top:0;bottom:0;width:2px!important;opacity:.9;cursor:pointer}
.cs-tools{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px;font-size:12px} .cs-tools button{background:transparent;color:var(--cs-fg);border:none;border-bottom:1px solid var(--cs-accent);padding:2px 0;cursor:pointer;font:inherit;font-size:13px}
.cs-meta{margin-top:12px;background:var(--cs-card);border:1px solid var(--cs-border);border-radius:12px;padding:10px 14px;font-size:13px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.cs-meta summary{cursor:pointer;font-weight:400;font-size:16px}
.cs-meta-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:10px}
.cs-meta h4{margin:6px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--cs-muted)}
.cs-muted{color:var(--cs-muted)} .cs-lic{margin:0 0 6px} .cs-priv{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:8px}
.cs-dot{display:inline-block;width:12px;height:12px;border-radius:50%} .cs-dot-green{background:#22c55e} .cs-dot-yellow{background:#eab308} .cs-dot-red{background:#ef4444}
.cs-table{width:100%;border-collapse:collapse;font-size:12px} .cs-table th{text-align:left;color:var(--cs-muted);font-weight:500;padding:3px 6px 3px 0;border-bottom:1px solid var(--cs-border)} .cs-table td{padding:4px 6px 4px 0;border-bottom:1px solid var(--cs-border);vertical-align:top}
.cs-status-public-domain{color:#22c55e} .cs-status-protected{color:#ef4444} .cs-status-own-work,.cs-status-performers-own-work{color:#3b82f6}
@media (max-width:640px){.cs-detail-inner{grid-template-columns:1fr}.cs-meta-grid{grid-template-columns:1fr}}
`;
  function injectCss() { if (document.getElementById('cs-css')) return; document.head.append(el('style', { id: 'cs-css' }, CSS)); }

  global.SegmentsPlayer = global.ConcertSegments = { mount: (o) => { injectCss(); return mount(o); }, COLORS, LABELS, fmt };
})(window);
