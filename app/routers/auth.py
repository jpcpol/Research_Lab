import os
import random
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from jose import jwt, JWTError
from sqlalchemy.orm import Session

AVATAR_DIR = Path("/app/static/avatars")
AVATAR_ALLOWED = {"image/jpeg", "image/png", "image/webp"}
AVATAR_EXT     = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
AVATAR_MAX_MB  = 2

from app.database import get_db
from app import models, schemas, email_utils
from app.auth import (
    hash_password, verify_password, create_token, get_current_user,
    SECRET_KEY, ALGORITHM, TOKEN_EXPIRE_HOURS,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_REGISTRATION_OPEN = os.getenv("REGISTRATION_OPEN", "false").lower() == "true"


# ── Registro público (solo si REGISTRATION_OPEN=true) ─────────────────────────

@router.post("/register", response_model=schemas.TokenResponse, status_code=201)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    """Registro de cuenta nueva. Deshabilitado por defecto (REGISTRATION_OPEN=false)."""
    if not _REGISTRATION_OPEN:
        raise HTTPException(403, "Public registration is disabled. Contact the administrator to receive an invitation.")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if db.query(models.User).filter(models.User.email == body.email.lower()).first():
        raise HTTPException(400, "Email already registered")
    user = models.User(
        email=body.email.lower().strip(),
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer", "user": user}


# ── Refresco de token ──────────────────────────────────────────────────────────

@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh_token(current_user: models.User = Depends(get_current_user)):
    """Emite un nuevo JWT si el actual es válido. Llámalo antes de que expire."""
    token = create_token(current_user.id)
    return {"access_token": token, "token_type": "bearer", "user": current_user}


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=schemas.TokenResponse)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer", "user": user}


# ── Login con PIN (2FA por email) ──────────────────────────────────────────────

class RequestLoginPinBody(schemas.BaseModel):
    email: str

@router.post("/request-login-pin")
def request_login_pin(body: RequestLoginPinBody, db: Session = Depends(get_db)):
    """Genera PIN de 6 dígitos para un colaborador activo y lo envía por email."""
    user = db.query(models.User).filter(
        models.User.email == body.email.lower().strip(),
        models.User.is_active == True,
    ).first()
    if user:
        pin = str(random.randint(100000, 999999))
        user.login_pin            = hash_password(pin)
        user.login_pin_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        db.commit()
        try:
            email_utils.send_pin(user.email, pin)
        except Exception as exc:
            logger.error("Error enviando login PIN a %s: %s", user.email, exc)
    # Respuesta idéntica — no revela si el email existe
    return {"sent": True}


class LoginWithPinBody(schemas.BaseModel):
    email:    str
    password: str
    pin:      str

@router.post("/login-with-pin", response_model=schemas.TokenResponse)
def login_with_pin(body: LoginWithPinBody, db: Session = Depends(get_db)):
    """Login de colaboradores con email + contraseña + PIN de verificación."""
    user = db.query(models.User).filter(models.User.email == body.email.lower().strip()).first()

    password_ok = bool(user) and verify_password(body.password, user.hashed_password if user else "x")

    if not user or not password_ok or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials or code.")

    if not user.login_pin:
        raise HTTPException(status_code=400, detail="Request a verification code first.")

    if not verify_password(body.pin, user.login_pin):
        raise HTTPException(status_code=401, detail="Invalid credentials or code.")

    if not user.login_pin_expires_at or datetime.now(timezone.utc) > user.login_pin_expires_at:
        raise HTTPException(status_code=400, detail="Code expired — request a new one.")

    # PIN de uso único
    user.login_pin            = None
    user.login_pin_expires_at = None
    db.commit()

    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ── Invitation flow ────────────────────────────────────────────────────────────

@router.get("/check-invite", response_model=schemas.InviteCheckResponse)
def check_invite(
    email: str = Query(...),
    db: Session = Depends(get_db),
):
    """Check if an email has a pending invitation (for smart login form)."""
    inv = (
        db.query(models.Invitation)
        .filter(
            models.Invitation.email == email.lower().strip(),
            models.Invitation.accepted_at.is_(None),
        )
        .first()
    )
    if not inv:
        return {"invited": False}
    project_name = inv.project.name if inv.project else None
    return {"invited": True, "project_name": project_name, "token": inv.token}


@router.get("/invite-info", response_model=schemas.InviteInfoResponse)
def invite_info(
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """Get email + project name from an invite token (for URL ?invite=TOKEN flow)."""
    inv = (
        db.query(models.Invitation)
        .filter(
            models.Invitation.token == token,
            models.Invitation.accepted_at.is_(None),
        )
        .first()
    )
    if not inv:
        raise HTTPException(404, "Invitation not found or already used")
    return {
        "email": inv.email,
        "project_name": inv.project.name if inv.project else None,
    }


@router.post("/send-pin")
def send_pin(body: schemas.SendPinRequest, db: Session = Depends(get_db)):
    """Generate a 6-digit PIN, save it hashed, and email it to the invitee."""
    email = body.email.lower().strip()
    inv = (
        db.query(models.Invitation)
        .filter(
            models.Invitation.email == email,
            models.Invitation.accepted_at.is_(None),
        )
        .first()
    )
    if not inv:
        raise HTTPException(404, "No pending invitation for this email")

    pin = str(random.randint(100000, 999999))
    inv.pin            = hash_password(pin)
    inv.pin_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    email_utils.send_pin(email, pin)
    return {"sent": True}


# ── Profile ───────────────────────────────────────────────────────────────────

@router.post("/profile/avatar", response_model=schemas.UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in AVATAR_ALLOWED:
        raise HTTPException(400, "Only JPG, PNG or WebP images are allowed")
    contents = await file.read()
    if len(contents) > AVATAR_MAX_MB * 1024 * 1024:
        raise HTTPException(400, f"Image must not exceed {AVATAR_MAX_MB} MB")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    # Remove previous avatar for this user (any extension)
    for old in AVATAR_DIR.glob(f"{user.id}.*"):
        old.unlink(missing_ok=True)

    ext  = AVATAR_EXT[file.content_type]
    path = AVATAR_DIR / f"{user.id}.{ext}"
    path.write_bytes(contents)

    user.avatar_url = f"/static/avatars/{user.id}.{ext}"
    db.commit()
    db.refresh(user)
    return user


@router.patch("/profile", response_model=schemas.UserOut)
def update_profile(
    body: schemas.UpdateProfileRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name cannot be empty")
    user.name = name
    db.commit()
    db.refresh(user)
    return user


@router.patch("/profile/professional", response_model=schemas.UserOut)
def update_professional(
    body: schemas.UpdateProfessionalRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actualiza datos profesionales e institucionales del usuario."""
    if body.title       is not None: user.title       = body.title.strip()       or None
    if body.institution is not None: user.institution = body.institution.strip()  or None
    if body.department  is not None: user.department  = body.department.strip()   or None
    if body.orcid       is not None: user.orcid       = body.orcid.strip()        or None
    if body.bio         is not None: user.bio         = body.bio.strip()          or None
    if body.website     is not None: user.website     = body.website.strip()      or None
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password")
def change_password(
    body: schemas.ChangePasswordRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"ok": True}


@router.post("/change-email/request")
def request_email_change(
    body: schemas.RequestEmailChangeRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    new_email = body.new_email.lower().strip()
    if new_email == user.email.lower():
        raise HTTPException(400, "Same as current email")
    if db.query(models.User).filter(models.User.email == new_email).first():
        raise HTTPException(400, "Email already in use by another account")

    pin = str(random.randint(100000, 999999))
    user.pending_email               = new_email
    user.email_change_pin            = hash_password(pin)
    user.email_change_pin_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    try:
        email_utils.send_pin(new_email, pin)
    except Exception as exc:
        logger.error("Error sending email-change PIN: %s", exc)

    return {"sent": True, "email": new_email}


@router.post("/change-email/confirm", response_model=schemas.UserOut)
def confirm_email_change(
    body: schemas.ConfirmEmailChangeRequest,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user.pending_email or not user.email_change_pin:
        raise HTTPException(400, "No pending email change")
    if not verify_password(body.pin, user.email_change_pin):
        raise HTTPException(400, "Incorrect PIN")
    if not user.email_change_pin_expires_at or \
            datetime.now(timezone.utc) > user.email_change_pin_expires_at:
        raise HTTPException(400, "PIN expired — request a new one")

    user.email                       = user.pending_email
    user.pending_email               = None
    user.email_change_pin            = None
    user.email_change_pin_expires_at = None
    db.commit()
    db.refresh(user)
    return user


# ── Invitation flow ────────────────────────────────────────────────────────────

@router.post("/accept-invite", response_model=schemas.TokenResponse)
def accept_invite(body: schemas.AcceptInviteRequest, db: Session = Depends(get_db)):
    """Validate PIN, create user account, add to project, mark invitation done."""
    inv = (
        db.query(models.Invitation)
        .filter(
            models.Invitation.token == body.token,
            models.Invitation.accepted_at.is_(None),
        )
        .first()
    )
    if not inv:
        raise HTTPException(404, "Invitation not found or already used")

    if not inv.pin:
        raise HTTPException(400, "Request a verification PIN first")

    if not verify_password(body.pin, inv.pin):
        raise HTTPException(400, "Incorrect PIN")

    if not inv.pin_expires_at or datetime.now(timezone.utc) > inv.pin_expires_at:
        raise HTTPException(400, "PIN expired — request a new one")

    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")

    existing = db.query(models.User).filter(models.User.email == inv.email).first()
    if existing:
        raise HTTPException(
            400,
            "This email already has an account. Sign in normally with your password.",
        )

    # Create account
    user = models.User(
        email=inv.email,
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.flush()

    # Add to project
    if inv.project_id:
        db.add(
            models.ProjectMember(
                project_id=inv.project_id,
                user_id=user.id,
                role=inv.role,
            )
        )

    inv.accepted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer", "user": user}
