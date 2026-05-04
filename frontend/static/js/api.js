/**
 * api.js — ContentBoost AI API client (all fetch calls to FastAPI backend)
 */

const API = {
  base: '',  // same origin

  getHeaders() {
    const token = localStorage.getItem('token');
    return token ? { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` } 
                 : { 'Content-Type': 'application/json' };
  },

  async post(path, body) {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: this.getHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      let msg = err.detail || `HTTP ${res.status}`;
      if (Array.isArray(msg)) {
        msg = msg.map(e => `${e.loc[e.loc.length - 1]}: ${e.msg}`).join(', ');
      }
      throw new Error(msg);
    }
    return res.json();
  },

  async get(path) {
    const res = await fetch(this.base + path, {
      headers: this.getHeaders()
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  async del(path) {
    const res = await fetch(this.base + path, { 
      method: 'DELETE',
      headers: this.getHeaders()
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },

  /** POST /analyze */
  analyze(payload)      { return this.post('/analyze', payload); },

  /** POST /generate (non-streaming) */
  generate(payload)     { return this.post('/generate', payload); },

  /** POST /refine */
  refine(payload)       { return this.post('/refine', payload); },

  /** POST /scrape — fetch competitor URL content */
  scrape(url)           { return this.post('/scrape', { url }); },

  /** GET /history */
  getAllHistory(limit = 80) { return this.get(`/history?limit=${limit}`); },

  /** GET /history/{product_name} */
  getProductHistory(productName) {
    return this.get(`/history/${encodeURIComponent(productName)}`);
  },

  /** DELETE /history/{version_id} */
  deleteVersion(versionId) { return this.del(`/history/${versionId}`); },

  /** GET /export/{version_id} — plain text download URL */
  exportUrl(versionId) { return `/export/${versionId}`; }, // Handled outside api.js, usually we need token so we might need fetch

  async downloadExport(versionId) {
    const res = await fetch(this.base + this.exportUrl(versionId), {
      headers: this.getHeaders()
    });
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `contentboost-export.txt`;
    a.click();
  },

  /**
   * POST /generate/stream — returns a Promise that resolves with the final
   * GenerateResponse data, firing onStatus(step, message) callbacks as
   * real server-side progress events arrive.
   */
  generateStream(payload, onStatus, onChunk) {
    return new Promise(async (resolve, reject) => {
      try {
        const res = await fetch(this.base + '/generate/stream', {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify(payload),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE lines: "data: {...}\n\n"
          const lines = buffer.split('\n\n');
          buffer = lines.pop(); // keep incomplete chunk

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const msg = JSON.parse(line.slice(6));
              if (msg.event === 'done' || msg.event === 'result') {
                resolve(msg.data);
              } else if (msg.event === 'error') {
                reject(new Error(msg.message || 'Stream error'));
              } else if (msg.event === 'status' && onStatus) {
                onStatus(msg.step, msg.message);
              } else if (msg.event === 'chunk' && onChunk) {
                onChunk(msg.text);
              }
            } catch (_) { /* skip malformed lines */ }
          }
        }
      } catch (err) {
        reject(err);
      }
    });
  },

  /** Auth endpoints */
  login(username, password) {
    return fetch(this.base + '/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username, password })
    }).then(async res => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return res.json();
    });
  },

  register(username, password) {
    return this.post('/register', { username, password });
  }
};
