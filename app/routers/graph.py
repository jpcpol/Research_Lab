"""
Research Lab — Knowledge Graph router
DT-RL-008: relaciones semánticas + auto-detección de [[wikilinks]]
"""
import re
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.auth import get_current_user
from app import models, schemas

router = APIRouter(tags=["graph"])

WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')


def _require_member(project_id: str, user, db: Session) -> models.ProjectMember:
    m = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=user.id
    ).first()
    if not m:
        raise HTTPException(403, "Not a member of this project")
    return m


# ── GET /projects/{project_id}/graph ────────────────────────────────────────

@router.get("/projects/{project_id}/graph", response_model=schemas.GraphOut)
def get_graph(
    project_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_member(project_id, current_user, db)

    nodes: list[schemas.GraphNode] = []
    title_map: dict[str, tuple[str, str]] = {}   # lower(title) → (id, type)

    # ── Collect all nodes ───────────────────────────────────────────────────

    for h in db.query(models.Hypothesis).filter_by(project_id=project_id).all():
        desc = h.description[:120] if h.description else None
        nodes.append(schemas.GraphNode(id=h.id, type="hypothesis", label=h.title, description=desc))
        title_map[h.title.lower()] = (h.id, "hypothesis")

    for n in db.query(models.Note).filter_by(project_id=project_id).all():
        desc = (n.body or "")[:120] or None
        nodes.append(schemas.GraphNode(id=n.id, type="note", label=n.title, description=desc))
        title_map[n.title.lower()] = (n.id, "note")

    for m in db.query(models.Milestone).filter_by(project_id=project_id).all():
        nodes.append(schemas.GraphNode(id=m.id, type="milestone", label=m.title, description=m.description))
        title_map[m.title.lower()] = (m.id, "milestone")

    for r in db.query(models.Reference).filter_by(project_id=project_id).all():
        desc = f"{r.authors} ({r.year})" if r.authors else None
        nodes.append(schemas.GraphNode(id=r.id, type="reference", label=r.title, description=desc))
        title_map[r.title.lower()] = (r.id, "reference")

    node_ids = {n.id for n in nodes}

    # ── Explicit relations ──────────────────────────────────────────────────

    edges: list[schemas.GraphEdge] = []
    seen: set[tuple[str, str]] = set()

    for rel in db.query(models.Relation).filter_by(project_id=project_id).all():
        if rel.from_id in node_ids and rel.to_id in node_ids:
            edges.append(schemas.GraphEdge(
                id=rel.id,
                from_id=rel.from_id,
                to_id=rel.to_id,
                label=rel.label,
                auto=rel.auto,
            ))
            seen.add((rel.from_id, rel.to_id))

    # ── Auto-detect [[wikilinks]] in notes ──────────────────────────────────

    for n in db.query(models.Note).filter_by(project_id=project_id).all():
        for link in WIKILINK_RE.findall(n.body or ""):
            result = title_map.get(link.lower())
            if result and result[0] != n.id and (n.id, result[0]) not in seen:
                edges.append(schemas.GraphEdge(
                    id=f"wl-{n.id[:8]}-{result[0][:8]}",
                    from_id=n.id,
                    to_id=result[0],
                    label="menciona",
                    auto=True,
                ))
                seen.add((n.id, result[0]))

    # ── Auto-detect [[wikilinks]] in hypotheses ─────────────────────────────

    for h in db.query(models.Hypothesis).filter_by(project_id=project_id).all():
        text = (h.title or "") + " " + (h.description or "")
        for link in WIKILINK_RE.findall(text):
            result = title_map.get(link.lower())
            if result and result[0] != h.id and (h.id, result[0]) not in seen:
                edges.append(schemas.GraphEdge(
                    id=f"wl-{h.id[:8]}-{result[0][:8]}",
                    from_id=h.id,
                    to_id=result[0],
                    label="menciona",
                    auto=True,
                ))
                seen.add((h.id, result[0]))

    return schemas.GraphOut(nodes=nodes, edges=edges)


# ── POST /projects/{project_id}/relations ───────────────────────────────────

@router.post("/projects/{project_id}/relations", response_model=schemas.RelationOut)
def create_relation(
    project_id: str,
    body: schemas.RelationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    _require_member(project_id, current_user, db)

    if body.from_id == body.to_id:
        raise HTTPException(422, "Source and target nodes cannot be the same")

    # Idempotent: return existing if identical relation already exists
    existing = db.query(models.Relation).filter_by(
        project_id=project_id,
        from_id=body.from_id,
        to_id=body.to_id,
        label=body.label,
    ).first()
    if existing:
        return existing

    rel = models.Relation(
        project_id=project_id,
        from_id=body.from_id,
        from_type=body.from_type,
        to_id=body.to_id,
        to_type=body.to_type,
        label=body.label,
        auto=False,
        created_by=current_user.id,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


# ── DELETE /projects/{project_id}/relations/{relation_id} ───────────────────

@router.delete("/projects/{project_id}/relations/{relation_id}")
def delete_relation(
    project_id: str,
    relation_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    member = _require_member(project_id, current_user, db)
    rel = db.query(models.Relation).filter_by(
        id=relation_id, project_id=project_id
    ).first()
    if not rel:
        raise HTTPException(404, "Relation not found")
    if rel.created_by != current_user.id and member.role != "PI":
        raise HTTPException(403, "Only the creator or PI can delete this relation")
    db.delete(rel)
    db.commit()
    return {"ok": True}
