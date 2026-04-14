from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, field_validator


# ─── Auth ─────────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

class UserOut(BaseModel):
    id: str
    email: str
    name: str
    avatar_url:  Optional[str] = None
    created_at:  datetime
    # Perfil profesional
    title:       Optional[str] = None
    institution: Optional[str] = None
    department:  Optional[str] = None
    orcid:       Optional[str] = None
    bio:         Optional[str] = None
    website:     Optional[str] = None
    model_config = {"from_attributes": True}

TokenResponse.model_rebuild()


# ─── Projects ─────────────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class MemberOut(BaseModel):
    user_id: str
    role: str
    user: UserOut
    joined_at: datetime
    model_config = {"from_attributes": True}

class ProjectOut(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    status: str
    created_at: datetime
    members: List[MemberOut] = []
    model_config = {"from_attributes": True}

class InviteMember(BaseModel):
    email: EmailStr
    role: str = "COLLABORATOR"


# ─── Profile ───────────────────────────────────────────────────────────────────

class UpdateProfileRequest(BaseModel):
    name: str

class UpdateProfessionalRequest(BaseModel):
    title:       Optional[str] = None
    institution: Optional[str] = None
    department:  Optional[str] = None
    orcid:       Optional[str] = None
    bio:         Optional[str] = None
    website:     Optional[str] = None

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class RequestEmailChangeRequest(BaseModel):
    new_email: EmailStr

class ConfirmEmailChangeRequest(BaseModel):
    pin: str


# ─── Invitations ───────────────────────────────────────────────────────────────

class InviteCheckResponse(BaseModel):
    invited: bool
    project_name: Optional[str] = None
    token: Optional[str] = None   # returned so frontend can use it directly

class InviteInfoResponse(BaseModel):
    email: str
    project_name: Optional[str] = None

class SendPinRequest(BaseModel):
    email: EmailStr

class AcceptInviteRequest(BaseModel):
    token: str
    name: str
    password: str
    pin: str


# ─── Journal ──────────────────────────────────────────────────────────────────

class JournalEntryCreate(BaseModel):
    title: Optional[str] = None
    body: str
    entry_type: str = "note"
    tags: Optional[str] = ""

class JournalEntryOut(BaseModel):
    id: str
    project_id: str
    author_id: str
    entry_type: str
    title: Optional[str]
    body: str
    tags: str
    created_at: datetime
    author: UserOut
    model_config = {"from_attributes": True}


# ─── Hypotheses ───────────────────────────────────────────────────────────────

class HypothesisCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: int = 3

class HypothesisUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None

class HypothesisOut(BaseModel):
    id: str
    project_id: str
    title: str
    description: Optional[str]
    status: str
    priority: int
    created_at: datetime
    updated_at: datetime
    creator: UserOut
    model_config = {"from_attributes": True}


# ─── Milestones ───────────────────────────────────────────────────────────────

class RequirementCreate(BaseModel):
    title: str
    notes: Optional[str] = None
    assigned_to: Optional[str] = None

class RequirementUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None

class RequirementOut(BaseModel):
    id: str
    title: str
    notes: Optional[str]
    status: str
    assigned_to: Optional[str]
    assignee: Optional[UserOut]
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}

class MilestoneCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[str] = None

class MilestoneUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    completed_at: Optional[datetime] = None

class MilestoneOut(BaseModel):
    id: str
    project_id: str
    title: str
    description: Optional[str]
    due_date: Optional[str]
    completed_at: Optional[datetime]
    created_at: datetime
    requirements: List[RequirementOut] = []
    creator: UserOut
    model_config = {"from_attributes": True}


# ─── References / Bibliography ────────────────────────────────────────────────

class ReferenceCreate(BaseModel):
    title: str
    authors: Optional[str] = ""
    year: Optional[int] = None
    ref_type: str = "paper"
    url: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    notes: Optional[str] = None
    tags: str = ""

class ReferenceUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    ref_type: Optional[str] = None
    url: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None

class ReferenceOut(BaseModel):
    id: str
    project_id: str
    title: str
    authors: str
    year: Optional[int]
    ref_type: str
    url: Optional[str]
    doi: Optional[str]
    abstract: Optional[str]
    notes: Optional[str]
    tags: str
    created_at: datetime
    updated_at: datetime
    author: UserOut
    model_config = {"from_attributes": True}


# ─── Notes ────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    title: str
    body: str = ""
    folder: str = "/"
    tags: str = ""

class NoteUpdate(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    folder: Optional[str] = None
    tags: Optional[str] = None

class NoteOut(BaseModel):
    id: str
    project_id: str
    author_id: str
    title: str
    body: str
    folder: str
    tags: str
    created_at: datetime
    updated_at: datetime
    author: UserOut
    model_config = {"from_attributes": True}


# ─── Documents ────────────────────────────────────────────────────────────────

class DocumentCreate(BaseModel):
    title: str
    body: str = ""

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    body:  Optional[str] = None

class DocumentSyncRequest(BaseModel):
    content:      str
    version_hash: Optional[str] = None   # SHA-256 del cuerpo anterior; None = primera sync

class DocumentOut(BaseModel):
    id:           str
    project_id:   str
    title:        str
    body:         str
    current_hash: Optional[str]
    locked_by:    Optional[str] = None   # nombre del usuario que tiene el lock (calculado)
    last_editor:  Optional[str] = None   # id del último editor
    created_at:   datetime
    updated_at:   datetime
    creator:      UserOut
    model_config = {"from_attributes": True}

class DocConflictOut(BaseModel):
    id:          str
    document_id: str
    content_a:   str
    content_b:   str
    created_at:  datetime
    submitter:   UserOut
    model_config = {"from_attributes": True}

class ConflictResolveRequest(BaseModel):
    resolution: str               # "accepted_a" | "accepted_b" | "manual"
    manual_content: Optional[str] = None   # solo si resolution == "manual"


# ─── Knowledge Graph ──────────────────────────────────────────────────────────

RELATION_LABELS = [
    "relacionado", "soporta", "contradice", "usa_método",
    "construye_sobre", "replica", "refuta", "define", "ejemplifica",
]

class RelationCreate(BaseModel):
    from_id:   str
    from_type: str
    to_id:     str
    to_type:   str
    label:     str = "relacionado"

class RelationOut(BaseModel):
    id:         str
    project_id: str
    from_id:    str
    from_type:  str
    to_id:      str
    to_type:    str
    label:      str
    auto:       bool
    created_at: datetime
    creator:    Optional[UserOut]
    model_config = {"from_attributes": True}

class GraphNode(BaseModel):
    id:          str
    type:        str
    label:       str
    description: Optional[str] = None

class GraphEdge(BaseModel):
    id:      str
    from_id: str
    to_id:   str
    label:   str
    auto:    bool = False

class GraphOut(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
