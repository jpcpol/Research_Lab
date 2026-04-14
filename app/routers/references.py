from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_project_member
from app.models import now_utc

router = APIRouter(prefix="/projects/{project_id}/references", tags=["references"])


@router.get("", response_model=list[schemas.ReferenceOut])
def list_references(
    project_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    return (
        db.query(models.Reference)
        .filter(models.Reference.project_id == project_id)
        .order_by(models.Reference.year.desc(), models.Reference.title)
        .all()
    )


@router.post("", response_model=schemas.ReferenceOut, status_code=201)
def create_reference(
    project_id: str,
    body: schemas.ReferenceCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    ref = models.Reference(project_id=project_id, author_id=user.id, **body.model_dump())
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


@router.patch("/{ref_id}", response_model=schemas.ReferenceOut)
def update_reference(
    project_id: str,
    ref_id: str,
    body: schemas.ReferenceUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    ref = db.query(models.Reference).filter(
        models.Reference.id == ref_id,
        models.Reference.project_id == project_id,
    ).first()
    if not ref:
        raise HTTPException(404, "Reference not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ref, k, v)
    ref.updated_at = now_utc()
    db.commit()
    db.refresh(ref)
    return ref


@router.delete("/{ref_id}", status_code=204)
def delete_reference(
    project_id: str,
    ref_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    ref = db.query(models.Reference).filter(
        models.Reference.id == ref_id,
        models.Reference.project_id == project_id,
    ).first()
    if not ref:
        raise HTTPException(404, "Reference not found")
    db.delete(ref)
    db.commit()
