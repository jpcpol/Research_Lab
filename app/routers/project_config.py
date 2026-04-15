"""
project_config.py — Project feature flags, AI config, and per-member authorizations.

Endpoints:
  GET  /projects/{id}/config                      — PI only: get project config
  PUT  /projects/{id}/config                      — PI only: update project config
  GET  /projects/{id}/config/members              — PI only: list member feature access
  PUT  /projects/{id}/config/members/{user_id}    — PI only: set member feature access
  GET  /projects/{id}/my-features                 — Any member: my feature access
"""

import os
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.database import get_db
from app import models
from app.auth import get_current_user, require_project_member

router = APIRouter(prefix="/projects", tags=["project-config"])

_ENC_KEY_HEX = os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", "")


# ── Crypto helpers ─────────────────────────────────────────────────────────────

def _encrypt(plaintext: str) -> str:
    if not _ENC_KEY_HEX:
        raise HTTPException(500, "Encryption key not configured on server")
    key   = bytes.fromhex(_ENC_KEY_HEX)
    nonce = secrets.token_bytes(12)
    ct    = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return (nonce + ct).hex()


def _decrypt(enc_hex: str) -> str:
    if not _ENC_KEY_HEX:
        raise HTTPException(500, "Encryption key not configured on server")
    raw       = bytes.fromhex(enc_hex)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(bytes.fromhex(_ENC_KEY_HEX)).decrypt(nonce, ct, None).decode()


def _get_or_create_config(project_id: str, db: Session) -> models.ProjectFeatureConfig:
    cfg = db.query(models.ProjectFeatureConfig).filter_by(project_id=project_id).first()
    if not cfg:
        cfg = models.ProjectFeatureConfig(project_id=project_id)
        db.add(cfg)
        db.flush()
    return cfg


# ── Schemas ────────────────────────────────────────────────────────────────────

class FeatureConfigIn(BaseModel):
    feat_obsidian:    bool = False
    feat_ai_local:    bool = False
    feat_ai_web:      bool = False
    feat_github_push: bool = False
    feat_wiki:        bool = False
    ai_provider:      Optional[str] = None
    ai_model:         Optional[str] = None
    ai_api_key:       Optional[str] = None   # plaintext — encrypted before storing
    ai_instructions:  Optional[str] = None
    ai_mcp_enabled:   bool = False


class FeatureConfigOut(BaseModel):
    feat_obsidian:    bool
    feat_ai_local:    bool
    feat_ai_web:      bool
    feat_github_push: bool
    feat_wiki:        bool
    ai_provider:      Optional[str]
    ai_model:         Optional[str]
    ai_api_key_set:   bool           # True if a key is stored (never exposed)
    ai_instructions:  Optional[str]
    ai_mcp_enabled:   bool


class MemberFeaturesIn(BaseModel):
    feat_obsidian:    bool = False
    feat_ai_local:    bool = False
    feat_ai_web:      bool = False
    feat_github_push: bool = False
    feat_wiki:        bool = False


class MemberFeaturesOut(BaseModel):
    user_id:          str
    user_name:        str
    user_email:       str
    role:             str
    feat_obsidian:    bool
    feat_ai_local:    bool
    feat_ai_web:      bool
    feat_github_push: bool
    feat_wiki:        bool


class MyFeaturesOut(BaseModel):
    role:              str
    feat_obsidian:     bool
    feat_ai_local:     bool
    feat_ai_web:       bool
    feat_github_push:  bool
    feat_wiki:         bool
    ai_web_available:  bool   # True only if feat_ai_web + key stored


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/config", response_model=FeatureConfigOut)
def get_project_config(
    project_id: str,
    db:   Session       = Depends(get_db),
    user: models.User   = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    cfg = _get_or_create_config(project_id, db)
    db.commit()
    return FeatureConfigOut(
        feat_obsidian    = cfg.feat_obsidian,
        feat_ai_local    = cfg.feat_ai_local,
        feat_ai_web      = cfg.feat_ai_web,
        feat_github_push = cfg.feat_github_push,
        feat_wiki        = cfg.feat_wiki,
        ai_provider      = cfg.ai_provider,
        ai_model         = cfg.ai_model,
        ai_api_key_set   = bool(cfg.ai_api_key_enc),
        ai_instructions  = cfg.ai_instructions,
        ai_mcp_enabled   = cfg.ai_mcp_enabled,
    )


@router.put("/{project_id}/config", response_model=FeatureConfigOut)
def update_project_config(
    project_id: str,
    body: FeatureConfigIn,
    db:   Session       = Depends(get_db),
    user: models.User   = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    cfg = _get_or_create_config(project_id, db)

    cfg.feat_obsidian    = body.feat_obsidian
    cfg.feat_ai_local    = body.feat_ai_local
    cfg.feat_ai_web      = body.feat_ai_web
    cfg.feat_github_push = body.feat_github_push
    cfg.feat_wiki        = body.feat_wiki
    cfg.ai_provider      = body.ai_provider
    cfg.ai_model         = body.ai_model
    cfg.ai_instructions  = body.ai_instructions
    cfg.ai_mcp_enabled   = body.ai_mcp_enabled

    if body.ai_api_key is not None and body.ai_api_key.strip():
        cfg.ai_api_key_enc = _encrypt(body.ai_api_key.strip())

    db.commit()
    db.refresh(cfg)
    return FeatureConfigOut(
        feat_obsidian    = cfg.feat_obsidian,
        feat_ai_local    = cfg.feat_ai_local,
        feat_ai_web      = cfg.feat_ai_web,
        feat_github_push = cfg.feat_github_push,
        feat_wiki        = cfg.feat_wiki,
        ai_provider      = cfg.ai_provider,
        ai_model         = cfg.ai_model,
        ai_api_key_set   = bool(cfg.ai_api_key_enc),
        ai_instructions  = cfg.ai_instructions,
        ai_mcp_enabled   = cfg.ai_mcp_enabled,
    )


@router.get("/{project_id}/config/members", response_model=List[MemberFeaturesOut])
def get_member_features(
    project_id: str,
    db:   Session       = Depends(get_db),
    user: models.User   = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    members = db.query(models.ProjectMember).filter_by(project_id=project_id).all()
    result  = []
    for m in members:
        mf = db.query(models.ProjectMemberFeature).filter_by(
            project_id=project_id, user_id=m.user_id
        ).first()
        result.append(MemberFeaturesOut(
            user_id          = m.user_id,
            user_name        = m.user.name,
            user_email       = m.user.email,
            role             = m.role,
            feat_obsidian    = mf.feat_obsidian    if mf else False,
            feat_ai_local    = mf.feat_ai_local    if mf else False,
            feat_ai_web      = mf.feat_ai_web      if mf else False,
            feat_github_push = mf.feat_github_push if mf else False,
            feat_wiki        = mf.feat_wiki        if mf else False,
        ))
    return result


@router.put("/{project_id}/config/members/{target_user_id}", response_model=MemberFeaturesOut)
def update_member_features(
    project_id:     str,
    target_user_id: str,
    body: MemberFeaturesIn,
    db:   Session       = Depends(get_db),
    user: models.User   = Depends(get_current_user),
):
    require_project_member(project_id, user, db, min_role="PI")
    member = db.query(models.ProjectMember).filter_by(
        project_id=project_id, user_id=target_user_id
    ).first()
    if not member:
        raise HTTPException(404, "Member not found in this project")

    mf = db.query(models.ProjectMemberFeature).filter_by(
        project_id=project_id, user_id=target_user_id
    ).first()
    if not mf:
        mf = models.ProjectMemberFeature(project_id=project_id, user_id=target_user_id)
        db.add(mf)

    mf.feat_obsidian    = body.feat_obsidian
    mf.feat_ai_local    = body.feat_ai_local
    mf.feat_ai_web      = body.feat_ai_web
    mf.feat_github_push = body.feat_github_push
    mf.feat_wiki        = body.feat_wiki

    db.commit()
    db.refresh(mf)
    return MemberFeaturesOut(
        user_id          = member.user_id,
        user_name        = member.user.name,
        user_email       = member.user.email,
        role             = member.role,
        feat_obsidian    = mf.feat_obsidian,
        feat_ai_local    = mf.feat_ai_local,
        feat_ai_web      = mf.feat_ai_web,
        feat_github_push = mf.feat_github_push,
        feat_wiki        = mf.feat_wiki,
    )


@router.get("/{project_id}/my-features", response_model=MyFeaturesOut)
def get_my_features(
    project_id: str,
    db:   Session       = Depends(get_db),
    user: models.User   = Depends(get_current_user),
):
    member = require_project_member(project_id, user, db, min_role="OBSERVER")
    cfg    = db.query(models.ProjectFeatureConfig).filter_by(project_id=project_id).first()

    # PI always has all features available; AI web requires key to be configured
    if member.role == "PI":
        return MyFeaturesOut(
            role             = "PI",
            feat_obsidian    = True,
            feat_ai_local    = True,
            feat_ai_web      = bool(cfg and cfg.feat_ai_web),
            feat_github_push = True,
            feat_wiki        = True,
            ai_web_available = bool(cfg and cfg.feat_ai_web and cfg.ai_api_key_enc),
        )

    mf = db.query(models.ProjectMemberFeature).filter_by(
        project_id=project_id, user_id=user.id
    ).first()

    def _both(member_flag: bool, project_flag: bool) -> bool:
        return member_flag and project_flag

    return MyFeaturesOut(
        role             = member.role,
        feat_obsidian    = _both(mf.feat_obsidian    if mf else False, cfg.feat_obsidian    if cfg else False),
        feat_ai_local    = _both(mf.feat_ai_local    if mf else False, cfg.feat_ai_local    if cfg else False),
        feat_ai_web      = _both(mf.feat_ai_web      if mf else False, cfg.feat_ai_web      if cfg else False),
        feat_github_push = _both(mf.feat_github_push if mf else False, cfg.feat_github_push if cfg else False),
        feat_wiki        = _both(mf.feat_wiki        if mf else False, cfg.feat_wiki        if cfg else False),
        ai_web_available = _both(mf.feat_ai_web      if mf else False, cfg.feat_ai_web      if cfg else False)
                           and bool(cfg.ai_api_key_enc if cfg else None),
    )
