"""
ai_chat.py — Web AI assistant chat endpoint.

Requires:
  - feat_ai_web = True at project level
  - feat_ai_web = True at member level (or PI role)
  - ai_api_key stored in project config

POST /projects/{id}/ai/chat
"""

import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.database import get_db
from app import models
from app.auth import get_current_user, require_project_member

router = APIRouter(prefix="/projects", tags=["ai-chat"])

_ENC_KEY_HEX = os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", "")


def _decrypt(enc_hex: str) -> str:
    if not _ENC_KEY_HEX:
        raise HTTPException(500, "Encryption key not configured on server")
    raw       = bytes.fromhex(enc_hex)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(bytes.fromhex(_ENC_KEY_HEX)).decrypt(nonce, ct, None).decode()


# ── Schemas ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role:    str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message:      str
    context_type: str             = "general"
    history:      List[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    model: str


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/{project_id}/ai/chat", response_model=ChatResponse)
async def ai_chat(
    project_id: str,
    body: ChatRequest,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    member = require_project_member(project_id, user, db, min_role="OBSERVER")

    cfg = db.query(models.ProjectFeatureConfig).filter_by(project_id=project_id).first()
    if not cfg or not cfg.feat_ai_web or not cfg.ai_api_key_enc:
        raise HTTPException(403, "AI assistant not configured for this project")

    if member.role != "PI":
        mf = db.query(models.ProjectMemberFeature).filter_by(
            project_id=project_id, user_id=user.id
        ).first()
        if not mf or not mf.feat_ai_web:
            raise HTTPException(403, "AI assistant not enabled for your account in this project")

    try:
        import anthropic
        api_key = _decrypt(cfg.ai_api_key_enc)
        model   = cfg.ai_model or "claude-sonnet-4-6"
        client  = anthropic.Anthropic(api_key=api_key)
    except Exception as exc:
        raise HTTPException(500, f"Failed to initialize AI client: {exc}")

    project = db.query(models.Project).filter_by(id=project_id).first()
    system  = (
        f"You are a research assistant for the scientific project '{project.name}'. "
        "Help researchers with documentation, analysis, hypotheses, and literature. "
        f"Current section context: {body.context_type}. "
        "Be concise and precise. Respond in the same language the user writes in."
    )
    if cfg.ai_instructions:
        system += f"\n\nProject-specific instructions:\n{cfg.ai_instructions}"

    messages = [{"role": m.role, "content": m.content} for m in body.history[-10:]]
    messages.append({"role": "user", "content": body.message})

    try:
        response = client.messages.create(
            model      = model,
            max_tokens = 1024,
            system     = system,
            messages   = messages,
        )
        reply = response.content[0].text
    except Exception as exc:
        raise HTTPException(500, f"AI request failed: {exc}")

    return ChatResponse(reply=reply, model=model)
