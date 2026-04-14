# DT-Master — Research Lab (standalone)
> Auditado: 2026-04-14 | Próxima revisión: al finalizar cada sprint

---

## Convenciones
| Severidad | Descripción |
|-----------|-------------|
| 🔴 CRÍTICO | Rompe el servicio en producción |
| 🟠 ALTO    | Riesgo de seguridad o falla en deploy standalone |
| 🟡 MEDIO   | Funcionalidad comprometida / objetivo incumplido |
| 🔵 BAJO    | Deuda de calidad o inconsistencia cosmética |

Estado: `[ ]` pendiente · `[~]` en progreso · `[x]` resuelto

---

## Items activos

### 🔴 DT-RL-018 — `build-and-deploy.sh`: path apunta al monorepo (roto)
**Estado:** `[ ]`  
**Archivo:** [obsidian-plugin/build-and-deploy.sh](../obsidian-plugin/build-and-deploy.sh) · línea 13  
**Problema:** `TARGET_DIR="${REPO_ROOT}/investigacion/static/plugin"` — apunta a la ruta del monorepo SSPA.  
El repo standalone no tiene carpeta `investigacion/`; el build deploy fallará o escribirá en un path inexistente.  
**Fix:** cambiar a `TARGET_DIR="${REPO_ROOT}/static/plugin"`.

---

### 🔴 DT-RL-019 — `cryptography` no está en `requirements.txt`
**Estado:** `[ ]`  
**Archivos:** [requirements.txt](../requirements.txt), [app/routers/github.py](../app/routers/github.py) · líneas 17–19  
**Problema:** `github.py` importa `from cryptography.hazmat.primitives...` pero el paquete `cryptography` no está declarado.  
El contenedor falla al arrancar con `ModuleNotFoundError`.  
**Fix:** agregar `cryptography>=42.0.0` a `requirements.txt`.

---

### 🟠 DT-RL-020 — Docker Compose sin Redis ni PostgreSQL (no funciona standalone)
**Estado:** `[ ]`  
**Archivo:** [docker-compose.yml](../docker-compose.yml)  
**Problema:** el compose solo define el servicio `research-lab` y depende de la red externa `sspa_infra` (del monorepo SSPA).  
Sin esa red activa, el servicio no puede alcanzar `postgres:5432` ni `sspa_redis:6379`.  
Un deploy verdaderamente standalone o en otro servidor falla silenciosamente (Postgres) o degrada locks (Redis).  
**Fix:** agregar servicios `postgres` y `redis` propios (con `profiles: ["standalone"]` para no romper el deploy integrado con SSPA), o documentar explícitamente que requiere el stack de infra corriendo.

---

### 🟠 DT-RL-021 — `.env.example` incompleto: faltan `REDIS_URL` y `GITHUB_TOKEN_ENCRYPTION_KEY`
**Estado:** `[ ]`  
**Archivo:** [.env.example](../.env.example)  
**Problema:** dos variables críticas no están documentadas:
- `REDIS_URL` — requerida por `documents.py` para soft locks (default hardcodeado: `redis://sspa_redis:6379/1`).
- `GITHUB_TOKEN_ENCRYPTION_KEY` — requerida por `github.py` para cifrar/descifrar claves de GitHub App (sin ella → HTTP 500 en todos los endpoints de GitHub).  
**Fix:** agregar ambas variables con comentarios explicativos en `.env.example`.

---

### 🟠 DT-RL-022 — Sin `.gitignore` — riesgo de commit de secrets
**Estado:** `[ ]`  
**Problema:** el directorio no tiene `.gitignore`. Sin él, `git add .` incluiría `.env` (credenciales JWT, Gmail, GitHub), `__pycache__/`, `*.pyc`, `static/avatars/` (datos de usuarios).  
**Fix:** crear `.gitignore` con al menos: `.env`, `__pycache__/`, `*.pyc`, `static/avatars/*`, `!static/avatars/.gitkeep`, `static/plugin/main.js`.

---

### 🟡 DT-RL-023 — CORS wildcard `allow_origins=["*"]` en producción
**Estado:** `[ ]`  
**Archivo:** [app/main.py](../app/main.py) · línea 73  
**Problema:** cualquier origen puede llamar a la API. Aceptable en dev, riesgo en producción donde el dominio es fijo (`lab.aural-syncro.com.ar` + posiblemente SSPA Management).  
**Fix:** leer `ALLOWED_ORIGINS` desde env y restringir en producción.

---

### 🟡 DT-RL-024 — Landing page en `/` no implementada (objetivo pendiente)
**Estado:** `[ ]`  
**Archivo:** [app/main.py](../app/main.py) · línea 106  
**Problema:** la ruta `/{full_path:path}` sirve siempre `index.html` (la SPA). El objetivo establece:
- `/` → landing page (hero + features + CTA "Solicitar acceso").
- `/app` (o `/login`) → SPA actual.
- Links desde SSPA Management → van directo a `/app`, nunca a `/`.  
**Fix:** crear `static/landing.html`, agregar rutas explícitas `/` → landing y `/app` → SPA, y actualizar el catch-all para excluir ambas.

---

### 🟡 DT-RL-025 — GitHub Actions CI/CD para distribución de plugin no existe
**Estado:** `[ ]`  
**Problema:** el objetivo define un workflow que al tagear `v*.*.*`:
1. ejecuta `obsidian-plugin/build-and-deploy.sh`  
2. commitea `static/plugin/main.js` y `plugin_version.json`  
3. (opcional) sube como Release asset  
El directorio `.github/workflows/` no existe.  
**Relacionado con:** DT-RL-018 (el script tiene el path roto, debe resolverse primero).

---

### 🟡 DT-RL-026 — `static/plugin/main.js` no existe — endpoint `/plugin/download` retorna 404
**Estado:** `[ ]`  
**Archivo:** [static/plugin/plugin_version.json](../static/plugin/plugin_version.json)  
**Problema:** `plugin_version.json` tiene `"build_available": false` y no existe `main.js`.  
El endpoint `GET /api/v1/plugin/download` y la card de descarga en la SPA no funcionan.  
**Fix:** ejecutar `bash obsidian-plugin/build-and-deploy.sh` una vez que DT-RL-018 esté resuelto y el entorno de build (Node + tsc) esté disponible.

---

### 🟡 DT-RL-028 — Inline migrations en `main.py` en lugar de Alembic
**Estado:** `[ ]`  
**Archivo:** [app/main.py](../app/main.py) · líneas 14–63  
**Problema:** las migraciones de schema se ejecutan como `ALTER TABLE IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` en el arranque de la app, violando la regla de colaboración "nunca saltar migraciones Alembic".  
- Riesgo de divergencia entre environments al crecer el schema.  
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` no es soportado por SQLite < 3.37.  
**Fix (mediano plazo):** inicializar Alembic, portar las migraciones inline a versiones numeradas, y eliminar `_run_migrations()`.

---

### 🔵 DT-RL-027 — Typo en nombre del directorio y archivo de deuda técnica
**Estado:** `[ ]`  
**Problema:**
- Directorio: `deuda_tecncica/` → debería ser `deuda_tecnica/` (letra transpuesta).
- Archivo: `DT-Master-MD` sin extensión `.md` → los editores no lo reconocen como Markdown.  
**Fix:** renombrar directorio y archivo (requiere actualizar referencias en el repo y en este documento).

---

### 🔵 DT-RL-029 — `plugin.py` importa `get_current_user` desde el router en lugar de `app.auth`
**Estado:** `[ ]`  
**Archivo:** [app/routers/plugin.py](../app/routers/plugin.py) · línea 11  
**Problema:** `from app.routers.auth import get_current_user` — importa el símbolo re-exportado por el router en lugar de la fuente canónica `app.auth`. Funciona pero es frágil.  
**Fix:** cambiar a `from app.auth import get_current_user`.

---

## Items resueltos / portados del monorepo SSPA

### [x] DT-RL-009 — GitHub App Integration (rev-3)
Credenciales por proyecto cifradas con AES-256-GCM. Installation tokens cacheados (1 h).  
Footer de autoría en cada archivo exportado. Portado como [app/routers/github.py](../app/routers/github.py).

### [x] DT-RL-010 — Documentos colaborativos + soft lock + resolución de conflictos
Modelo `Document` + `DocConflict`. Optimistic lock con SHA-256. Soft lock vía Redis con TTL 10 min.  
Portado como [app/routers/documents.py](../app/routers/documents.py).

### [~] DT-RL-014 — MCP Bridge: Claude Code ↔ Obsidian vault anti-colisión (Módulo E)
`mcp-lab-bridge.mjs` implementado con 4 tools (`read_note`, `write_note`, `list_notes`, `search_notes`).  
**Pendiente:**
- Documentar setup completo en README.
- Agregar sección Obsidian en la SPA del Lab con instrucciones de configuración del MCP.
- Verificar API `createServer` vs clase `Server` del SDK MCP v1.x (posible incompatibilidad).

### [x] DT-RL-017 — Plugin distribution router
`GET /api/v1/plugin/latest` y `GET /api/v1/plugin/download` implementados en [app/routers/plugin.py](../app/routers/plugin.py).  
Card de descarga y `loadPluginInfo()` / `downloadPlugin()` agregados a la SPA.  
`build-and-deploy.sh` y `plugin_version.json` placeholder creados.  
**Bloqueado por:** DT-RL-018 (path roto en el script) y DT-RL-026 (main.js no compilado).
