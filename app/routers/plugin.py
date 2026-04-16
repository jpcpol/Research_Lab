"""
Research Lab — Obsidian Plugin distribution router
Serves plugin version info, compiled main.js, MCP Bridge, and personalized installer.
"""
import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app import models

router = APIRouter(tags=["plugin"])

_STATIC_DIR    = os.path.join(os.path.dirname(__file__), "..", "..", "static", "plugin")
_VERSION_FILE  = os.path.join(_STATIC_DIR, "plugin_version.json")
_MAIN_JS       = os.path.join(_STATIC_DIR, "main.js")
_INSTALLER_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "installer")
_INSTALLER_TPL = os.path.join(_INSTALLER_DIR, "install-lab-tools.mjs")
_MCP_BRIDGE    = os.path.join(os.path.dirname(__file__), "..", "..", "obsidian-plugin", "mcp-lab-bridge.mjs")


def _read_manifest() -> dict:
    if not os.path.isfile(_VERSION_FILE):
        raise HTTPException(404, "No plugin build available yet")
    with open(_VERSION_FILE, encoding="utf-8") as f:
        return json.load(f)


# GET /api/v1/plugin/latest  — version info (requires auth)
@router.get("/plugin/latest")
def plugin_latest(current_user=Depends(get_current_user)):
    manifest = _read_manifest()
    if not manifest.get("build_available"):
        raise HTTPException(404, "No plugin build available yet")
    return {
        "version":     manifest.get("version", "unknown"),
        "filename":    manifest.get("filename", "main.js"),
        "released_at": manifest.get("released_at"),
    }


# GET /api/v1/plugin/download  — serve compiled main.js (public)
@router.get("/plugin/download", include_in_schema=False)
def plugin_download():
    manifest = _read_manifest()
    if not manifest.get("build_available") or not os.path.isfile(_MAIN_JS):
        raise HTTPException(404, "No plugin build available yet")
    version = manifest.get("version", "1.0.0")
    filename = f"sspa-research-lab-{version}.js"
    return FileResponse(
        _MAIN_JS,
        media_type="application/javascript",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# GET /api/v1/plugin/mcp-bridge  — serve mcp-lab-bridge.mjs (auth required)
@router.get("/plugin/mcp-bridge", include_in_schema=False)
def mcp_bridge_download(current_user=Depends(get_current_user)):
    if not os.path.isfile(_MCP_BRIDGE):
        raise HTTPException(404, "MCP Bridge file not found")
    return FileResponse(
        _MCP_BRIDGE,
        media_type="application/javascript",
        filename="mcp-lab-bridge.mjs",
        headers={"Content-Disposition": 'attachment; filename="mcp-lab-bridge.mjs"'},
    )


# GET /api/v1/plugin/installer?project_id=UUID  — personalized installer (auth required)
@router.get("/plugin/installer", include_in_schema=False)
def plugin_installer(
    request: Request,
    project_id: str = Query(..., description="Project UUID"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not os.path.isfile(_INSTALLER_TPL):
        raise HTTPException(404, "Installer template not found")

    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Extract raw JWT from Authorization header to embed in installer
    auth_header = request.headers.get("Authorization", "")
    raw_token = auth_header.removeprefix("Bearer ").strip()

    lab_url = str(request.base_url).rstrip("/")

    with open(_INSTALLER_TPL, encoding="utf-8") as f:
        template = f.read()

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    installer = (
        template
        .replace("__LAB_URL__",        lab_url)
        .replace("__LAB_TOKEN__",       raw_token)
        .replace("__LAB_PROJECT_ID__",  project_id)
        .replace("__USER_NAME__",       current_user.name)
        .replace("__PROJECT_NAME__",    project.name)
        .replace("__GENERATED_AT__",    generated_at)
    )

    return Response(
        content=installer,
        media_type="application/javascript",
        headers={"Content-Disposition": 'attachment; filename="install-lab-tools.mjs"'},
    )
