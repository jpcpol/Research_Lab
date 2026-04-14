from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_project_member
from app.models import now_utc

router = APIRouter(prefix="/projects/{project_id}/hypotheses", tags=["hypotheses"])

VALID_STATUSES = {"pending", "in_progress", "validated", "rejected", "on_hold"}


@router.post("", response_model=schemas.HypothesisOut, status_code=201)
def create_hypothesis(
    project_id: str,
    body: schemas.HypothesisCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    h = models.Hypothesis(project_id=project_id, created_by=user.id, **body.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@router.get("", response_model=list[schemas.HypothesisOut])
def list_hypotheses(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    return (
        db.query(models.Hypothesis)
        .filter(models.Hypothesis.project_id == project_id)
        .order_by(models.Hypothesis.priority, models.Hypothesis.created_at)
        .all()
    )


@router.patch("/{hypothesis_id}", response_model=schemas.HypothesisOut)
def update_hypothesis(
    project_id: str,
    hypothesis_id: str,
    body: schemas.HypothesisUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    h = db.query(models.Hypothesis).filter(
        models.Hypothesis.id == hypothesis_id,
        models.Hypothesis.project_id == project_id,
    ).first()
    if not h:
        raise HTTPException(404, "Hypothesis not found")
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Valid: {VALID_STATUSES}")
    updates = body.model_dump(exclude_none=True)
    for k, v in updates.items():
        setattr(h, k, v)
    h.updated_by = user.id
    h.updated_at = now_utc()
    db.commit()
    db.refresh(h)
    return h


@router.delete("/{hypothesis_id}", status_code=204)
def delete_hypothesis(
    project_id: str,
    hypothesis_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    h = db.query(models.Hypothesis).filter(
        models.Hypothesis.id == hypothesis_id,
        models.Hypothesis.project_id == project_id,
    ).first()
    if not h:
        raise HTTPException(404, "Hypothesis not found")
    db.delete(h)
    db.commit()
