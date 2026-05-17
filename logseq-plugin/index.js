/* global logseq */

'use strict';

const path            = require('path');
const fs              = require('fs');
const { createHash }  = require('crypto');

// ── Helpers ───────────────────────────────────────────────────────────────────

function sha256(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function jwtExpiry(token) {
  try {
    const payload = JSON.parse(
      Buffer.from(
        token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'),
        'base64'
      ).toString()
    );
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null;
  } catch { return null; }
}

// ── Settings schema ───────────────────────────────────────────────────────────

const SETTINGS_SCHEMA = [
  {
    key:         'serverUrl',
    type:        'string',
    title:       'Lab URL',
    description: 'URL base del Research Lab',
    default:     'https://lab.aural-syncro.com.ar',
  },
  {
    key:         'jwtToken',
    type:        'string',
    title:       'JWT Token',
    description: 'Obtenelo desde el Lab → Herramientas → Token personal',
    default:     '',
  },
  {
    key:         'projectId',
    type:        'string',
    title:       'Project ID',
    description: 'UUID del proyecto (visible en la URL del Lab)',
    default:     '',
  },
  {
    key:         'docMap',
    type:        'object',
    title:       'Mapa de documentos',
    description: 'Mapa interno: nombre de página → ID en el Lab. No editar manualmente.',
    default:     {},
  },
];

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  graphPath:    '',
  lastPage:     null,   // originalName of last open page
  openHashes:   {},     // originalName → sha256 of content at open time
  syncTimers:   {},     // originalName → debounce handle
  refreshTimer: null,
};

const REFRESH_AHEAD_MS = 10 * 60 * 1000;
const DEBOUNCE_MS      = 1500;

// ── Config guard ──────────────────────────────────────────────────────────────

function isConfigured() {
  const s = logseq.settings;
  return !!(s?.serverUrl && s?.jwtToken && s?.projectId);
}

// ── API client ────────────────────────────────────────────────────────────────

async function api(method, endpoint, body) {
  const s   = logseq.settings;
  const url = `${s.serverUrl.replace(/\/$/, '')}/api/v1${endpoint}`;
  return fetch(url, {
    method,
    headers: {
      'Content-Type':  'application/json',
      'Authorization': `Bearer ${s.jwtToken}`,
    },
    ...(body != null ? { body: JSON.stringify(body) } : {}),
  });
}

// ── File path resolution ──────────────────────────────────────────────────────

/**
 * Logseq stores pages in {graphPath}/pages/{originalName}.md
 * Journal pages live in  {graphPath}/journals/{YYYY_MM_DD}.md
 */
function resolvePagePath(originalName) {
  const journalMatch = originalName.match(/^(\d{4})[_-](\d{2})[_-](\d{2})$/);
  if (journalMatch) {
    const [, y, m, d] = journalMatch;
    return path.join(state.graphPath, 'journals', `${y}_${m}_${d}.md`);
  }
  return path.join(state.graphPath, 'pages', `${originalName}.md`);
}

async function readPageContent(originalName) {
  try {
    return await fs.promises.readFile(resolvePagePath(originalName), 'utf-8');
  } catch { return null; }
}

// ── Document management ───────────────────────────────────────────────────────

async function ensureDocument(originalName, content) {
  const docMap  = logseq.settings.docMap ?? {};
  if (docMap[originalName]) return docMap[originalName];

  try {
    const res = await api(
      'POST',
      `/projects/${logseq.settings.projectId}/documents`,
      { title: originalName, body: content }
    );
    if (!res.ok) return null;
    const data = await res.json();
    await logseq.updateSettings({ docMap: { ...docMap, [originalName]: data.id } });
    return data.id;
  } catch { return null; }
}

// ── Core lifecycle ────────────────────────────────────────────────────────────

async function onPageOpen(originalName) {
  if (!isConfigured()) return;

  const content = await readPageContent(originalName);
  if (content === null) return;

  state.lastPage = originalName;

  const docId = await ensureDocument(originalName, content);
  if (!docId) return;

  // Acquire soft lock — best-effort, never blocks the user
  try {
    const res = await api(
      'PUT',
      `/projects/${logseq.settings.projectId}/documents/${docId}/lock`,
      null
    );
    if (res.status === 409) {
      const data = await res.json();
      const who  = data.detail?.split('por ')[1] ?? 'otro usuario';
      logseq.App.showMsg(`⚠️ Research Lab: documento bloqueado por ${who}`, 'warning');
    }
  } catch { /* lock is best-effort */ }

  state.openHashes[originalName] = sha256(content);
}

async function syncPage(originalName) {
  if (!isConfigured()) return;

  const content = await readPageContent(originalName);
  if (content === null) return;

  const docId = await ensureDocument(originalName, content);
  if (!docId) return;

  const version_hash = state.openHashes[originalName] ?? null;

  try {
    const res = await api(
      'POST',
      `/projects/${logseq.settings.projectId}/documents/${docId}/sync`,
      { content, version_hash }
    );

    if (res.status === 409) {
      logseq.App.showMsg(
        '⚠️ Research Lab: conflicto detectado — revisá la web para resolver',
        'warning'
      );
      return;
    }
    if (!res.ok) {
      logseq.App.showMsg(`Research Lab sync error ${res.status}`, 'error');
      return;
    }

    state.openHashes[originalName] = sha256(content);
  } catch {
    logseq.App.showMsg('Research Lab: sin conexión', 'warning');
  }
}

async function releaseLock(originalName) {
  if (!isConfigured()) return;
  const docId = (logseq.settings.docMap ?? {})[originalName];
  if (!docId) return;

  delete state.openHashes[originalName];

  try {
    await api(
      'DELETE',
      `/projects/${logseq.settings.projectId}/documents/${docId}/lock`,
      null
    );
  } catch { /* best-effort */ }
}

function scheduleSync(originalName) {
  if (state.syncTimers[originalName]) clearTimeout(state.syncTimers[originalName]);
  state.syncTimers[originalName] = setTimeout(() => {
    delete state.syncTimers[originalName];
    syncPage(originalName);
  }, DEBOUNCE_MS);
}

// ── Token refresh ─────────────────────────────────────────────────────────────

function scheduleTokenRefresh() {
  if (state.refreshTimer) clearTimeout(state.refreshTimer);
  const token = logseq.settings?.jwtToken;
  if (!token) return;

  const exp   = jwtExpiry(token);
  if (!exp) return;

  const delay = Math.max(0, exp - Date.now() - REFRESH_AHEAD_MS);
  state.refreshTimer = setTimeout(refreshToken, delay);
}

async function refreshToken() {
  if (!isConfigured()) return;
  try {
    const res = await api('POST', '/auth/refresh', null);
    if (!res.ok) {
      logseq.App.showMsg('Research Lab: no se pudo renovar el token', 'warning');
      return;
    }
    const data = await res.json();
    await logseq.updateSettings({ jwtToken: data.access_token });
    scheduleTokenRefresh();
    logseq.App.showMsg('Research Lab: token renovado', 'success');
  } catch { /* silent — retry on next startup */ }
}

// ── Entry point ───────────────────────────────────────────────────────────────

async function main() {
  logseq.useSettingsSchema(SETTINGS_SCHEMA);

  const graph       = await logseq.App.getCurrentGraph();
  state.graphPath   = graph?.path ?? '';

  scheduleTokenRefresh();

  // ── Commands ────────────────────────────────────────────────────────────────

  logseq.App.registerCommand('research-lab', {
    key:   'sync-page',
    label: 'Research Lab: Sync page now',
  }, async () => {
    const page = await logseq.Editor.getCurrentPage();
    if (!page) return;
    await syncPage(page.originalName ?? page.name);
  });

  logseq.App.registerCommand('research-lab', {
    key:   'renew-token',
    label: 'Research Lab: Renovar token JWT',
  }, refreshToken);

  logseq.App.registerCommand('research-lab', {
    key:   'clear-docmap',
    label: 'Research Lab: Limpiar mapa de documentos',
  }, async () => {
    await logseq.updateSettings({ docMap: {} });
    logseq.App.showMsg('Research Lab: mapa limpiado', 'success');
  });

  // ── Page navigation → lock / hash ───────────────────────────────────────────

  logseq.App.onRouteChanged(async ({ path: routePath }) => {
    const match = routePath?.match(/^\/(?:page|file)\/(.+)$/);
    if (!match) return;

    const pageName = decodeURIComponent(match[1]);

    if (state.lastPage && state.lastPage !== pageName) {
      await releaseLock(state.lastPage);
    }

    await onPageOpen(pageName);
  });

  // ── Block edits → debounced sync ────────────────────────────────────────────

  logseq.DB.onChanged(({ blocks }) => {
    if (!state.lastPage || !isConfigured()) return;
    const affected = blocks.some(
      b => (b.page?.originalName ?? b.page?.name) === state.lastPage
    );
    if (affected) scheduleSync(state.lastPage);
  });

  logseq.App.showMsg('SSPA Research Lab: plugin listo ✓', 'success');
}

logseq.ready(main).catch(console.error);
