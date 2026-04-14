import hashlib
import os
import logging
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_project_member
from app.models import now_utc

logger = logging.getLogger(__name__)

# ── Redis connection ───────────────────────────────────────────────────────────
_REDIS_URL = os.getenv("REDIS_URL", "redis://sspa_redis:6379/1")
_LOCK_TTL  = 600   # seconds (10 min)

try:
    _redis = redis_lib.from_url(_REDIS_URL, decode_responses=True)
    _redis.ping()
except Exception as exc:  # pragma: no cover
    logger.warning("Redis unavailable — soft locks disabled: %s", exc)
    _redis = None


def _lock_key(doc_id: str) -> str:
    return f"doc:lock:{doc_id}"


def _get_lock(doc_id: str) -> str | None:
    """Returns the name of the user holding the lock, or None."""
    if _redis is None:
        return None
    return _redis.get(_lock_key(doc_id))


def _set_lock(doc_id: str, user_name: str) -> None:
    if _redis is None:
        return
    _redis.setex(_lock_key(doc_id), _LOCK_TTL, user_name)


def _del_lock(doc_id: str) -> None:
    if _redis is None:
        return
    _redis.delete(_lock_key(doc_id))


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_doc_or_404(project_id: str, doc_id: str, db: Session) -> models.Document:
    doc = db.query(models.Document).filter(
        models.Document.id == doc_id,
        models.Document.project_id == project_id,
    ).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


def _enrich(doc: models.Document) -> dict:
    """Add computed locked_by field to a Document for the response."""
    d = schemas.DocumentOut.model_validate(doc).model_dump()
    d["locked_by"] = _get_lock(doc.id)
    return d


# ── Router ────────────────────────────────────────────────────────────────────

router = APIRouter(tags=["documents"])


# POST /projects/{project_id}/documents
@router.post("/projects/{project_id}/documents",
             response_model=schemas.DocumentOut, status_code=201)
def create_document(
    project_id: str,
    body: schemas.DocumentCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    doc = models.Document(
        project_id=project_id,
        created_by=user.id,
        title=body.title.strip(),
        body=body.body,
        current_hash=_sha256(body.body) if body.body else None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return _enrich(doc)


# GET /projects/{project_id}/documents
@router.get("/projects/{project_id}/documents",
            response_model=list[schemas.DocumentOut])
def list_documents(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    docs = (
        db.query(models.Document)
        .filter(models.Document.project_id == project_id)
        .order_by(models.Document.updated_at.desc())
        .all()
    )
    return [_enrich(d) for d in docs]


# GET /projects/{project_id}/documents/{doc_id}
@router.get("/projects/{project_id}/documents/{doc_id}",
            response_model=schemas.DocumentOut)
def get_document(
    project_id: str, doc_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    doc = _get_doc_or_404(project_id, doc_id, db)
    return _enrich(doc)


# PUT /projects/{project_id}/documents/{doc_id}/lock  — adquirir soft lock
@router.put("/projects/{project_id}/documents/{doc_id}/lock")
def acquire_lock(
    project_id: str, doc_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    _get_doc_or_404(project_id, doc_id, db)

    current = _get_lock(doc_id)
    if current and current != user.name:
        raise HTTPException(409, f"Document locked by {current}")

    _set_lock(doc_id, user.name)
    return {"locked": True, "locked_by": user.name, "ttl_seconds": _LOCK_TTL}


# DELETE /projects/{project_id}/documents/{doc_id}/lock  — liberar soft lock
@router.delete("/projects/{project_id}/documents/{doc_id}/lock", status_code=204)
def release_lock(
    project_id: str, doc_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    _get_doc_or_404(project_id, doc_id, db)
    _del_lock(doc_id)


# POST /projects/{project_id}/documents/{doc_id}/sync  — sync desde Obsidian
@router.post("/projects/{project_id}/documents/{doc_id}/sync",
             response_model=schemas.DocumentOut)
def sync_document(
    project_id: str, doc_id: str,
    body: schemas.DocumentSyncRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    doc = _get_doc_or_404(project_id, doc_id, db)

    # Check optimistic lock
    expected_hash = body.version_hash
    is_new = doc.current_hash is None and expected_hash is None

    if not is_new and doc.current_hash != expected_hash:
        # Conflicto — guardar y notificar
        conflict = models.DocConflict(
            document_id=doc_id,
            content_a=doc.body,
            content_b=body.content,
            submitted_by=user.id,
        )
        db.add(conflict)
        db.commit()
        raise HTTPException(
            409,
            detail={
                "conflict": True,
                "message": "Conflicto detectado — el PI debe resolver en la web",
                "conflict_id": conflict.id,
            },
        )

    doc.body         = body.content
    doc.current_hash = _sha256(body.content)
    doc.last_editor  = user.id
    doc.updated_at   = now_utc()
    db.commit()
    db.refresh(doc)
    return _enrich(doc)


# PATCH /projects/{project_id}/documents/{doc_id}  — edición web directa
@router.patch("/projects/{project_id}/documents/{doc_id}",
              response_model=schemas.DocumentOut)
def update_document(
    project_id: str, doc_id: str,
    body: schemas.DocumentUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    doc = _get_doc_or_404(project_id, doc_id, db)

    if body.title is not None:
        doc.title = body.title.strip()
    if body.body is not None:
        doc.body         = body.body
        doc.current_hash = _sha256(body.body)
        doc.last_editor  = user.id
    doc.updated_at = now_utc()
    db.commit()
    db.refresh(doc)
    return _enrich(doc)


# DELETE /projects/{project_id}/documents/{doc_id}
@router.delete("/projects/{project_id}/documents/{doc_id}", status_code=204)
def delete_document(
    project_id: str, doc_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    doc = _get_doc_or_404(project_id, doc_id, db)
    _del_lock(doc_id)
    db.delete(doc)
    db.commit()


# GET /projects/{project_id}/conflicts  — listar conflictos pendientes (PI)
@router.get("/projects/{project_id}/conflicts",
            response_model=list[schemas.DocConflictOut])
def list_conflicts(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    conflicts = (
        db.query(models.DocConflict)
        .join(models.Document)
        .filter(
            models.Document.project_id == project_id,
            models.DocConflict.resolved_at.is_(None),
        )
        .order_by(models.DocConflict.created_at.desc())
        .all()
    )
    return conflicts


# POST /projects/{project_id}/conflicts/{conflict_id}/resolve  — resolver (PI)
@router.post("/projects/{project_id}/conflicts/{conflict_id}/resolve",
             response_model=schemas.DocumentOut)
def resolve_conflict(
    project_id: str, conflict_id: str,
    body: schemas.ConflictResolveRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")

    conflict = db.query(models.DocConflict).filter(
        models.DocConflict.id == conflict_id,
        models.DocConflict.resolved_at.is_(None),
    ).first()
    if not conflict:
        raise HTTPException(404, "Conflict not found or already resolved")

    doc = _get_doc_or_404(project_id, conflict.document_id, db)

    if body.resolution == "accepted_a":
        new_content = conflict.content_a
    elif body.resolution == "accepted_b":
        new_content = conflict.content_b
    elif body.resolution == "manual":
        if not body.manual_content:
            raise HTTPException(400, "manual_content is required for manual resolution")
        new_content = body.manual_content
    else:
        raise HTTPException(400, "resolution must be accepted_a, accepted_b or manual")

    doc.body         = new_content
    doc.current_hash = _sha256(new_content)
    doc.last_editor  = user.id
    doc.updated_at   = now_utc()

    conflict.resolved_at = now_utc()
    conflict.resolved_by = user.id
    conflict.resolution  = body.resolution

    db.commit()
    db.refresh(doc)
    return _enrich(doc)
