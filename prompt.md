Prompt para nuevo workspace — Research Lab (standalone)

Contexto del proyecto: Research Lab — Aural-Syncro

Sos mi asistente de desarrollo para separar el Research Lab del monorepo SSPA y convertirlo en un proyecto independiente.

──────────────────────────────────────────────────────
ESTADO ACTUAL
──────────────────────────────────────────────────────
El Research Lab vive en `investigacion/` dentro del monorepo SSPA:
  - Backend: FastAPI (Python), PostgreSQL, Redis, MinIO
  - Frontend: SPA vanilla JS/HTML en `investigacion/static/index.html`
  - Plugin Obsidian: `obsidian-plugin/` (TypeScript, esbuild)
  - MCP Bridge: `obsidian-plugin/mcp-lab-bridge.mjs` (Node.js MCP server)
  - Docker: servicios en el `docker-compose.yml` principal de SSPA
  - Dominio objetivo: `lab.aural-syncro.com.ar`

──────────────────────────────────────────────────────
OBJETIVOS DE ESTA SESIÓN
──────────────────────────────────────────────────────
1. REPOSITORIO SEPARADO
   - Crear la estructura de carpetas del nuevo repo `research-lab/`
   - Extraer todo lo de `investigacion/` + `obsidian-plugin/` a ese repo
   - `docker-compose.yml` propio con los servicios: FastAPI, PostgreSQL, Redis, MinIO
   - `.env.example` y `Dockerfile` propios
   - Variables de entorno necesarias: DATABASE_URL, REDIS_URL, SECRET_KEY, 
     GITHUB_TOKEN_ENCRYPTION_KEY, MINIO_* (mismos nombres que en SSPA)

2. LANDING PAGE
   - Ruta raíz `/` → landing page del Research Lab
   - Ruta `/app` (o `/login`) → SPA actual (sin landing)
   - Desde SSPA Management, los links van directamente a `/app` (nunca a `/`)
   - La landing debe tener: hero ("Investigación colaborativa para equipos científicos"),
     features (Knowledge Graph, Obsidian sync, GitHub integration, i18n ES/EN),
     CTA "Solicitar acceso" → formulario de registro con invitación
   - Mismo design system que la SPA actual (variables CSS: --bg, --surface, --teal, etc.)

3. PLUGIN DISTRIBUTION / CI-CD
   - GitHub Actions workflow: al crear tag `v*.*.*` en el repo
     → ejecutar `obsidian-plugin/build-and-deploy.sh`
     → commitear `investigacion/static/plugin/main.js` y `plugin_version.json` al repo
     → (opcional) subir como Release asset de GitHub
   - El endpoint `GET /api/v1/plugin/download` ya existe y sirve el archivo

4. MCP BRIDGE — completar integración
   - `obsidian-plugin/mcp-lab-bridge.mjs` ya existe con las 4 herramientas
     (read_note, write_note con lock, list_notes, search_notes)
   - Pendiente: documentar setup completo en README y en la sección Obsidian del Lab
   - Pendiente: agregar `npm install @modelcontextprotocol/sdk node-fetch` al build pipeline

──────────────────────────────────────────────────────
REGLAS DE COLABORACIÓN (heredadas del proyecto)
──────────────────────────────────────────────────────
- Código y comentarios en inglés, comunicación conmigo en español
- Nunca saltar migraciones Alembic; nunca `docker compose exec`, usar `docker exec <container> sh -c "cd /app && ..."`
- `docker compose up -d --no-deps <service>` (no docker restart) para recargar env_file
- Secrets en `.env`, nunca en código
- Toda deuda técnica registrada en `deuda_tecnica/DT-Master.md`
- Login siempre: multi-step + PIN email (flujo ya implementado en la SPA actual)
- Errores HTTP en inglés en el backend (el frontend maneja la traducción)
- Auth con `require_project_member()` helper (ya en `app/auth.py`)

──────────────────────────────────────────────────────
ARCHIVOS CLAVE A PORTAR (ya implementados en SSPA)
──────────────────────────────────────────────────────
Backend routers:
  app/routers/auth.py        — login multi-step + PIN + JWT + avatar + profile
  app/routers/projects.py    — CRUD proyectos + invitaciones
  app/routers/journal.py     — bitácora
  app/routers/hypotheses.py  — hipótesis
  app/routers/milestones.py  — hitos
  app/routers/notes.py       — notas con [[wikilinks]]
  app/routers/references.py  — referencias bibliográficas (BibTeX)
  app/routers/documents.py   — documentos colaborativos + soft lock + conflictos
  app/routers/graph.py       — knowledge graph + relaciones semánticas
  app/routers/github.py      — integración GitHub App + commits + file browser
  app/routers/plugin.py      — distribución del plugin Obsidian (nuevo)

Frontend:
  static/index.html          — SPA completa (~5000 líneas), i18n ES/EN implementado

Plugin:
  obsidian-plugin/main.ts            — plugin Obsidian con sync + lock
  obsidian-plugin/mcp-lab-bridge.mjs — MCP server anti-colisión (nuevo)
  obsidian-plugin/build-and-deploy.sh — script compilación + deploy (nuevo)
  obsidian-plugin/mcp.template.json  — template config MCP para Claude Code (nuevo)

──────────────────────────────────────────────────────
PRIMER PASO SUGERIDO
──────────────────────────────────────────────────────
Empezá por definir la estructura de carpetas del nuevo repo y el docker-compose.yml
independiente, luego la landing page, luego el GitHub Actions workflow.
No modifiques el monorepo SSPA — todo el trabajo va en el nuevo workspace.
Resumen de lo implementado en esta sesión:

Archivo	Cambio
investigacion/app/routers/plugin.py	Nuevo router: GET /plugin/latest + GET /plugin/download
investigacion/app/main.py	Registra plugin.router
investigacion/static/plugin/plugin_version.json	Manifiesto del build (placeholder)
investigacion/static/index.html	Card descarga en sección Obsidian + loadPluginInfo() + downloadPlugin() + i18n keys
obsidian-plugin/build-and-deploy.sh	Script compilación + deploy automático
obsidian-plugin/mcp-lab-bridge.mjs	MCP server con 4 tools, lock-aware
obsidian-plugin/mcp.template.json	Template .mcp.json para Claude Code
obsidian-plugin/package.json	Deps MCP agregadas
deuda_tecnica/DT-Master.md	DT-RL-017 registrado; DT-RL-014 actualizado
Para activar el plugin download: ejecutar bash obsidian-plugin/build-and-deploy.sh desde la raíz del repo una vez que tengas el build compilado. Eso actualiza plugin_version.json con "build_available": true y copia main.js al directorio estático.