import {
  App,
  Notice,
  Plugin,
  PluginSettingTab,
  Setting,
  TFile,
} from "obsidian";

// ── SHA-256 (Web Crypto — available in Obsidian's Electron env) ───────────────

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ── Settings ──────────────────────────────────────────────────────────────────

interface LabPluginSettings {
  serverUrl:  string;   // e.g. https://lab.aural-syncro.com.ar
  jwtToken:   string;
  projectId:  string;
  // Map: vault relative path → Lab document id
  docMap:     Record<string, string>;
}

const DEFAULTS: LabPluginSettings = {
  serverUrl:  "",
  jwtToken:   "",
  projectId:  "",
  docMap:     {},
};

// ── Plugin ────────────────────────────────────────────────────────────────────

// Refresh the token 10 minutes before it expires (or immediately if already expired)
const REFRESH_AHEAD_MS = 10 * 60 * 1000;

function jwtExpiry(token: string): number | null {
  try {
    const b64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(atob(b64));
    return typeof payload.exp === "number" ? payload.exp * 1000 : null;
  } catch {
    return null;
  }
}

export default class LabPlugin extends Plugin {
  settings: LabPluginSettings = DEFAULTS;

  private _openHashes: Record<string, string> = {};
  private _refreshTimer: ReturnType<typeof setTimeout> | null = null;

  async onload() {
    await this.loadSettings();
    this.addSettingTab(new LabSettingTab(this.app, this));
    this._scheduleTokenRefresh();

    // ── Command: sync current file ──────────────────────────────────────────
    this.addCommand({
      id:   "sync-to-lab",
      name: "Sync to Research Lab",
      checkCallback: (checking) => {
        const file = this.app.workspace.getActiveFile();
        if (!file || file.extension !== "md") return false;
        if (!checking) this._syncFile(file);
        return true;
      },
    });

    // ── Command: renew token manually ───────────────────────────────────────
    this.addCommand({
      id:   "renew-token",
      name: "Research Lab: Renovar token JWT",
      callback: () => this._refreshToken(),
    });

    // ── Lifecycle hooks ─────────────────────────────────────────────────────
    this.registerEvent(
      this.app.workspace.on("file-open", async (file) => {
        if (!file || file.extension !== "md") return;
        await this._onFileOpen(file);
      })
    );

    this.registerEvent(
      this.app.vault.on("modify", async (file) => {
        if (!(file instanceof TFile) || file.extension !== "md") return;
        if (this.app.workspace.getActiveFile()?.path !== file.path) return;
        await this._syncFile(file);
      })
    );

    this.registerEvent(
      this.app.workspace.on("active-leaf-change", async () => {
        const prev = this._getLastOpenPath();
        if (prev) await this._releaseLock(prev);
      })
    );
  }

  onunload() {
    if (this._refreshTimer) clearTimeout(this._refreshTimer);
    for (const path of Object.keys(this._openHashes)) {
      this._releaseLock(path).catch(() => {});
    }
  }

  // ── Token auto-refresh ──────────────────────────────────────────────────────

  private _scheduleTokenRefresh(): void {
    if (this._refreshTimer) clearTimeout(this._refreshTimer);
    if (!this.settings.jwtToken) return;

    const exp = jwtExpiry(this.settings.jwtToken);
    if (!exp) return;

    const delay = Math.max(0, exp - Date.now() - REFRESH_AHEAD_MS);
    this._refreshTimer = setTimeout(() => this._refreshToken(), delay);
  }

  private async _refreshToken(): Promise<void> {
    if (!this._isConfigured()) return;
    try {
      const res  = await this._api("POST /auth/refresh", "POST", null);
      if (!res.ok) { new Notice("Lab: no se pudo renovar el token"); return; }
      const data = await res.json();
      this.settings.jwtToken = data.access_token;
      await this.saveSettings();
      this._scheduleTokenRefresh();
      new Notice("Lab: token renovado automáticamente");
    } catch {
      // Silent — will retry on next Obsidian startup
    }
  }

  // ── File lifecycle ──────────────────────────────────────────────────────────

  private _lastOpenPath: string | null = null;
  private _getLastOpenPath(): string | null { return this._lastOpenPath; }

  private async _onFileOpen(file: TFile): Promise<void> {
    if (!this._isConfigured()) return;
    const docId = await this._ensureDocument(file);
    if (!docId) return;

    this._lastOpenPath = file.path;

    // Acquire soft lock
    try {
      const res = await this._api(
        `PUT /projects/${this.settings.projectId}/documents/${docId}/lock`,
        "PUT",
        null
      );
      if (res.status === 409) {
        const data = await res.json();
        new Notice(`⚠️ Lab: documento bloqueado por ${data.detail?.split("por ")[1] ?? "otro usuario"}`);
      }
    } catch { /* lock is best-effort */ }

    // Record hash of server content for conflict detection
    const content = await this.app.vault.read(file);
    this._openHashes[file.path] = await sha256(content);
  }

  private async _syncFile(file: TFile): Promise<void> {
    if (!this._isConfigured()) return;
    const docId = await this._ensureDocument(file);
    if (!docId) return;

    const content      = await this.app.vault.read(file);
    const version_hash = this._openHashes[file.path] ?? null;

    try {
      const res = await this._api(
        `POST /projects/${this.settings.projectId}/documents/${docId}/sync`,
        "POST",
        { content, version_hash }
      );

      if (res.status === 409) {
        new Notice("⚠️ Lab: conflicto detectado — revisá la web para resolver");
        return;
      }
      if (!res.ok) {
        new Notice(`Lab sync error ${res.status}`);
        return;
      }

      // Update hash to current content after successful sync
      this._openHashes[file.path] = await sha256(content);
    } catch (err) {
      new Notice("Lab sync: sin conexión");
    }
  }

  private async _releaseLock(filePath: string): Promise<void> {
    if (!this._isConfigured()) return;
    const docId = this.settings.docMap[filePath];
    if (!docId) return;
    delete this._openHashes[filePath];
    try {
      await this._api(
        `DELETE /projects/${this.settings.projectId}/documents/${docId}/lock`,
        "DELETE",
        null
      );
    } catch { /* best-effort */ }
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  /**
   * Get or create the Lab document for this vault file.
   * Stores the mapping in settings.docMap keyed by vault path.
   */
  private async _ensureDocument(file: TFile): Promise<string | null> {
    const existing = this.settings.docMap[file.path];
    if (existing) return existing;

    try {
      const res = await this._api(
        `POST /projects/${this.settings.projectId}/documents`,
        "POST",
        { title: file.basename, body: await this.app.vault.read(file) }
      );
      if (!res.ok) return null;
      const data = await res.json();
      this.settings.docMap[file.path] = data.id;
      await this.saveSettings();
      return data.id;
    } catch {
      return null;
    }
  }

  private _isConfigured(): boolean {
    return !!(
      this.settings.serverUrl &&
      this.settings.jwtToken &&
      this.settings.projectId
    );
  }

  private async _api(
    path: string,
    method: string,
    body: unknown
  ): Promise<Response> {
    // path starts with e.g. "POST /projects/..."  — strip the method prefix
    const url = `${this.settings.serverUrl.replace(/\/$/, "")}/api/v1${path.replace(/^(GET|POST|PUT|PATCH|DELETE) /, "")}`;
    return fetch(url, {
      method,
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${this.settings.jwtToken}`,
      },
      ...(body !== null ? { body: JSON.stringify(body) } : {}),
    });
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULTS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
    this._scheduleTokenRefresh();   // reschedule whenever token changes
  }
}

// ── Settings Tab ──────────────────────────────────────────────────────────────

class LabSettingTab extends PluginSettingTab {
  plugin: LabPlugin;

  constructor(app: App, plugin: LabPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "SSPA Research Lab" });

    new Setting(containerEl)
      .setName("Server URL")
      .setDesc("URL base del Lab (ej. https://lab.aural-syncro.com.ar)")
      .addText((t) =>
        t
          .setPlaceholder("https://lab.aural-syncro.com.ar")
          .setValue(this.plugin.settings.serverUrl)
          .onChange(async (v) => {
            this.plugin.settings.serverUrl = v.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("JWT Token")
      .setDesc("Token de autenticación — obtenelo desde el Lab → Perfil")
      .addText((t) =>
        t
          .setPlaceholder("eyJ...")
          .setValue(this.plugin.settings.jwtToken)
          .onChange(async (v) => {
            this.plugin.settings.jwtToken = v.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Project ID")
      .setDesc("ID del proyecto (UUID — copialo desde la URL del Lab)")
      .addText((t) =>
        t
          .setPlaceholder("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
          .setValue(this.plugin.settings.projectId)
          .onChange(async (v) => {
            this.plugin.settings.projectId = v.trim();
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Limpiar mapa de documentos")
      .setDesc("Borra el mapa de archivos ↔ IDs del Lab (útil si cambiaste de proyecto).")
      .addButton((btn) =>
        btn.setButtonText("Limpiar").onClick(async () => {
          this.plugin.settings.docMap = {};
          await this.plugin.saveSettings();
          new Notice("Mapa de documentos limpiado");
        })
      );
  }
}
