"""mcp.py — MCP server with Streamable HTTP transport for claude.ai integration.

Each researcher connects claude.ai to:
  https://lab.aural-syncro.com.ar/mcp?token=<mcp_token>

No Anthropic API key needed — the researcher's own Claude Pro/Max subscription
handles inference. This server provides the data tools.

Protocol: MCP Streamable HTTP (JSON-RPC 2.0, single POST endpoint).
"""

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.models import now_utc

router = APIRouter(tags=["mcp"])

PROTOCOL_VERSION = "2024-11-05"


# ── Auth ───────────────────────────────────────────────────────────────────────

def _get_user_by_mcp_token(token: str, db: Session) -> models.User:
    user = db.query(models.User).filter(
        models.User.mcp_token == token,
        models.User.is_active == True,
    ).first()
    if not user:
        raise HTTPException(401, "Invalid MCP token")
    return user


# ── Membership guard ───────────────────────────────────────────────────────────

def _require_member(project_id: str, user: models.User, db: Session) -> models.ProjectMember:
    member = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=user.id
    ).first()
    if not member:
        raise ValueError(f"You are not a member of project {project_id}")
    return member


# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_projects",
        "description": "List all research projects the researcher belongs to, with their role in each.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_project_overview",
        "description": (
            "Get a summary of a research project: description, status, hypothesis counts "
            "by state, recent journal activity, team size, and notes/references counts."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "list_hypotheses",
        "description": "List hypotheses of a research project, optionally filtered by status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["pending", "in_progress", "validated", "rejected", "on_hold"],
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "get_hypothesis",
        "description": "Get full detail of a hypothesis: description, status, priority, creation date, and its knowledge graph relations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id":    {"type": "string", "description": "Project ID"},
                "hypothesis_id": {"type": "string", "description": "Hypothesis ID"},
            },
            "required": ["project_id", "hypothesis_id"],
        },
    },
    {
        "name": "create_hypothesis",
        "description": "Create a new hypothesis in a research project. Requires COLLABORATOR or PI role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id":  {"type": "string", "description": "Project ID"},
                "title":       {"type": "string", "description": "Hypothesis title"},
                "description": {"type": "string", "description": "Detailed description"},
                "priority": {
                    "type": "integer",
                    "description": "Priority: 1 (critical) to 5 (low)",
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": ["project_id", "title"],
        },
    },
    {
        "name": "list_journal",
        "description": "Get recent entries from the immutable project journal (bitácora). Entries cannot be modified after creation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "limit": {
                    "type": "integer",
                    "description": "Max entries (default 10, max 50)",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["project_id"],
        },
    },
    {
        "name": "add_journal_entry",
        "description": (
            "Add an immutable entry to the project journal (bitácora). "
            "Once created it cannot be modified or deleted. Requires COLLABORATOR or PI role."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "title":      {"type": "string", "description": "Entry title"},
                "body":       {"type": "string", "description": "Entry content (Markdown supported)"},
                "entry_type": {
                    "type": "string",
                    "description": "Type of entry",
                    "enum": ["progress", "modification", "note", "milestone", "decision"],
                },
            },
            "required": ["project_id", "title", "body"],
        },
    },
    {
        "name": "search_notes",
        "description": "Search notes in a project by keyword (searches title and body).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
                "query":      {"type": "string", "description": "Search query"},
            },
            "required": ["project_id", "query"],
        },
    },
    {
        "name": "list_references",
        "description": "Get the bibliography of a research project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    },
]


# ── Tool handlers ──────────────────────────────────────────────────────────────

def _handle_list_projects(args: dict, user: models.User, db: Session) -> str:
    memberships = db.query(models.ProjectMember).filter_by(user_id=user.id).all()
    if not memberships:
        return "You are not a member of any project yet."
    lines = [f"# Research Projects for {user.name}\n"]
    for m in memberships:
        p = m.project
        lines.append(f"## {p.name}")
        lines.append(f"- **ID**: `{p.id}`")
        lines.append(f"- **Status**: {p.status} | **Role**: {m.role}")
        if p.description:
            lines.append(f"- {p.description[:150]}")
        lines.append("")
    return "\n".join(lines)


def _handle_get_project_overview(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    _require_member(project_id, user, db)
    p = db.query(models.Project).filter_by(id=project_id).first()
    if not p:
        raise ValueError("Project not found")

    hyp_total      = db.query(models.Hypothesis).filter_by(project_id=project_id).count()
    hyp_validated  = db.query(models.Hypothesis).filter_by(project_id=project_id, status="validated").count()
    hyp_progress   = db.query(models.Hypothesis).filter_by(project_id=project_id, status="in_progress").count()
    hyp_pending    = db.query(models.Hypothesis).filter_by(project_id=project_id, status="pending").count()
    journal_count  = db.query(models.JournalEntry).filter_by(project_id=project_id).count()
    notes_count    = db.query(models.Note).filter_by(project_id=project_id).count()
    refs_count     = db.query(models.Reference).filter_by(project_id=project_id).count()
    members        = db.query(models.ProjectMember).filter_by(project_id=project_id).all()

    lines = [
        f"# {p.name}",
        f"**Status**: {p.status}",
        f"**Description**: {p.description or 'No description'}",
        f"\n## Hypotheses ({hyp_total} total)",
        f"- ✅ Validated: {hyp_validated}",
        f"- 🔬 In progress: {hyp_progress}",
        f"- ⏳ Pending: {hyp_pending}",
        f"- Other: {hyp_total - hyp_validated - hyp_progress - hyp_pending}",
        f"\n## Activity",
        f"- Journal entries: {journal_count}",
        f"- Notes: {notes_count}",
        f"- References: {refs_count}",
        f"\n## Team ({len(members)} members)",
    ]
    for m in members:
        lines.append(f"- {m.user.name} ({m.role})")
    return "\n".join(lines)


def _handle_list_hypotheses(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    _require_member(project_id, user, db)

    q = db.query(models.Hypothesis).filter_by(project_id=project_id)
    if args.get("status"):
        q = q.filter_by(status=args["status"])
    hypotheses = q.order_by(models.Hypothesis.priority, models.Hypothesis.created_at).all()

    if not hypotheses:
        return "No hypotheses found."

    status_emoji = {
        "pending": "⏳", "in_progress": "🔬", "validated": "✅",
        "rejected": "❌", "on_hold": "⏸️",
    }
    lines = [f"# Hypotheses ({len(hypotheses)})\n"]
    for h in hypotheses:
        emoji = status_emoji.get(h.status, "•")
        lines.append(f"{emoji} **{h.title}** (`{h.id}`)")
        lines.append(f"   Status: {h.status} | Priority: {h.priority}/5")
        if h.description:
            lines.append(f"   {h.description[:150]}")
        lines.append("")
    return "\n".join(lines)


def _handle_get_hypothesis(args: dict, user: models.User, db: Session) -> str:
    project_id    = args["project_id"]
    hypothesis_id = args["hypothesis_id"]
    _require_member(project_id, user, db)

    h = db.query(models.Hypothesis).filter_by(id=hypothesis_id, project_id=project_id).first()
    if not h:
        raise ValueError("Hypothesis not found")

    relations = db.query(models.Relation).filter(
        models.Relation.project_id == project_id,
        or_(models.Relation.from_id == hypothesis_id, models.Relation.to_id == hypothesis_id),
    ).all()

    lines = [
        f"# {h.title}",
        f"**ID**: `{h.id}`",
        f"**Status**: {h.status} | **Priority**: {h.priority}/5",
        f"**Created**: {h.created_at.strftime('%Y-%m-%d') if h.created_at else 'unknown'}",
        f"**Updated**: {h.updated_at.strftime('%Y-%m-%d') if h.updated_at else 'unknown'}",
        f"\n## Description\n{h.description or 'No description'}",
    ]
    if relations:
        lines.append(f"\n## Knowledge Graph Relations ({len(relations)})")
        for r in relations:
            if r.from_id == hypothesis_id:
                lines.append(f"- → **{r.label}** ({r.to_type} `{r.to_id}`)")
            else:
                lines.append(f"- ← **{r.label}** ({r.from_type} `{r.from_id}`)")
    return "\n".join(lines)


def _handle_create_hypothesis(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    member = _require_member(project_id, user, db)
    if member.role not in ("PI", "COLLABORATOR"):
        raise ValueError("COLLABORATOR or PI role required to create hypotheses")

    h = models.Hypothesis(
        id=str(uuid.uuid4()),
        project_id=project_id,
        created_by=user.id,
        title=args["title"],
        description=args.get("description", ""),
        priority=args.get("priority", 3),
        status="pending",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    db.add(h)
    db.commit()
    return f"✅ Hypothesis created\n**{h.title}** (`{h.id}`)\nStatus: pending | Priority: {h.priority}/5"


def _handle_list_journal(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    _require_member(project_id, user, db)
    limit = min(int(args.get("limit", 10)), 50)

    entries = (
        db.query(models.JournalEntry)
        .filter_by(project_id=project_id)
        .order_by(models.JournalEntry.created_at.desc())
        .limit(limit)
        .all()
    )
    if not entries:
        return "No journal entries found."

    lines = [f"# Journal — last {len(entries)} entries\n"]
    for e in entries:
        date = e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "unknown"
        author = e.author.name if e.author else "unknown"
        lines.append(f"## [{e.entry_type.upper()}] {e.title}")
        lines.append(f"*{date} · {author}*\n")
        lines.append(e.body[:400] + ("…" if len(e.body) > 400 else ""))
        lines.append("")
    return "\n".join(lines)


def _handle_add_journal_entry(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    member = _require_member(project_id, user, db)
    if member.role not in ("PI", "COLLABORATOR"):
        raise ValueError("COLLABORATOR or PI role required to add journal entries")

    entry = models.JournalEntry(
        id=str(uuid.uuid4()),
        project_id=project_id,
        author_id=user.id,
        title=args["title"],
        body=args["body"],
        entry_type=args.get("entry_type", "note"),
        created_at=now_utc(),
    )
    db.add(entry)
    db.commit()
    return (
        f"✅ Journal entry recorded\n**{entry.title}** · type: {entry.entry_type}\n"
        "This entry is immutable and cannot be modified."
    )


def _handle_search_notes(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    _require_member(project_id, user, db)
    query = args["query"].lower()

    notes = db.query(models.Note).filter_by(project_id=project_id).all()
    matches = [n for n in notes if query in n.title.lower() or query in (n.body or "").lower()]

    if not matches:
        return f"No notes found matching '{args['query']}'."

    lines = [f"# Notes matching '{args['query']}' ({len(matches)} results)\n"]
    for n in matches:
        lines.append(f"## {n.title} (`{n.id}`)")
        lines.append(f"*Folder: {n.folder} | Tags: {n.tags or 'none'}*")
        body_lower = (n.body or "").lower()
        idx = body_lower.find(query)
        if idx >= 0:
            start = max(0, idx - 60)
            snippet = n.body[start : idx + 120]
            lines.append(f"…{snippet}…")
        lines.append("")
    return "\n".join(lines)


def _handle_list_references(args: dict, user: models.User, db: Session) -> str:
    project_id = args["project_id"]
    _require_member(project_id, user, db)

    refs = (
        db.query(models.Reference)
        .filter_by(project_id=project_id)
        .order_by(models.Reference.year.desc())
        .all()
    )
    if not refs:
        return "No references found."

    lines = [f"# Bibliography ({len(refs)} references)\n"]
    for r in refs:
        year = f" ({r.year})" if r.year else ""
        lines.append(f"- **{r.title}**{year}")
        lines.append(f"  {r.authors or 'Unknown authors'} | Type: {r.ref_type}")
        if r.doi:
            lines.append(f"  DOI: {r.doi}")
        if r.url:
            lines.append(f"  URL: {r.url}")
    return "\n".join(lines)


TOOL_HANDLERS = {
    "list_projects":        _handle_list_projects,
    "get_project_overview": _handle_get_project_overview,
    "list_hypotheses":      _handle_list_hypotheses,
    "get_hypothesis":       _handle_get_hypothesis,
    "create_hypothesis":    _handle_create_hypothesis,
    "list_journal":         _handle_list_journal,
    "add_journal_entry":    _handle_add_journal_entry,
    "search_notes":         _handle_search_notes,
    "list_references":      _handle_list_references,
}


# ── JSON-RPC helpers ───────────────────────────────────────────────────────────

def _ok(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _err(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _dispatch(body: dict, user: models.User, db: Session) -> Optional[dict]:
    method = body.get("method", "")
    id_    = body.get("id")

    # Notifications — no response
    if method == "notifications/initialized":
        return None

    if method == "initialize":
        return _ok(id_, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "Research Lab", "version": "1.0.0"},
        })

    if method == "tools/list":
        return _ok(id_, {"tools": TOOLS})

    if method == "tools/call":
        params  = body.get("params", {})
        name    = params.get("name", "")
        args    = params.get("arguments", {})
        handler = TOOL_HANDLERS.get(name)
        if not handler:
            return _ok(id_, {
                "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                "isError": True,
            })
        try:
            text = handler(args, user, db)
            return _ok(id_, {"content": [{"type": "text", "text": text}], "isError": False})
        except ValueError as e:
            return _ok(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        except Exception as e:
            return _ok(id_, {"content": [{"type": "text", "text": f"Internal error: {e}"}], "isError": True})

    return _err(id_, -32601, f"Method not found: {method}")


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/mcp")
async def mcp_endpoint(
    request: Request,
    token: str = Query(..., description="Personal MCP token from Research Lab settings"),
    db: Session = Depends(get_db),
):
    user = _get_user_by_mcp_token(token, db)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_err(None, -32700, "Parse error"), status_code=400)

    if isinstance(body, list):
        responses = [r for item in body if (r := _dispatch(item, user, db)) is not None]
        return JSONResponse(responses)

    result = _dispatch(body, user, db)
    if result is None:
        return Response(status_code=202)
    return JSONResponse(result)
