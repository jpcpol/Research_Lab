from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app import models, schemas, email_utils
from app.auth import get_current_user, require_project_member

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_project_or_404(project_id: str, db: Session) -> models.Project:
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@router.post("", response_model=schemas.ProjectOut, status_code=201)
def create_project(
    body: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    slug = body.slug.lower().replace(" ", "-")
    if db.query(models.Project).filter(models.Project.slug == slug).first():
        raise HTTPException(400, "Slug already in use")
    project = models.Project(name=body.name, slug=slug, description=body.description)
    db.add(project)
    db.flush()
    db.add(models.ProjectMember(project_id=project.id, user_id=user.id, role="PI"))
    db.commit()
    db.refresh(project)
    return project


@router.get("", response_model=list[schemas.ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    memberships = db.query(models.ProjectMember).filter(
        models.ProjectMember.user_id == user.id
    ).all()
    project_ids = [m.project_id for m in memberships]
    return db.query(models.Project).filter(models.Project.id.in_(project_ids)).all()


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    return _get_project_or_404(project_id, db)


@router.patch("/{project_id}", response_model=schemas.ProjectOut)
def update_project(
    project_id: str,
    body: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    project = _get_project_or_404(project_id, db)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/members", status_code=201)
def invite_member(
    project_id: str,
    body: schemas.InviteMember,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """
    Send an invitation to collaborate.
    - If the email already belongs to a registered user → add them directly.
    - Otherwise → create an Invitation record and send an invitation email.
    """
    require_project_member(project_id, user, db, min_role="PI")
    project = _get_project_or_404(project_id, db)
    email = body.email.lower().strip()

    # Case 1: user already registered
    target = db.query(models.User).filter(models.User.email == email).first()
    if target:
        existing = db.query(models.ProjectMember).filter(
            models.ProjectMember.project_id == project_id,
            models.ProjectMember.user_id == target.id,
        ).first()
        if existing:
            raise HTTPException(400, "User is already a project member")
        db.add(models.ProjectMember(project_id=project_id, user_id=target.id, role=body.role))
        db.commit()
        return {"status": "added", "message": f"{target.name} agregado al proyecto"}

    # Case 2: pending invite already exists → resend
    existing_inv = (
        db.query(models.Invitation)
        .filter(
            models.Invitation.email == email,
            models.Invitation.project_id == project_id,
            models.Invitation.accepted_at.is_(None),
        )
        .first()
    )
    if existing_inv:
        try:
            email_utils.send_invitation(email, project.name, user.name, existing_inv.token)
        except Exception:
            pass
        return {"status": "resent", "message": "Invitación reenviada"}

    # Case 3: new invitation
    inv = models.Invitation(
        email=email,
        project_id=project_id,
        role=body.role,
        invited_by=user.id,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)

    try:
        email_utils.send_invitation(email, project.name, user.name, inv.token)
    except Exception:
        pass  # invitation created even if email fails; logged inside email_utils

    return {"status": "invited", "message": f"Invitación enviada a {email}"}


@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(
    project_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    member = db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id,
        models.ProjectMember.user_id == user_id,
    ).first()
    if not member:
        raise HTTPException(404, "Member not found")
    if member.role == "PI" and member.user_id == user.id:
        raise HTTPException(400, "PI cannot remove themselves")
    db.delete(member)
    db.commit()


# ── Búsqueda global ────────────────────────────────────────────────────────────

def _snippet(text: Optional[str], q: str, length: int = 130) -> str:
    """Extrae un fragmento de texto alrededor del primer match de q."""
    if not text:
        return ""
    idx = text.lower().find(q.lower())
    if idx == -1:
        return text[:length] + ("…" if len(text) > length else "")
    start = max(0, idx - 45)
    end   = min(len(text), start + length)
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


SEARCH_LIMIT = 6   # máx resultados por tipo

@router.get("/{project_id}/search")
def search_project(
    project_id: str,
    q:    str           = Query(..., min_length=2),
    type: Optional[str] = Query(None),   # all|journal|hypothesis|note|milestone|reference
    db:   Session       = Depends(get_db),
    user: models.User   = Depends(get_current_user),
):
    """Búsqueda full-text dentro de un proyecto. Filtra por tipo opcional."""
    require_project_member(project_id, user, db)
    pat     = f"%{q}%"
    results = []
    types   = {type} if type and type != "all" else {"journal","hypothesis","note","milestone","reference"}

    if "journal" in types:
        rows = (
            db.query(models.JournalEntry)
            .filter(
                models.JournalEntry.project_id == project_id,
                or_(
                    models.JournalEntry.title.ilike(pat),
                    models.JournalEntry.body.ilike(pat),
                ),
            )
            .order_by(models.JournalEntry.created_at.desc())
            .limit(SEARCH_LIMIT).all()
        )
        for r in rows:
            results.append({
                "type": "journal", "id": r.id,
                "title":   r.title or "(sin título)",
                "snippet": _snippet(r.body, q),
                "extra":   r.entry_type,
                "date":    r.created_at.isoformat(),
            })

    if "hypothesis" in types:
        rows = (
            db.query(models.Hypothesis)
            .filter(
                models.Hypothesis.project_id == project_id,
                or_(
                    models.Hypothesis.title.ilike(pat),
                    models.Hypothesis.description.ilike(pat),
                ),
            )
            .order_by(models.Hypothesis.created_at.desc())
            .limit(SEARCH_LIMIT).all()
        )
        for r in rows:
            results.append({
                "type": "hypothesis", "id": r.id,
                "title":   r.title,
                "snippet": _snippet(r.description, q),
                "extra":   r.status,
                "date":    r.created_at.isoformat(),
            })

    if "note" in types:
        rows = (
            db.query(models.Note)
            .filter(
                models.Note.project_id == project_id,
                or_(
                    models.Note.title.ilike(pat),
                    models.Note.body.ilike(pat),
                ),
            )
            .order_by(models.Note.updated_at.desc())
            .limit(SEARCH_LIMIT).all()
        )
        for r in rows:
            results.append({
                "type": "note", "id": r.id,
                "title":   r.title,
                "snippet": _snippet(r.body, q),
                "extra":   r.folder,
                "date":    r.updated_at.isoformat(),
            })

    if "milestone" in types:
        rows = (
            db.query(models.Milestone)
            .filter(
                models.Milestone.project_id == project_id,
                or_(
                    models.Milestone.title.ilike(pat),
                    models.Milestone.description.ilike(pat),
                ),
            )
            .order_by(models.Milestone.created_at.desc())
            .limit(SEARCH_LIMIT).all()
        )
        for r in rows:
            results.append({
                "type": "milestone", "id": r.id,
                "title":   r.title,
                "snippet": _snippet(r.description, q),
                "extra":   None,
                "date":    r.created_at.isoformat(),
            })

    if "reference" in types:
        rows = (
            db.query(models.Reference)
            .filter(
                models.Reference.project_id == project_id,
                or_(
                    models.Reference.title.ilike(pat),
                    models.Reference.authors.ilike(pat),
                    models.Reference.abstract.ilike(pat),
                ),
            )
            .order_by(models.Reference.created_at.desc())
            .limit(SEARCH_LIMIT).all()
        )
        for r in rows:
            results.append({
                "type": "reference", "id": r.id,
                "title":   r.title,
                "snippet": _snippet(r.abstract or r.authors, q),
                "extra":   r.ref_type,
                "date":    r.created_at.isoformat(),
            })

    return {"query": q, "total": len(results), "results": results}
