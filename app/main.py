from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.database import engine, Base
from app.routers import auth, projects, journal, hypotheses, milestones, notes, references, graph, github, documents, plugin, project_config, ai_chat

# Create all tables on startup
Base.metadata.create_all(bind=engine)

# ── Inline column migrations (ADD COLUMN IF NOT EXISTS — safe to re-run) ──────
def _run_migrations() -> None:
    from sqlalchemy import text
    stmts = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_email VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_change_pin VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email_change_pin_expires_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_pin VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS login_pin_expires_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS title VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS institution VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS orcid VARCHAR",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS website VARCHAR",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_token_enc VARCHAR",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_installation_id VARCHAR",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_owner VARCHAR",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_repo VARCHAR",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_app_id VARCHAR",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS github_app_private_key_enc TEXT",
        # DT-RL-010 — Documents
        """CREATE TABLE IF NOT EXISTS documents (
            id           VARCHAR PRIMARY KEY,
            project_id   VARCHAR REFERENCES projects(id) ON DELETE CASCADE,
            created_by   VARCHAR REFERENCES users(id),
            title        VARCHAR NOT NULL,
            body         TEXT DEFAULT '',
            current_hash VARCHAR,
            last_editor  VARCHAR REFERENCES users(id),
            created_at   TIMESTAMP WITH TIME ZONE,
            updated_at   TIMESTAMP WITH TIME ZONE
        )""",
        """CREATE TABLE IF NOT EXISTS doc_conflicts (
            id           VARCHAR PRIMARY KEY,
            document_id  VARCHAR REFERENCES documents(id) ON DELETE CASCADE,
            content_a    TEXT,
            content_b    TEXT,
            submitted_by VARCHAR REFERENCES users(id),
            resolved_at  TIMESTAMP WITH TIME ZONE,
            resolved_by  VARCHAR REFERENCES users(id),
            resolution   VARCHAR,
            created_at   TIMESTAMP WITH TIME ZONE
        )""",
        # DT-RL-014 / Points 1-4 — Project feature config + member features
        """CREATE TABLE IF NOT EXISTS project_feature_configs (
            id               VARCHAR PRIMARY KEY,
            project_id       VARCHAR UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
            feat_obsidian    BOOLEAN DEFAULT FALSE,
            feat_ai_local    BOOLEAN DEFAULT FALSE,
            feat_ai_web      BOOLEAN DEFAULT FALSE,
            feat_github_push BOOLEAN DEFAULT FALSE,
            feat_wiki        BOOLEAN DEFAULT FALSE,
            ai_provider      VARCHAR,
            ai_model         VARCHAR,
            ai_api_key_enc   TEXT,
            ai_instructions  TEXT,
            ai_mcp_enabled   BOOLEAN DEFAULT FALSE,
            updated_at       TIMESTAMP WITH TIME ZONE
        )""",
        """CREATE TABLE IF NOT EXISTS project_member_features (
            id               VARCHAR PRIMARY KEY,
            project_id       VARCHAR REFERENCES projects(id) ON DELETE CASCADE,
            user_id          VARCHAR REFERENCES users(id)    ON DELETE CASCADE,
            feat_obsidian    BOOLEAN DEFAULT FALSE,
            feat_ai_local    BOOLEAN DEFAULT FALSE,
            feat_ai_web      BOOLEAN DEFAULT FALSE,
            feat_github_push BOOLEAN DEFAULT FALSE,
            feat_wiki        BOOLEAN DEFAULT FALSE,
            updated_at       TIMESTAMP WITH TIME ZONE,
            UNIQUE (project_id, user_id)
        )""",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))

_run_migrations()

app = FastAPI(
    title="Aural-Syncro Research Platform",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(auth.router,        prefix="/api/v1")
app.include_router(projects.router,    prefix="/api/v1")
app.include_router(journal.router,     prefix="/api/v1")
app.include_router(hypotheses.router,  prefix="/api/v1")
app.include_router(milestones.router,  prefix="/api/v1")
app.include_router(notes.router,       prefix="/api/v1")
app.include_router(references.router,  prefix="/api/v1")
app.include_router(graph.router,       prefix="/api/v1")
app.include_router(github.router,      prefix="/api/v1")
app.include_router(documents.router,      prefix="/api/v1")
app.include_router(plugin.router,         prefix="/api/v1")
app.include_router(project_config.router, prefix="/api/v1")
app.include_router(ai_chat.router,        prefix="/api/v1")

# Serve SPA
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_ico():
        return FileResponse(os.path.join(static_dir, "favicon.ico"))

    @app.get("/favicon.png", include_in_schema=False)
    def favicon_png():
        return FileResponse(os.path.join(static_dir, "favicon.png"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        index = os.path.join(static_dir, "index.html")
        return FileResponse(index)
