from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_project_member
from app.models import now_utc

router = APIRouter(prefix="/projects/{project_id}/milestones", tags=["milestones"])


def _get_milestone(project_id: str, milestone_id: str, db: Session) -> models.Milestone:
    m = db.query(models.Milestone).filter(
        models.Milestone.id == milestone_id,
        models.Milestone.project_id == project_id,
    ).first()
    if not m:
        raise HTTPException(404, "Milestone not found")
    return m


# ── Milestones ────────────────────────────────────────────────────────────────

@router.post("", response_model=schemas.MilestoneOut, status_code=201)
def create_milestone(
    project_id: str,
    body: schemas.MilestoneCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    m = models.Milestone(project_id=project_id, created_by=user.id, **body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


@router.get("", response_model=list[schemas.MilestoneOut])
def list_milestones(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    return (
        db.query(models.Milestone)
        .filter(models.Milestone.project_id == project_id)
        .order_by(models.Milestone.created_at)
        .all()
    )


@router.patch("/{milestone_id}", response_model=schemas.MilestoneOut)
def update_milestone(
    project_id: str, milestone_id: str,
    body: schemas.MilestoneUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    m = _get_milestone(project_id, milestone_id, db)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.post("/{milestone_id}/complete", response_model=schemas.MilestoneOut)
def toggle_complete(
    project_id: str, milestone_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    m = _get_milestone(project_id, milestone_id, db)
    m.completed_at = None if m.completed_at else datetime.now(timezone.utc)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{milestone_id}", status_code=204)
def delete_milestone(
    project_id: str, milestone_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    m = _get_milestone(project_id, milestone_id, db)
    db.delete(m)
    db.commit()


# ── Requirements ─────────────────────────────────────────────────────────────

@router.post("/{milestone_id}/requirements", response_model=schemas.RequirementOut, status_code=201)
def create_requirement(
    project_id: str, milestone_id: str,
    body: schemas.RequirementCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    _get_milestone(project_id, milestone_id, db)
    r = models.Requirement(
        milestone_id=milestone_id,
        project_id=project_id,
        **body.model_dump(),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


@router.patch("/{milestone_id}/requirements/{req_id}", response_model=schemas.RequirementOut)
def update_requirement(
    project_id: str, milestone_id: str, req_id: str,
    body: schemas.RequirementUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    r = db.query(models.Requirement).filter(
        models.Requirement.id == req_id,
        models.Requirement.milestone_id == milestone_id,
    ).first()
    if not r:
        raise HTTPException(404, "Requirement not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    r.updated_at = now_utc()
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{milestone_id}/requirements/{req_id}", status_code=204)
def delete_requirement(
    project_id: str, milestone_id: str, req_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    r = db.query(models.Requirement).filter(
        models.Requirement.id == req_id,
        models.Requirement.milestone_id == milestone_id,
    ).first()
    if not r:
        raise HTTPException(404, "Requirement not found")
    db.delete(r)
    db.commit()
