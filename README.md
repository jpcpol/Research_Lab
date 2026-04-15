# Aural-Syncro Research Lab

> Plataforma de investigación colaborativa para equipos científicos.  
> Parte del ecosistema **SSPA (Aural-Syncro)** · Dominio: `lab.aural-syncro.com.ar`

---

## ¿Qué es Research Lab?

Research Lab es una plataforma web diseñada para que equipos de investigación científica puedan **organizar, trazar y colaborar** sobre su trabajo académico desde un único entorno seguro. Fue construida con la premisa de que la ciencia se hace en equipo: cada hipótesis, cada referencia bibliográfica, cada avance registrado en la bitácora pertenece al colectivo, no al individuo.

El sistema está pensado especialmente para grupos académicos e instituciones que necesitan:

- Documentar el proceso científico de forma estructurada y auditable.
- Compartir conocimiento entre investigadores con distintos niveles de acceso.
- Integrar sus herramientas de trabajo habituales (Obsidian, GitHub) con la plataforma.
- Operar con soberanía sobre sus datos (infraestructura propia, sin dependencia de terceros).

---

## Funcionalidades principales

### Gestión de proyectos de investigación
Cada proyecto tiene su propio espacio de trabajo con roles diferenciados:
- **PI (Principal Investigator):** control total, aprobación de cambios, configuración de integraciones.
- **Collaborator:** crea y edita contenido, propone cambios al repositorio GitHub del proyecto.
- **Observer:** acceso de solo lectura para revisores externos o evaluadores.

### Bitácora científica
Registro cronológico e inmutable de avances, decisiones, modificaciones y notas del equipo. Cada entrada queda firmada por su autor y no puede ser editada retroactivamente, garantizando la trazabilidad del proceso de investigación.

### Hipótesis
Panel de gestión de hipótesis con estados controlados (`Pendiente → En proceso → Validada / Rechazada / En espera`) y niveles de prioridad. Permite registrar la evolución de cada hipótesis con descripción completa y autoría.

### Hitos y requerimientos
Gestión de hitos con fechas límite y listas de requerimientos asociados. Cada requerimiento puede asignarse a un miembro del equipo y tiene su propio ciclo de vida (`pendiente → en progreso → hecho / bloqueado`).

### Knowledge Graph
Visualización interactiva de las relaciones semánticas entre todos los elementos del proyecto (notas, hipótesis, referencias, hitos, entradas de bitácora). Las relaciones pueden ser manuales o detectadas automáticamente a partir de `[[wikilinks]]` en el contenido de las notas.

Tipos de relación disponibles: `relacionado`, `soporta`, `contradice`, `usa_método`, `construye_sobre`, `replica`, `refuta`, `define`, `ejemplifica`.

### Referencias bibliográficas
Gestor de bibliografía con soporte para tipos `paper`, `book`, `dataset`, `standard`, `web` y `other`. Admite DOI, URL, resumen y notas del equipo. Exportable a GitHub como archivo Markdown con autoría.

### Documentos colaborativos
Editor de documentos con sincronización bidireccional hacia bóvedas Obsidian. Incluye:
- **Soft lock via Redis:** previene ediciones simultáneas mostrando quién tiene el documento abierto.
- **Detección de conflictos:** si dos colaboradores editan offline, el sistema detecta la divergencia y registra el conflicto para que el PI lo resuelva manualmente.

### Integración con GitHub
Cada proyecto puede conectarse a un repositorio GitHub mediante una **GitHub App** (Installation Token, sin PAT personal). Permite:
- Exportar cualquier elemento (notas, hipótesis, bitácora, hitos, referencias) como archivo Markdown con footer de autoría académica (nombre, institución, ORCID).
- Crear branches y Pull Requests automáticamente.
- Publicar un snapshot del Knowledge Graph como diagrama Mermaid.

### Perfil académico
Cada investigador puede completar su perfil con título académico, institución, departamento, ORCID y sitio web. Estos datos se incluyen automáticamente en los footers de autoría al exportar contenido a GitHub.

---

## Plugin para Obsidian

El plugin oficial permite sincronizar notas y documentos entre la bóveda local de Obsidian y la plataforma, con anti-colisión de ediciones en tiempo real.

**Instalación manual:**
1. Descargar `main.js` y `manifest.json` desde la sección Obsidian dentro de la plataforma.
2. Copiar ambos archivos en `.obsidian/plugins/sspa-research-lab/` dentro de la bóveda.
3. Activar el plugin y configurar la URL del Lab, el token JWT y el ID del proyecto.

### MCP Bridge para Claude Code
El archivo `obsidian-plugin/mcp-lab-bridge.mjs` es un servidor MCP que permite a **Claude Code** leer y escribir notas en la bóveda de Obsidian con anti-colisión contra la plataforma.

```json
// .mcp.json (en el raíz del proyecto donde uses Claude Code)
{
  "mcpServers": {
    "lab-bridge": {
      "command": "node",
      "args": ["<ruta>/obsidian-plugin/mcp-lab-bridge.mjs"],
      "env": {
        "VAULT_PATH": "<ruta-absoluta-a-la-boveda>",
        "LAB_URL": "https://lab.aural-syncro.com.ar",
        "LAB_TOKEN": "<jwt-del-usuario>",
        "LAB_PROJECT_ID": "<uuid-del-proyecto>"
      }
    }
  }
}
```

---

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | FastAPI (Python 3.11), SQLAlchemy 2.0, Alembic |
| Base de datos | PostgreSQL 15 (TimescaleDB) |
| Cache / Locks | Redis 7.2 |
| Frontend | SPA Vanilla JS/HTML — i18n ES/EN incorporado |
| Plugin | TypeScript, esbuild, Obsidian SDK |
| MCP Bridge | Node.js, `@modelcontextprotocol/sdk` |
| Infraestructura | Docker, red compartida `sspa_infra` |
| Dominio | `lab.aural-syncro.com.ar` via Cloudflare Tunnel |

---

## Arquitectura de deploy

Research Lab corre como un servicio Docker dentro de la red interna `sspa_infra` del ecosistema SSPA, junto con el resto de los servicios de la plataforma (PostgreSQL, Redis, Cloudflare Tunnel). No expone puertos a internet directamente; el acceso público pasa por el tunnel de Cloudflare.

```
Internet
   │
   ▼
Cloudflare Tunnel (sspa-cloudflare-tunnel)
   │
   ├─── lab.aural-syncro.com.ar  ──►  sspa_research_lab:8004
   ├─── api.aural-syncro.com.ar  ──►  sspa_management_backend:8000
   └─── ...
```

El contenedor monta el código fuente y los archivos estáticos como volúmenes para permitir actualizaciones sin rebuild completo.

---

## Variables de entorno

Copiar `.env.example` como `.env` y completar los valores reales:

| Variable | Descripción |
|----------|-------------|
| `SECRET_KEY` | Clave JWT (32 bytes hex, `openssl rand -hex 32`) |
| `TOKEN_EXPIRE_HOURS` | Duración del token en horas (default: 72) |
| `DATABASE_URL` | Conexión PostgreSQL |
| `REDIS_URL` | Conexión Redis con auth (`redis://:PASS@redis:6379/1`) |
| `GITHUB_TOKEN_ENCRYPTION_KEY` | AES-256 para cifrar claves privadas de GitHub App (64 hex chars) |
| `APP_URL` | URL pública usada en los emails de invitación |
| `GMAIL_USER` | Cuenta Gmail para envío de PINs y notificaciones |
| `GMAIL_APP_PASSWORD` | App Password de 16 caracteres de Gmail |
| `REGISTRATION_OPEN` | `true` = registro abierto, `false` = solo por invitación (default) |

---

## Comandos operativos

```bash
# Levantar el servicio (asume que sspa_infra está corriendo)
docker compose up -d --no-deps research-lab

# Rebuild completo (cuando cambia requirements.txt o el Dockerfile)
docker compose build research-lab && docker compose up -d --no-deps research-lab

# Ver logs en tiempo real
docker logs -f sspa_research_lab

# Ejecutar un comando interno (sin docker exec -it)
docker exec sspa_research_lab sh -c "cd /app && python -c 'print(\"ok\")'"

# Compilar y deployar el plugin Obsidian
bash obsidian-plugin/build-and-deploy.sh
```

---

## Modelo de acceso e invitaciones

El registro público está **deshabilitado por defecto** (`REGISTRATION_OPEN=false`). Los nuevos investigadores acceden únicamente mediante invitación:

1. Un PI envía una invitación por email desde la plataforma.
2. El invitado recibe un enlace con token único.
3. Al ingresar, el sistema envía un PIN de 6 dígitos al email (válido 15 minutos).
4. Con el PIN, el invitado crea su cuenta y queda vinculado al proyecto.

Los colaboradores existentes también usan PIN por email en cada inicio de sesión (2FA implícito), sin depender de aplicaciones de autenticación externas.

---

## Convenciones del proyecto

- Código y comentarios en **inglés**; comunicación del equipo en **español**.
- Errores HTTP del backend en inglés (el frontend gestiona la traducción i18n).
- Las migraciones de schema se realizan mediante `_run_migrations()` en `app/main.py` (inline, idempotentes). La migración a Alembic está pendiente (ver DT-RL-028).
- Deuda técnica registrada en `deuda_tecncica/DT-Master.md`.
- Para recargar variables de entorno: `docker compose up -d --no-deps research-lab` (nunca `docker restart`).

---

## Licencia y contexto

Research Lab es un proyecto interno de **Aural-Syncro**. Su desarrollo está orientado a facilitar la investigación científica colaborativa con herramientas modernas, accesibles y bajo control total del equipo.
