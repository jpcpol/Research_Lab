#!/usr/bin/env node
/**
 * mcp-lab-bridge.mjs
 * MCP server — Obsidian vault ↔ Research Lab anti-collision bridge
 *
 * Exposes four tools to Claude Code / Claude AI:
 *   read_note    — read a vault file
 *   write_note   — write a vault file (acquires Lab lock first)
 *   list_notes   — list .md files in vault (optionally filtered by prefix)
 *   search_notes — full-text search across vault files
 *
 * Setup:
 *   1. npm install @modelcontextprotocol/sdk node-fetch
 *   2. Copy mcp.template.json → .mcp.json in your Claude Code project root
 *      and fill in VAULT_PATH, LAB_URL, LAB_TOKEN, LAB_PROJECT_ID
 *   3. Run: node mcp-lab-bridge.mjs
 *
 * Environment variables (or pass via .mcp.json env block):
 *   VAULT_PATH       — absolute path to the Obsidian vault
 *   LAB_URL          — Research Lab base URL (e.g. https://lab.aural-syncro.com.ar)
 *   LAB_TOKEN        — JWT access token (same as in Obsidian plugin settings)
 *   LAB_PROJECT_ID   — project UUID
 *
 * DT-RL-014 — Claude Code local integration via MCP (Módulo E)
 */

import { Server }  from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import fs   from "fs/promises";
import path from "path";

const VAULT     = process.env.VAULT_PATH      ?? "";
const LAB_URL   = (process.env.LAB_URL        ?? "").replace(/\/$/, "");
const LAB_TOKEN = process.env.LAB_TOKEN       ?? "";
const PROJECT   = process.env.LAB_PROJECT_ID  ?? "";

// ── Lab API helpers ────────────────────────────────────────────────────────────

async function labFetch(method, endpoint, body = null) {
  const { default: fetch } = await import("node-fetch");
  const opts = {
    method,
    headers: {
      "Content-Type":  "application/json",
      "Authorization": `Bearer ${LAB_TOKEN}`,
    },
  };
  if (body) opts.body = JSON.stringify(body);
  return fetch(`${LAB_URL}/api/v1${endpoint}`, opts);
}

/** Returns document id for a given vault path, or null if not mapped. */
async function resolveDocId(vaultPath) {
  // The plugin stores the docMap in vault/.obsidian/plugins/sspa-research-lab/data.json
  try {
    const dataFile = path.join(VAULT, ".obsidian", "plugins", "sspa-research-lab", "data.json");
    const raw  = await fs.readFile(dataFile, "utf-8");
    const data = JSON.parse(raw);
    return (data.docMap ?? {})[vaultPath] ?? null;
  } catch {
    return null;
  }
}

/** Acquire Lab soft lock for a document. Returns { ok, lockedBy }. */
async function acquireLock(docId) {
  if (!LAB_TOKEN || !PROJECT || !docId) return { ok: true, lockedBy: null };
  try {
    const r = await labFetch("PUT", `/projects/${PROJECT}/documents/${docId}/lock`);
    if (r.status === 409) {
      const d = await r.json();
      return { ok: false, lockedBy: d.detail?.replace("Document locked by ", "") ?? "otro usuario" };
    }
    return { ok: true, lockedBy: null };
  } catch {
    return { ok: true, lockedBy: null };   // best-effort — allow write on API error
  }
}

/** Release Lab soft lock for a document. */
async function releaseLock(docId) {
  if (!LAB_TOKEN || !PROJECT || !docId) return;
  try {
    await labFetch("DELETE", `/projects/${PROJECT}/documents/${docId}/lock`);
  } catch { /* best-effort */ }
}

// ── Tool handlers ─────────────────────────────────────────────────────────────

async function readNote({ vault_path }) {
  if (!VAULT) throw new Error("VAULT_PATH not set");
  const abs  = path.join(VAULT, vault_path);
  const content = await fs.readFile(abs, "utf-8");
  return { content };
}

async function writeNote({ vault_path, content }) {
  if (!VAULT) throw new Error("VAULT_PATH not set");
  const abs   = path.join(VAULT, vault_path);
  const docId = await resolveDocId(vault_path);

  // Anti-collision: acquire lock before writing
  const lock = await acquireLock(docId);
  if (!lock.ok) {
    throw new Error(
      `Cannot write — document is locked by ${lock.lockedBy}. ` +
      `Wait for them to finish or ask them to release the lock.`
    );
  }

  try {
    await fs.mkdir(path.dirname(abs), { recursive: true });
    await fs.writeFile(abs, content, "utf-8");
  } finally {
    await releaseLock(docId);
  }

  return { written: true, vault_path };
}

async function listNotes({ prefix = "" }) {
  if (!VAULT) throw new Error("VAULT_PATH not set");

  async function walk(dir, results = []) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    for (const e of entries) {
      if (e.name.startsWith(".")) continue;  // skip hidden dirs like .obsidian
      const full = path.join(dir, e.name);
      if (e.isDirectory()) await walk(full, results);
      else if (e.name.endsWith(".md")) {
        const rel = path.relative(VAULT, full).replace(/\\/g, "/");
        if (!prefix || rel.startsWith(prefix)) results.push(rel);
      }
    }
    return results;
  }

  const files = await walk(VAULT);
  return { files };
}

async function searchNotes({ query, max_results = 20 }) {
  if (!VAULT) throw new Error("VAULT_PATH not set");
  const { files } = await listNotes({});
  const q = query.toLowerCase();
  const matches = [];

  for (const rel of files) {
    if (matches.length >= max_results) break;
    try {
      const text = await fs.readFile(path.join(VAULT, rel), "utf-8");
      const idx  = text.toLowerCase().indexOf(q);
      if (idx !== -1) {
        const start   = Math.max(0, idx - 80);
        const snippet = text.slice(start, idx + 160).replace(/\n/g, " ").trim();
        matches.push({ path: rel, snippet });
      }
    } catch { /* skip unreadable files */ }
  }

  return { matches };
}

// ── MCP server setup ──────────────────────────────────────────────────────────

const TOOLS = [
  {
    name: "read_note",
    description: "Read the full content of a note from the Obsidian vault.",
    inputSchema: {
      type: "object",
      properties: {
        vault_path: { type: "string", description: "Relative path inside the vault (e.g. 'Research/hypothesis.md')" },
      },
      required: ["vault_path"],
    },
  },
  {
    name: "write_note",
    description: "Write content to a vault note, acquiring the Research Lab lock first to prevent collisions with other collaborators.",
    inputSchema: {
      type: "object",
      properties: {
        vault_path: { type: "string", description: "Relative path inside the vault" },
        content:    { type: "string", description: "Full content to write" },
      },
      required: ["vault_path", "content"],
    },
  },
  {
    name: "list_notes",
    description: "List all Markdown files in the vault, optionally filtered by a path prefix.",
    inputSchema: {
      type: "object",
      properties: {
        prefix: { type: "string", description: "Optional path prefix to filter results (e.g. 'Research/')" },
      },
    },
  },
  {
    name: "search_notes",
    description: "Full-text search across all vault notes. Returns matching file paths with context snippets.",
    inputSchema: {
      type: "object",
      properties: {
        query:       { type: "string", description: "Search string" },
        max_results: { type: "integer", description: "Maximum results to return (default: 20)" },
      },
      required: ["query"],
    },
  },
];

const server = new Server(
  { name: "mcp-lab-bridge", version: "1.0.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const args = req.params.arguments ?? {};
  try {
    let result;
    switch (req.params.name) {
      case "read_note":    result = await readNote(args);    break;
      case "write_note":   result = await writeNote(args);   break;
      case "list_notes":   result = await listNotes(args);   break;
      case "search_notes": result = await searchNotes(args); break;
      default: throw new Error(`Unknown tool: ${req.params.name}`);
    }
    return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
  } catch (err) {
    return { isError: true, content: [{ type: "text", text: err.message }] };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);
