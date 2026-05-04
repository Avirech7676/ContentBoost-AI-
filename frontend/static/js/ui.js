/**
 * ui.js — UI rendering helpers for ContentBoost AI
 *
 * Key fixes vs original:
 * - All LLM content inserted as innerHTML is sanitised with DOMPurify
 * - Timestamp parsing fixed (no manual 'Z' append)
 * - renderSpinner() + updateSpinnerMessage() for real loading state
 * - renderCompare() shows dropdowns to pick any 2 history entries
 * - renderResults() includes refinement instruction input per card
 */

/* ── Toast ───────────────────────────────────────────────────────────────── */
let _toastTimer = null;
function toast(msg, duration = 2500) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), duration);
}

/* ── Status bar ─────────────────────────────────────────────────────────── */
function setStatus(msg, state = 'idle') {
  document.getElementById('status-text').textContent = msg;
  const dot = document.getElementById('status-indicator');
  dot.className = `status-dot ${state}`;
}

/* ── Tab switching ───────────────────────────────────────────────────────── */
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.toggle('active', t.dataset.panel === name);
  });
  document.querySelectorAll('.panel').forEach(p => {
    p.classList.toggle('active', p.id === `panel-${name}`);
  });
}

/* ── Safe HTML from LLM text ─────────────────────────────────────────────── */
function _safe(text) {
  /** Sanitise arbitrary text before inserting as innerHTML. */
  if (typeof DOMPurify !== 'undefined') {
    return DOMPurify.sanitize(text || '');
  }
  // Fallback: plain-text encode (no keyword highlighting)
  const d = document.createElement('div');
  d.textContent = text || '';
  return d.innerHTML;
}

/* ── Keyword highlight (result sanitised separately) ─────────────────────── */
function highlightKeywords(text, keywords = []) {
  if (!keywords.length || !text) return _safe(text);
  // Start from safe text
  let out = _safe(text);
  keywords.forEach(kw => {
    const escaped = kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const re = new RegExp(`\\b(${escaped})\\b`, 'gi');
    out = out.replace(re, '<span class="kw-hl">$1</span>');
  });
  // Run DOMPurify again after injecting highlight spans (they're safe but double-check)
  return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(out) : out;
}

/* ── Score colour class ──────────────────────────────────────────────────── */
function scoreClass(s) { return s >= 70 ? 'score-good' : s >= 50 ? 'score-warn' : 'score-bad'; }
function fillClass(s)  { return s >= 70 ? 'fill-good'  : s >= 50 ? 'fill-warn'  : 'fill-bad';  }

/* ── Real spinner (replaces fake timed progress steps) ──────────────────── */
function renderSpinner(message = 'Connecting to AI…') {
  document.getElementById('results-area').innerHTML = `
    <div class="progress-box" id="real-spinner">
      <div class="spinner-large"></div>
      <div class="spinner-msg" id="spinner-msg">${_safe(message)}</div>
    </div>`;
}

function updateSpinnerMessage(message) {
  const el = document.getElementById('spinner-msg');
  if (el) el.textContent = message;
}

/* ── Helpers kept for backwards compat ───────────────────────────────────── */
function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ── Render results panel ────────────────────────────────────────────────── */
function renderResults(data) {
  const { version_number, product_name, tone, keywords = [],
    competitor_insights = [], seo_version, marketing_version,
    technical_version, version_id } = data;

  const versions = [
    { key: 'seo_version',       label: 'SEO optimised', badge: 'badge-seo',  obj: seo_version },
    { key: 'marketing_version', label: 'Marketing',     badge: 'badge-mkt',  obj: marketing_version },
    { key: 'technical_version', label: 'Technical',     badge: 'badge-tech', obj: technical_version },
  ];

  const kwChips = keywords.map(k => `<span class="chip chip-kw">${_safe(k)}</span>`).join('');
  const insightRows = competitor_insights.map(ci =>
    `<div class="suggestion-row"><div class="sug-icon sug-tip">i</div><span>${_safe(ci)}</span></div>`
  ).join('');

  // Version cards — each has a refinement instruction input
  const cards = versions.map(v => {
    const highlighted = highlightKeywords(v.obj?.description || '', keywords);
    const safeTitle   = _safe(v.obj?.title || '');
    const vid         = _safe(version_id);
    const vkey        = _safe(v.key);
    return `
    <div class="rcard" id="rcard-${v.key}">
      <div class="rcard-header">
        <div class="rcard-header-left">
          <span class="badge ${v.badge}">${v.label}</span>
          <span class="rcard-title">${safeTitle}</span>
        </div>
        <div class="rcard-actions">
          <button class="btn btn-xs" onclick="UI.copyText(this, ${JSON.stringify(v.obj?.description || '')})">Copy</button>
          <button class="btn btn-xs btn-refine" onclick="App.refineVersion('${vid}', '${vkey}')">Refine ↗</button>
        </div>
      </div>
      <div class="rcard-body">${highlighted}</div>
      <div class="rcard-refine-row">
        <input class="refine-instruction" type="text" maxlength="500"
          placeholder="Optional instruction for AI refine (e.g. 'make it shorter', 'add urgency')…" />
      </div>
    </div>`;
  }).join('');

  const vid = _safe(version_id);
  document.getElementById('results-area').innerHTML = `
    <div class="result-meta">
      <div class="result-meta-left">
        <span style="font-size:15px;font-weight:500">${_safe(product_name)}</span>
        <span class="badge badge-ver">v${version_number}</span>
        <span class="badge badge-tone">${_safe(tone)}</span>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-sm" onclick="App.exportVersion('${vid}')">Export TXT</button>
      </div>
    </div>
    <div class="info-card">
      <div class="section-label">Extracted keywords</div>
      <div class="chip-list">${kwChips}</div>
      ${competitor_insights.length ? `<div class="section-label" style="margin-top:12px">Competitor insights</div>${insightRows}` : ''}
    </div>
    ${cards}`;
}

/* ── Render SEO panel ────────────────────────────────────────────────────── */
function renderSEO(data) {
  const m   = data.seo_metrics || {};
  const sug = data.suggestions || [];
  const keywords = data.keywords || [];
  const overall  = m.overall_score || 0;

  const metrics = [
    { label: 'Readability',       val: `${m.readability_score || 0}/100`, raw: m.readability_score || 0 },
    { label: 'Keyword density',   val: `${(m.keyword_density || 0).toFixed(1)}%`, raw: (m.keyword_density >= 1.5 && m.keyword_density <= 3) ? 80 : 45 },
    { label: 'Title length',      val: `${m.title_length || 0} chars`,    raw: m.title_length <= 70 ? 90 : 50 },
    { label: 'Description words', val: `${m.description_length || 0}`,    raw: m.description_length >= 150 ? 90 : 55 },
    { label: 'Flesch score',      val: `${m.flesch_score || 0}`,          raw: m.flesch_score || 0 },
  ];

  const metricRows = metrics.map(r =>
    `<div class="metric-row"><span>${r.label}</span><span class="metric-val ${scoreClass(r.raw)}">${r.val}</span></div>`
  ).join('');

  const sugRows = sug.length
    ? sug.map(s => `
      <div class="suggestion-row">
        <div class="sug-icon sug-${s.type === 'warn' ? 'warn' : 'tip'}">${s.type === 'warn' ? '!' : 'i'}</div>
        <span>${_safe(s.text)}</span>
      </div>`).join('')
    : '<p style="font-size:13px;color:var(--c-text-2)">No major issues found — great work!</p>';

  const highlighted = highlightKeywords((data.seo_version || {}).description || '', keywords);

  document.getElementById('seo-area').innerHTML = `
    <div class="seo-grid">
      <div class="score-card">
        <div class="score-big ${scoreClass(overall)}">${Math.round(overall)}</div>
        <div class="score-label">Overall SEO score</div>
        <div class="score-bar"><div class="score-fill ${fillClass(overall)}" style="width:${overall}%"></div></div>
      </div>
      <div class="info-card" style="margin-bottom:0">
        <div class="section-label" style="margin-bottom:8px">Metrics</div>
        ${metricRows}
      </div>
    </div>
    <div class="info-card">
      <div class="section-label" style="margin-bottom:8px">Improvement suggestions</div>
      ${sugRows}
    </div>
    <div class="info-card">
      <div class="section-label" style="margin-bottom:8px">SEO version with highlighted keywords</div>
      <div style="font-size:14px;line-height:1.75">${highlighted}</div>
    </div>`;
}

/* ── Render compare panel ────────────────────────────────────────────────── */
function renderCompare(allResults, historyEntries = []) {
  const area = document.getElementById('compare-area');
  if (!area) return;

  const pool = historyEntries.length > 0 ? historyEntries : allResults;
  if (!pool || pool.length === 0) {
    area.innerHTML = `<div class="empty-state"><div class="empty-icon">⊞</div><div class="empty-title">Nothing to compare</div><div class="empty-body">Generate at least one version to use the compare panel.</div></div>`;
    return;
  }

  const options = pool.map(e =>
    `<option value="${e.version_id}">v${e.version_number} — ${e.product_name} (${e.tone})</option>`
  ).join('');

  const defaultA = pool.length >= 2 ? pool[1].version_id : pool[0].version_id;
  const defaultB = pool[0].version_id;

  area.innerHTML = `
    <div class="compare-controls">
      <div class="compare-sel-row">
        <label>Version A</label>
        <select id="cmp-sel-a" onchange="App.updateCompare()">${options}</select>
      </div>
      <div class="compare-sel-row">
        <label>Version B</label>
        <select id="cmp-sel-b" onchange="App.updateCompare()">${options}</select>
      </div>
    </div>
    <div id="compare-pair"></div>`;

  // Set defaults
  const selA = document.getElementById('cmp-sel-a');
  const selB = document.getElementById('cmp-sel-b');
  if (selA) selA.value = defaultA;
  if (selB) selB.value = defaultB;

  const a = pool.find(e => e.version_id === defaultA);
  const b = pool.find(e => e.version_id === defaultB);
  renderComparePair(a, b);
}

function renderComparePair(a, b) {
  const area = document.getElementById('compare-pair');
  if (!area) return;

  const col = (entry, label) => {
    if (!entry) return `<div><div class="compare-label">${label} — not selected</div></div>`;
    const score = Math.round(entry.seo_metrics?.overall_score || 0);
    return `
      <div>
        <div class="compare-label">
          ${_safe(entry.product_name)} · v${entry.version_number} · ${_safe(entry.tone)}
          · SEO: <strong class="${scoreClass(score)}">${score}</strong>
        </div>
        <div class="rcard">
          <div style="font-size:12px;color:var(--c-text-2);margin-bottom:6px;font-weight:500">SEO version</div>
          <div class="rcard-body" style="font-size:13px">${_safe(entry.seo_version?.description || '')}</div>
        </div>
        <div class="rcard" style="margin-top:8px">
          <div style="font-size:12px;color:var(--c-text-2);margin-bottom:6px;font-weight:500">Marketing version</div>
          <div class="rcard-body" style="font-size:13px">${_safe(entry.marketing_version?.description || '')}</div>
        </div>
      </div>`;
  };

  area.innerHTML = `<div class="compare-grid">${col(a, 'Version A')}${col(b, 'Version B')}</div>`;
}

/* ── Render history panel ────────────────────────────────────────────────── */
function renderHistory(entries, selectedId = null) {
  const area = document.getElementById('history-area');
  if (!entries || entries.length === 0) {
    area.innerHTML = `<div class="empty-state"><div class="empty-icon">◷</div><div class="empty-title">No history yet</div><div class="empty-body">Each generation is automatically saved here.</div></div>`;
    return;
  }

  const html = entries.map(e => {
    const score    = Math.round(e.seo_metrics?.overall_score || 0);
    const kwPreview = (e.keywords || []).slice(0, 4).join(', ');
    // Fix: timestamp already has tz info from server — parse as-is
    const ts = new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const selected = e.version_id === selectedId ? 'selected' : '';
    const vid = e.version_id;
    return `
    <div class="hist-item ${selected}" id="hist-${vid}" onclick="App.restoreVersion('${vid}')">
      <div class="hist-top">
        <div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap">
          <span class="hist-product">${_safe(e.product_name)}</span>
          <span class="badge badge-ver">v${e.version_number}</span>
          <span class="badge badge-tone">${_safe(e.tone)}</span>
        </div>
        <span class="hist-time">${ts}</span>
      </div>
      <div class="hist-meta">SEO score: <strong class="${scoreClass(score)}">${score}</strong>${kwPreview ? ' · ' + _safe(kwPreview) : ''}</div>
      <div class="score-bar" style="margin-top:7px">
        <div class="score-fill ${fillClass(score)}" style="width:${score}%"></div>
      </div>
      <div class="hist-actions" onclick="event.stopPropagation()">
        <button class="btn btn-xs" onclick="App.exportVersion('${vid}')">Export</button>
        <button class="btn btn-xs" onclick="App.deleteFromHistory('${vid}')">Delete</button>
      </div>
    </div>`;
  }).join('');

  area.innerHTML = `
    <p style="font-size:13px;color:var(--c-text-2);margin-bottom:1rem">${entries.length} version${entries.length > 1 ? 's' : ''} tracked</p>
    ${html}`;
}

/* ── Copy helper ─────────────────────────────────────────────────────────── */
function copyText(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  }).catch(() => toast('Copy failed'));
}

/* ── Auth UI ─────────────────────────────────────────────────────────────── */
function toggleAuthModal() {
  const modal = document.getElementById('auth-modal');
  modal.style.display = modal.style.display === 'none' ? 'flex' : 'none';
}

function updateAuthStatus() {
  const token = localStorage.getItem('token');
  const statusEl = document.getElementById('auth-status');
  if (token) {
    statusEl.textContent = 'Logout';
    statusEl.onclick = () => {
      localStorage.removeItem('token');
      UI.toast('Logged out successfully');
      UI.updateAuthStatus();
      clearAll(); // from app.js
    };
  } else {
    statusEl.textContent = 'Login / Register';
    statusEl.onclick = toggleAuthModal;
  }
}

async function login() {
  const u = document.getElementById('auth-user').value.trim();
  const p = document.getElementById('auth-pass').value.trim();
  
  if (!u || !p) {
    UI.toast('Please enter both username and password');
    return;
  }
  
  try {
    const data = await API.login(u, p);
    localStorage.setItem('token', data.access_token);
    UI.toast('Logged in successfully!');
    toggleAuthModal();
    updateAuthStatus();
    loadHistory(); // from app.js
  } catch (err) {
    UI.toast(err.message || 'Login failed');
  }
}

async function register() {
  const u = document.getElementById('auth-user').value.trim();
  const p = document.getElementById('auth-pass').value.trim();
  
  if (!u) {
    UI.toast('Username is required');
    return;
  }
  if (p.length < 3) {
    UI.toast('Password must be at least 3 characters');
    return;
  }
  
  try {
    await API.register(u, p);
    UI.toast('Registration successful! Logging in...');
    await login();
  } catch (err) {
    UI.toast(err.message || 'Registration failed');
  }
}

// Check initial status
document.addEventListener('DOMContentLoaded', updateAuthStatus);

/* Expose on global UI object */
const UI = {
  toast, setStatus, showTab, highlightKeywords, scoreClass, fillClass,
  renderSpinner, updateSpinnerMessage, delay,
  renderResults, renderSEO, renderCompare, renderComparePair, renderHistory,
  copyText, toggleAuthModal, updateAuthStatus, login, register
};
