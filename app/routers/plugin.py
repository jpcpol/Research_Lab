"""
Research Lab — Obsidian Plugin distribution router
Serves plugin version info and compiled main.js for download.
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.routers.auth import get_current_user

router = APIRouter(tags=["plugin"])

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "plugin")
_VERSION_FILE = os.path.join(_STATIC_DIR, "plugin_version.json")
_MAIN_JS = os.path.join(_STATIC_DIR, "main.js")


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
