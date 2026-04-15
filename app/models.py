import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, ForeignKey,
    Integer, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


def now_utc():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


# ─── Users ───────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=new_uuid)
    email         = Column(String, unique=True, index=True, nullable=False)
    name          = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active     = Column(Boolean, default=True)
    created_at    = Column(DateTime(timezone=True), default=now_utc)

    avatar_url                  = Column(String, nullable=True)    # /static/avatars/{id}.ext

    # Email-change flow (added post-launch)
    pending_email               = Column(String, nullable=True)
    email_change_pin            = Column(String, nullable=True)   # hashed
    email_change_pin_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Login PIN — 2FA por email en cada sesión
    login_pin             = Column(String, nullable=True)
    login_pin_expires_at  = Column(DateTime(timezone=True), nullable=True)

    # Perfil profesional / institucional
    title        = Column(String, nullable=True)   # Dr., Mg., Lic., Ing., Prof., etc.
    institution  = Column(String, nullable=True)   # Universidad / Centro de investigación
    department   = Column(String, nullable=True)   # Departamento / Laboratorio / Área
    orcid        = Column(String, nullable=True)   # ORCID iD — 0000-0000-0000-000X
    bio          = Column(Text,   nullable=True)   # Breve bio profesional
    website      = Column(String, nullable=True)   # Sitio web / perfil académico

    memberships   = relationship("ProjectMember", back_populates="user")


# ─── Projects ────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id          = Column(String, primary_key=True, default=new_uuid)
    name        = Column(String, nullable=False)
    slug        = Column(String, unique=True, index=True, nullable=False)
    description = Column(Text)
    status      = Column(SAEnum("active", "paused", "archived", name="project_status"),
                         default="active")
    created_at  = Column(DateTime(timezone=True), default=now_utc)

    # GitHub App integration (credenciales por proyecto, cifradas en DB)
    github_token_enc             = Column(String, nullable=True)   # legacy — ya no se usa
    github_installation_id       = Column(String, nullable=True)   # GitHub App Installation ID
    github_owner                 = Column(String, nullable=True)
    github_repo                  = Column(String, nullable=True)
    github_app_id                = Column(String, nullable=True)   # GitHub App ID
    github_app_private_key_enc   = Column(Text,   nullable=True)   # PEM cifrado AES-256-GCM

    members         = relationship("ProjectMember", back_populates="project")
    journal         = relationship("JournalEntry", back_populates="project")
    hypotheses      = relationship("Hypothesis", back_populates="project")
    milestones      = relationship("Milestone", back_populates="project")
    notes           = relationship("Note", back_populates="project")
    references      = relationship("Reference", back_populates="project")
    relations       = relationship("Relation", back_populates="project", cascade="all, delete-orphan")
    documents       = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    feature_config  = relationship("ProjectFeatureConfig", uselist=False, cascade="all, delete-orphan")
    member_features = relationship("ProjectMemberFeature", cascade="all, delete-orphan")


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id         = Column(String, primary_key=True, default=new_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id    = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    role       = Column(SAEnum("PI", "COLLABORATOR", "OBSERVER", name="member_role"),
                        default="COLLABORATOR")
    joined_at  = Column(DateTime(timezone=True), default=now_utc)

    project = relationship("Project", back_populates="members")
    user    = relationship("User", back_populates="memberships")


# ─── Journal ─────────────────────────────────────────────────────────────────

class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id         = Column(String, primary_key=True, default=new_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    author_id  = Column(String, ForeignKey("users.id"))
    entry_type = Column(SAEnum(
        "progress", "modification", "note", "milestone", "decision",
        name="entry_type"), default="note")
    title      = Column(String)
    body       = Column(Text, nullable=False)
    tags       = Column(String, default="")   # comma-separated
    created_at = Column(DateTime(timezone=True), default=now_utc)
    # Immutable — no updated_at

    project = relationship("Project", back_populates="journal")
    author  = relationship("User")


# ─── Hypotheses ──────────────────────────────────────────────────────────────

class Hypothesis(Base):
    __tablename__ = "hypotheses"

    id          = Column(String, primary_key=True, default=new_uuid)
    project_id  = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    created_by  = Column(String, ForeignKey("users.id"))
    title       = Column(String, nullable=False)
    description = Column(Text)
    status      = Column(SAEnum(
        "pending", "in_progress", "validated", "rejected", "on_hold",
        name="hypothesis_status"), default="pending")
    priority    = Column(Integer, default=3)   # 1=critical … 5=low
    updated_by  = Column(String, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), default=now_utc)
    updated_at  = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project   = relationship("Project", back_populates="hypotheses")
    creator   = relationship("User", foreign_keys=[created_by])
    updater   = relationship("User", foreign_keys=[updated_by])


# ─── Milestones & Requirements ───────────────────────────────────────────────

class Milestone(Base):
    __tablename__ = "milestones"

    id          = Column(String, primary_key=True, default=new_uuid)
    project_id  = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    title       = Column(String, nullable=False)
    description = Column(Text)
    due_date    = Column(String, nullable=True)   # ISO date string
    completed_at= Column(DateTime(timezone=True), nullable=True)
    created_by  = Column(String, ForeignKey("users.id"))
    created_at  = Column(DateTime(timezone=True), default=now_utc)

    project      = relationship("Project", back_populates="milestones")
    creator      = relationship("User")
    requirements = relationship("Requirement", back_populates="milestone",
                                cascade="all, delete-orphan")


class Requirement(Base):
    __tablename__ = "requirements"

    id           = Column(String, primary_key=True, default=new_uuid)
    milestone_id = Column(String, ForeignKey("milestones.id", ondelete="CASCADE"))
    project_id   = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    title        = Column(String, nullable=False)
    notes        = Column(Text)
    status       = Column(SAEnum(
        "pending", "in_progress", "done", "blocked",
        name="req_status"), default="pending")
    assigned_to  = Column(String, ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=now_utc)
    updated_at   = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    milestone = relationship("Milestone", back_populates="requirements")
    assignee  = relationship("User")


# ─── References / Bibliography ───────────────────────────────────────────────

class Reference(Base):
    __tablename__ = "references"

    id         = Column(String, primary_key=True, default=new_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    author_id  = Column(String, ForeignKey("users.id"))
    title      = Column(String, nullable=False)
    authors    = Column(String, default="")   # comma-separated
    year       = Column(Integer, nullable=True)
    ref_type   = Column(SAEnum(
        "paper", "book", "dataset", "standard", "web", "other",
        name="ref_type"), default="paper")
    url        = Column(String, nullable=True)
    doi        = Column(String, nullable=True)
    abstract   = Column(Text, nullable=True)
    notes      = Column(Text, nullable=True)
    tags       = Column(String, default="")   # comma-separated
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project = relationship("Project", back_populates="references")
    author  = relationship("User")


# ─── Notes (Obsidian-like) ───────────────────────────────────────────────────

class Note(Base):
    __tablename__ = "notes"

    id         = Column(String, primary_key=True, default=new_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    author_id  = Column(String, ForeignKey("users.id"))
    title      = Column(String, nullable=False)
    body       = Column(Text, default="")
    folder     = Column(String, default="/")   # virtual folder path
    tags       = Column(String, default="")    # comma-separated
    created_at = Column(DateTime(timezone=True), default=now_utc)
    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project = relationship("Project", back_populates="notes")
    author  = relationship("User")


# ─── Invitations ─────────────────────────────────────────────────────────────

class Invitation(Base):
    __tablename__ = "invitations"

    id             = Column(String, primary_key=True, default=new_uuid)
    email          = Column(String, nullable=False, index=True)
    project_id     = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    role           = Column(String, default="COLLABORATOR")
    token          = Column(String, unique=True, default=new_uuid)   # link token
    pin            = Column(String, nullable=True)                   # hashed 6-digit PIN
    pin_expires_at = Column(DateTime(timezone=True), nullable=True)
    invited_by     = Column(String, ForeignKey("users.id"), nullable=True)
    accepted_at    = Column(DateTime(timezone=True), nullable=True)
    created_at     = Column(DateTime(timezone=True), default=now_utc)

    project = relationship("Project")
    inviter = relationship("User", foreign_keys=[invited_by])


# ─── Documents (Obsidian sync + collaborative editing) ───────────────────────

class Document(Base):
    __tablename__ = "documents"

    id           = Column(String, primary_key=True, default=new_uuid)
    project_id   = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    created_by   = Column(String, ForeignKey("users.id"))
    title        = Column(String, nullable=False)
    body         = Column(Text, default="")
    current_hash = Column(String, nullable=True)   # SHA-256 of body — versioning
    last_editor  = Column(String, ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=now_utc)
    updated_at   = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project   = relationship("Project", back_populates="documents")
    creator   = relationship("User", foreign_keys=[created_by])
    editor    = relationship("User", foreign_keys=[last_editor])
    conflicts = relationship("DocConflict", back_populates="document",
                             cascade="all, delete-orphan")


class DocConflict(Base):
    __tablename__ = "doc_conflicts"

    id           = Column(String, primary_key=True, default=new_uuid)
    document_id  = Column(String, ForeignKey("documents.id", ondelete="CASCADE"))
    content_a    = Column(Text)   # versión en DB al momento del conflicto
    content_b    = Column(Text)   # versión entrante (conflicto)
    submitted_by = Column(String, ForeignKey("users.id"))
    resolved_at  = Column(DateTime(timezone=True), nullable=True)
    resolved_by  = Column(String, ForeignKey("users.id"), nullable=True)
    resolution   = Column(SAEnum("accepted_a", "accepted_b", "manual",
                                 name="conflict_resolution"), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=now_utc)

    document  = relationship("Document", back_populates="conflicts")
    submitter = relationship("User", foreign_keys=[submitted_by])
    resolver  = relationship("User", foreign_keys=[resolved_by])


# ─── Knowledge Graph ─────────────────────────────────────────────────────────

# ─── Project Feature Config & Member Features ────────────────────────────────

class ProjectFeatureConfig(Base):
    """Per-project feature toggles and AI assistant configuration (managed by PI)."""
    __tablename__ = "project_feature_configs"

    id         = Column(String, primary_key=True, default=new_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), unique=True)

    # Feature toggles (project-level enablement)
    feat_obsidian    = Column(Boolean, default=False)   # Obsidian plugin allowed
    feat_ai_local    = Column(Boolean, default=False)   # MCP / Claude Code local AI
    feat_ai_web      = Column(Boolean, default=False)   # Web AI chat assistant
    feat_github_push = Column(Boolean, default=False)   # GitHub propose/push allowed
    feat_wiki        = Column(Boolean, default=False)   # Wiki publish allowed

    # AI assistant config
    ai_provider     = Column(String,  nullable=True)   # "claude" | None
    ai_model        = Column(String,  nullable=True)   # e.g. "claude-sonnet-4-6"
    ai_api_key_enc  = Column(Text,    nullable=True)   # AES-256-GCM encrypted API key
    ai_instructions = Column(Text,    nullable=True)   # Project-level system prompt
    ai_mcp_enabled  = Column(Boolean, default=False)

    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project = relationship("Project", back_populates="feature_config")


class ProjectMemberFeature(Base):
    """Per-user feature authorization within a project (granted by PI)."""
    __tablename__ = "project_member_features"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id         = Column(String, primary_key=True, default=new_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    user_id    = Column(String, ForeignKey("users.id",    ondelete="CASCADE"))

    feat_obsidian    = Column(Boolean, default=False)
    feat_ai_local    = Column(Boolean, default=False)
    feat_ai_web      = Column(Boolean, default=False)
    feat_github_push = Column(Boolean, default=False)
    feat_wiki        = Column(Boolean, default=False)

    updated_at = Column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project = relationship("Project", back_populates="member_features")
    user    = relationship("User")


# ─── Knowledge Graph ─────────────────────────────────────────────────────────

class Relation(Base):
    __tablename__ = "relations"

    id          = Column(String, primary_key=True, default=new_uuid)
    project_id  = Column(String, ForeignKey("projects.id", ondelete="CASCADE"))
    from_id     = Column(String, nullable=False)
    from_type   = Column(String, nullable=False)   # hypothesis|note|milestone|reference|journal|concept
    to_id       = Column(String, nullable=False)
    to_type     = Column(String, nullable=False)
    label       = Column(String, default="relacionado")  # controlled vocab or free text
    auto        = Column(Boolean, default=False)          # True = auto-detected from [[wikilink]]
    created_by  = Column(String, ForeignKey("users.id"), nullable=True)
    created_at  = Column(DateTime(timezone=True), default=now_utc)

    project = relationship("Project", back_populates="relations")
    creator = relationship("User")
