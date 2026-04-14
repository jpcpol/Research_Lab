from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app import models, schemas
from app.auth import get_current_user, require_project_member
from app.models import now_utc

router = APIRouter(prefix="/projects/{project_id}/notes", tags=["notes"])


@router.post("", response_model=schemas.NoteOut, status_code=201)
def create_note(
    project_id: str,
    body: schemas.NoteCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    note = models.Note(project_id=project_id, author_id=user.id, **body.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("", response_model=list[schemas.NoteOut])
def list_notes(
    project_id: str,
    folder: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    q = db.query(models.Note).filter(models.Note.project_id == project_id)
    if folder:
        q = q.filter(models.Note.folder == folder)
    return q.order_by(models.Note.updated_at.desc()).all()


@router.get("/{note_id}", response_model=schemas.NoteOut)
def get_note(
    project_id: str, note_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db)
    note = db.query(models.Note).filter(
        models.Note.id == note_id,
        models.Note.project_id == project_id,
    ).first()
    if not note:
        raise HTTPException(404, "Note not found")
    return note


@router.patch("/{note_id}", response_model=schemas.NoteOut)
def update_note(
    project_id: str, note_id: str,
    body: schemas.NoteUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    note = db.query(models.Note).filter(
        models.Note.id == note_id,
        models.Note.project_id == project_id,
    ).first()
    if not note:
        raise HTTPException(404, "Note not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(note, k, v)
    note.updated_at = now_utc()
    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}", status_code=204)
def delete_note(
    project_id: str, note_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="COLLABORATOR")
    note = db.query(models.Note).filter(
        models.Note.id == note_id,
        models.Note.project_id == project_id,
    ).first()
    if not note:
        raise HTTPException(404, "Note not found")
    db.delete(note)
    db.commit()
