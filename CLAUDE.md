# Research Lab — Plataforma de Investigación Científica

## Descripción

SPA colaborativa para equipos de investigación científica. Gestiona hipótesis, bitácora inmutable, referencias bibliográficas, milestones, grafo de conocimiento semántico y sincronización con Obsidian. Forma parte del ecosistema SSPA en `app.researchlab.com.ar`.

## Stack

- **Backend**: FastAPI 0.115 async · PostgreSQL 15 (TimescaleDB) · Redis 7.2 · SQLAlchemy 2 (Alembic pendiente — DT-RL-028)
- **Frontend**: SPA vanilla JS/HTML/CSS con i18n (ES/EN) en `static/`
- **Plugin**: TypeScript + Obsidian SDK + MCP bridge (Node.js) en `obsidian-plugin/`
- **Auth**: JWT + bcrypt · SlowAPI rate limiting
- **Crypto**: AES-256-GCM para API keys · RSA/ECDH en MCP bridge
- **Infra**: Docker · Cloudflare Tunnel · red `sspa_infra` (compartida con SSPA)

## Puerto de desarrollo

- API + SPA: `http://localhost:8004`

## Módulos del backend (`app/routers/`)

| Módulo | Función |
| --------------- | ----------------------------------------------- |
| `auth.py` | Login, tokens JWT |
| `register.py` | Registro y solicitudes |
| `projects.py` | CRUD de proyectos de investigación |
| `hypotheses.py` | Gestión de hipótesis con estado de validación |
| `notes.py` | Notas con soft-lock anti-colisión (Redis) |
| `documents.py` | Documentos de proyecto |
| `references.py` | Bibliografía (papers, libros, datasets, normas) |
| `journal.py` | Bitácora científica inmutable |
| `milestones.py` | Hitos y requerimientos |
| `graph.py` | Grafo de conocimiento semántico con wikilinks |
| `ai_chat.py` | Chat IA con Claude (claude-sonnet-4-6 default) |
| `github.py` | Integración GitHub App |
| `plugin.py` | API para el plugin de Obsidian |
| `project_config.py` | Feature toggles y permisos por proyecto/miembro |
| `mcp.py` | MCP Server (Streamable HTTP, JSON-RPC 2.0) para Claude Code |

## Grafo de conocimiento

`app/routers/graph.py` detecta `[[wikilinks]]` automáticamente y los tipifica:

Relaciones: `relacionado`, `soporta`, `contradice`, `usa_método`, `construye_sobre`, `replica`, `refuta`, `define`, `ejemplifica`

## Plugin de Obsidian + MCP Bridge (stdio)

`obsidian-plugin/mcp-lab-bridge.mjs` — MCP Server stdio transport (`@modelcontextprotocol/sdk` v1.x):

- `read_note` / `write_note` (con soft-lock anti-colisión vía API)
- `list_notes` / `search_notes`

Requiere `.mcp.json` con: `VAULT_PATH`, `LAB_URL`, `LAB_TOKEN`, `LAB_PROJECT_ID`.

## MCP Server nativo (Streamable HTTP)

`app/routers/mcp.py` — JSON-RPC 2.0 en `/api/v1/mcp`. Tools: `list_projects`, `get_project_overview`, `list_hypotheses`, `create_hypothesis`, `list_journal`, `search`, `propose_pr`. Auth: `mcp_token` de usuario (independiente del JWT de sesión).

## Integración Claude API

`app/routers/ai_chat.py`:
- Modelo por defecto: `claude-sonnet-4-6`
- Configurable por proyecto en `ProjectFeatureConfig`
- Requiere `feat_ai_web=True` a nivel proyecto y miembro
- Historial máx. 10 mensajes · max_tokens: 1024
- Endpoints adicionales: `/ai/auto-push`, `/ai/changelog`, `/ai/weekly-summary`

## Wiki de Conocimiento

Wiki personal en: `c:\Users\Usuario\Documents\Aural Syncro\Obsidian`

**Nota**: el MCP bridge de este proyecto (`obsidian-plugin/mcp-lab-bridge.mjs`) puede leer y escribir directamente en el vault del wiki — conexión bidireccional nativa.

**Consultar el wiki cuando:**

- Necesites contexto sobre patrones de arquitectura reutilizables en el ecosistema Aural Syncro
- Busques decisiones tomadas en proyectos relacionados (SSPA, @nanohero)

**Actualizar el wiki cuando:**

- Implementes un patrón de grafo de conocimiento reutilizable
- Documentes la arquitectura del MCP bridge como referencia para otros proyectos
- Página a actualizar: `wiki/proyectos/research-lab.md`
