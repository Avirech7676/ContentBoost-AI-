/**
 * app.js — ContentBoost AI main application logic
 *
 * Key fixes vs original:
 * - Generate uses real SSE streaming (no fake timed progress steps)
 * - Error message references Gemini, not Anthropic
 * - Refine UI exposes the instruction text field
 * - Competitor URL scraper integrated
 * - Compare panel supports selecting any 2 stored versions
 */

/* ── State ───────────────────────────────────────────────────────────────── */
const State = {
  selectedTone: 'persuasive',
  currentVersionId: null,
  allResults: [],       // GenerateResponse objects accumulated this session
  historyEntries: [],   // HistoryEntry objects from server
};

/* ── Init ────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  bindToneButtons();
  bindTabButtons();
  bindSidebarButtons();
  loadHistory();
});

function bindToneButtons() {
  document.querySelectorAll('.tone-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tone-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      State.selectedTone = btn.dataset.tone;
    });
  });
}

function bindTabButtons() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => UI.showTab(tab.dataset.panel));
  });
}

function bindSidebarButtons() {
  document.getElementById('btn-generate').addEventListener('click', runGenerate);
  document.getElementById('btn-analyze').addEventListener('click', runAnalyze);
  document.getElementById('btn-demo').addEventListener('click', loadDemo);
  document.getElementById('btn-clear').addEventListener('click', clearAll);
  document.getElementById('btn-scrape').addEventListener('click', runScrape);
  const emptyDemo = document.getElementById('btn-demo-empty');
  if (emptyDemo) emptyDemo.addEventListener('click', loadDemo);
}

/* ── History ─────────────────────────────────────────────────────────────── */
async function loadHistory() {
  try {
    const resp = await API.getAllHistory(80);
    State.historyEntries = resp.entries || [];
    if (State.historyEntries.length > 0) {
      UI.renderHistory(State.historyEntries, State.currentVersionId);
      UI.renderCompare(State.allResults, State.historyEntries);
    }
  } catch (_) { /* silent — no history yet */ }
}

/* ── Demo data ───────────────────────────────────────────────────────────── */
function loadDemo() {
  document.getElementById('inp-name').value     = 'ProSound X9 Wireless Headphones';
  document.getElementById('inp-cat').value      = 'Electronics';
  document.getElementById('inp-desc').value     = 'Good headphones with wireless connectivity. Battery lasts long. Comfortable to wear. Good sound quality. Comes with charging cable.';
  document.getElementById('inp-audience').value = 'Music enthusiasts, remote workers, commuters';
  document.getElementById('inp-comp').value     = 'Experience studio-quality audio anywhere with our flagship noise-cancelling headphones. Enjoy 40-hour battery life, premium leather ear cushions, Hi-Res Audio certification, and foldable design for travel. Compatible with all Bluetooth 5.0 devices.';
  UI.toast('Demo product loaded');
}

function clearAll() {
  ['inp-name', 'inp-desc', 'inp-audience', 'inp-comp', 'inp-comp-url'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  document.getElementById('inp-cat').value = '';
  State.currentVersionId = null;
  State.allResults = [];
  document.getElementById('results-area').innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">✦</div>
      <div class="empty-title">No results yet</div>
      <div class="empty-body">Fill in your product details and click "Generate descriptions".</div>
      <button class="btn btn-secondary" onclick="loadDemo()">Load demo product</button>
    </div>`;
  ['seo-area'].forEach(id => {
    document.getElementById(id).innerHTML = `<div class="empty-state"><div class="empty-icon">○</div><div class="empty-title">Nothing here yet</div></div>`;
  });
  UI.renderCompare([], []);
  UI.setStatus('Ready', 'idle');
}

/* ── Collect input ────────────────────────────────────────────────────────── */
function collectInput() {
  return {
    product_name:         document.getElementById('inp-name').value.trim(),
    category:             document.getElementById('inp-cat').value || null,
    existing_description: document.getElementById('inp-desc').value.trim() || null,
    competitor_content:   document.getElementById('inp-comp').value.trim() || null,
    target_audience:      document.getElementById('inp-audience').value.trim() || null,
    tone:                 State.selectedTone,
  };
}

/* ── Competitor URL scraper ───────────────────────────────────────────────── */
async function runScrape() {
  const urlEl = document.getElementById('inp-comp-url');
  const url = urlEl?.value?.trim();
  if (!url) { UI.toast('Enter a competitor URL first'); return; }

  const btn = document.getElementById('btn-scrape');
  btn.disabled = true;
  btn.textContent = 'Scraping…';
  UI.setStatus('Scraping competitor page…', 'loading');

  try {
    const data = await API.scrape(url);
    document.getElementById('inp-comp').value = data.content;
    UI.toast(`✓ Scraped ${data.word_count} words from competitor page`);
    UI.setStatus('Scrape complete', 'success');
    if (urlEl) urlEl.value = '';
  } catch (err) {
    UI.toast(`Scrape failed: ${err.message}`);
    UI.setStatus('Scrape error', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Scrape URL';
  }
}

/* ── Generate (real SSE streaming) ───────────────────────────────────────── */
async function runGenerate() {
  const input = collectInput();
  if (!input.product_name) {
    UI.toast('Please enter a product name');
    return;
  }

  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> Generating…';
  UI.setStatus('Starting AI pipeline…', 'loading');
  UI.renderSpinner();          // show real spinner, not fake steps
  UI.showTab('results');

  try {
    // We'll create temporary DOM elements for the typing effect
    document.getElementById('results-area').innerHTML = `
      <div id="stream-seo" class="info-card">
        <h3 id="stream-seo-title">SEO Version</h3>
        <p id="stream-seo-desc" style="color:var(--c-text-2)"></p>
      </div>
      <div id="stream-mkt" class="info-card" style="margin-top:15px">
        <h3 id="stream-mkt-title">Marketing Version</h3>
        <p id="stream-mkt-desc" style="color:var(--c-text-2)"></p>
      </div>
    `;

    const extractPartial = (text, versionType) => {
      // Regex to extract title
      const titleMatch = text.match(new RegExp(`"${versionType}"\\s*:\\s*\\{[^}]*"title"\\s*:\\s*"([^"]*)`));
      const title = titleMatch ? titleMatch[1] : '';
      
      // Regex to extract description (handles escaped quotes and newlines)
      const descMatch = text.match(new RegExp(`"${versionType}"\\s*:\\s*\\{.*?\\"description"\\s*:\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)`, 's'));
      const desc = descMatch ? descMatch[1] : '';
      
      return { title, desc: desc.replace(/\\n/g, '<br>').replace(/\\"/g, '"') };
    };

    const data = await API.generateStream(input, 
      (step, message) => {
        UI.setStatus(message, 'loading');
      },
      (chunkText) => {
        // As chunkText accumulates, try to parse out the SEO and Marketing versions
        const seoData = extractPartial(chunkText, 'seo_version');
        if (seoData.title) document.getElementById('stream-seo-title').textContent = seoData.title;
        if (seoData.desc) document.getElementById('stream-seo-desc').innerHTML = seoData.desc;
        
        const mktData = extractPartial(chunkText, 'marketing_version');
        if (mktData.title) document.getElementById('stream-mkt-title').textContent = mktData.title;
        if (mktData.desc) document.getElementById('stream-mkt-desc').innerHTML = mktData.desc;
      }
    );

    State.allResults.push(data);
    State.currentVersionId = data.version_id;

    UI.renderResults(data);
    UI.renderSEO(data);

    await loadHistory();
    UI.renderHistory(State.historyEntries, data.version_id);
    UI.renderCompare(State.allResults, State.historyEntries);

    UI.setStatus(`v${data.version_number} generated — ${new Date().toLocaleTimeString()}`, 'success');
    UI.toast('Descriptions generated successfully!');

  } catch (err) {
    const isAuthErr = err.message.includes('Not authenticated') || err.message.includes('401') || err.message.includes('Could not validate credentials');
    document.getElementById('results-area').innerHTML = `
      <div class="info-card" style="border-color:var(--c-text-danger)">
        <div style="font-size:14px;font-weight:500;color:var(--c-text-danger)">Generation failed</div>
        <div style="font-size:13px;color:var(--c-text-2);margin-top:5px">${err.message}</div>
        <div style="font-size:12px;color:var(--c-text-3);margin-top:4px">
          ${isAuthErr 
            ? 'You must be logged in to use this feature. <a href="#" onclick="UI.toggleAuthModal()" style="color:inherit;text-decoration:underline">Click here to log in</a>.' 
            : 'Check that your GROQ_API_KEY is set in .env and the server is running.'}
        </div>
      </div>`;
    UI.setStatus('Error — check console', 'error');
    console.error('[ContentBoost] Generate error:', err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 1v12M1 7h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      Generate descriptions`;
  }
}

/* ── Analyze only ─────────────────────────────────────────────────────────── */
async function runAnalyze() {
  const input = collectInput();
  if (!input.product_name) { UI.toast('Please enter a product name'); return; }

  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  btn.textContent = 'Analysing…';
  UI.setStatus('Analysing…', 'loading');

  try {
    const data = await API.analyze(input);

    const kwChips    = (data.keywords || []).map(k => `<span class="chip chip-kw">${_esc(k)}</span>`).join('');
    const insightRows = (data.competitor_insights || []).map(i =>
      `<div class="suggestion-row"><div class="sug-icon sug-tip">i</div><span>${_esc(i)}</span></div>`
    ).join('');
    const patternRows = (data.writing_patterns || []).map(p =>
      `<div class="suggestion-row"><div class="sug-icon sug-tip">◈</div><span>${_esc(p)}</span></div>`
    ).join('');
    const featChips  = (data.common_features || []).map(f => `<span class="chip chip-feat">${_esc(f)}</span>`).join('');

    document.getElementById('results-area').innerHTML = `
      <div style="font-size:15px;font-weight:500;margin-bottom:1rem">Analysis results</div>
      <div class="info-card">
        <div class="section-label">Keywords (${data.keywords?.length || 0})</div>
        <div class="chip-list">${kwChips || '<span style="font-size:13px;color:var(--c-text-2)">None found</span>'}</div>
      </div>
      ${featChips   ? `<div class="info-card"><div class="section-label">Common features</div><div class="chip-list">${featChips}</div></div>` : ''}
      ${insightRows ? `<div class="info-card"><div class="section-label">Competitor insights</div>${insightRows}</div>` : ''}
      ${patternRows ? `<div class="info-card"><div class="section-label">Writing patterns</div>${patternRows}</div>` : ''}`;

    UI.showTab('results');
    UI.setStatus('Analysis complete', 'success');
    UI.toast('Analysis complete');
  } catch (err) {
    const isAuthErr = err.message.includes('401') || err.message.includes('Could not validate credentials');
    if (isAuthErr) {
      UI.toast('Authentication required — please log in');
      UI.toggleAuthModal();
    } else {
      UI.toast(`Analysis failed: ${err.message}`);
    }
    UI.setStatus('Error', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Analyze only';
  }
}

/* ── HTML escape helper (used instead of direct LLM text in attributes) ───── */
function _esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

/* ── Refine a version ─────────────────────────────────────────────────────── */
async function refineVersion(versionId, versionType) {
  const cardId = `rcard-${versionType}`;
  const card = document.getElementById(cardId);
  if (!card) return;

  // Get optional instruction from the card's input field
  const instructionEl = card.querySelector('.refine-instruction');
  const instruction = instructionEl ? instructionEl.value.trim() || null : null;

  const body = card.querySelector('.rcard-body');
  const btn  = card.querySelector('.btn-refine');
  const origText = btn?.textContent;
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  UI.setStatus('Refining…', 'loading');

  try {
    const data = await API.refine({ version_id: versionId, version_type: versionType, instruction });

    const titleEl = card.querySelector('.rcard-title');
    if (titleEl) titleEl.textContent = data.refined_title;

    const result = State.allResults.find(r => r.version_id === versionId);
    if (result && result[versionType]) {
      result[versionType].description = data.refined_description;
      result[versionType].title = data.refined_title;
    }

    // Sanitise with DOMPurify before inserting as innerHTML
    const kw = result?.keywords || [];
    const highlighted = UI.highlightKeywords(data.refined_description, kw);
    body.innerHTML = DOMPurify.sanitize(highlighted);

    if (instructionEl) instructionEl.value = '';
    UI.setStatus('Refined', 'success');
    UI.toast('Version refined!');
  } catch (err) {
    const isAuthErr = err.message.includes('401') || err.message.includes('Could not validate credentials');
    if (isAuthErr) {
      UI.toast('Authentication required — please log in');
      UI.toggleAuthModal();
    } else {
      UI.toast(`Refinement failed: ${err.message}`);
    }
    UI.setStatus('Error', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText || 'Refine ↗'; }
  }
}

/* ── Restore from history ─────────────────────────────────────────────────── */
function restoreVersion(versionId) {
  const entry = State.historyEntries.find(e => e.version_id === versionId);
  if (!entry) return;

  const asResult = { ...entry };
  State.currentVersionId = versionId;

  UI.renderResults(asResult);
  UI.renderSEO(asResult);
  UI.showTab('results');
  UI.setStatus(`Viewing v${entry.version_number} — ${entry.product_name}`, 'idle');

  document.querySelectorAll('.hist-item').forEach(el => el.classList.remove('selected'));
  const el = document.getElementById(`hist-${versionId}`);
  if (el) el.classList.add('selected');
}

/* ── Compare: update when user changes dropdowns ─────────────────────────── */
function updateCompare() {
  const selA = document.getElementById('cmp-sel-a');
  const selB = document.getElementById('cmp-sel-b');
  if (!selA || !selB) return;
  const idA = selA.value;
  const idB = selB.value;
  const a = State.historyEntries.find(e => e.version_id === idA);
  const b = State.historyEntries.find(e => e.version_id === idB);
  UI.renderComparePair(a || null, b || null);
}

/* ── Export ───────────────────────────────────────────────────────────────── */
function exportVersion(versionId) {
  const url = API.exportUrl(versionId);
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  UI.toast('Downloading export…');
}

/* ── Delete from history ──────────────────────────────────────────────────── */
async function deleteFromHistory(versionId) {
  if (!confirm('Delete this version from history?')) return;
  try {
    await API.deleteVersion(versionId);
    State.historyEntries = State.historyEntries.filter(e => e.version_id !== versionId);
    State.allResults     = State.allResults.filter(r => r.version_id !== versionId);
    UI.renderHistory(State.historyEntries, State.currentVersionId);
    UI.renderCompare(State.allResults, State.historyEntries);
    UI.toast('Version deleted');
  } catch (err) {
    UI.toast(`Delete failed: ${err.message}`);
  }
}

/* Expose for inline onclick attributes */
const App = { refineVersion, restoreVersion, exportVersion, deleteFromHistory, updateCompare, runScrape };
