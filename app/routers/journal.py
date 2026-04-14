from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_project_member

router = APIRouter(prefix="/projects/{project_id}/journal", tags=["journal"])


@router.post("", response_model=schemas.JournalEntryOut, status_code=201)
def create_entry(
    project_id: str,
    body: schemas.JournalEntryCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    entry = models.JournalEntry(
        project_id=project_id,
        author_id=user.id,
        **body.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("", response_model=list[schemas.JournalEntryOut])
def list_entries(
    project_id: str,
    entry_type: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    q = db.query(models.JournalEntry).filter(
        models.JournalEntry.project_id == project_id
    )
    if entry_type:
        q = q.filter(models.JournalEntry.entry_type == entry_type)
    return q.order_by(models.JournalEntry.created_at.desc()).offset(offset).limit(limit).all()
