import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

SECRET_KEY  = os.getenv("SECRET_KEY", "change-me-in-production-min-32-chars!!")
ALGORITHM   = "HS256"
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "72"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer      = HTTPBearer(auto_error=False)


# ─── Password helpers ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT helpers ──────────────────────────────────────────────────────────────

def create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": user_id, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ─── FastAPI dependency ───────────────────────────────────────────────────────

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")
    user_id = decode_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired token")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User not found or inactive")
    return user


def require_project_member(project_id: str, user: models.User, db: Session,
                            min_role: str = "OBSERVER") -> models.ProjectMember:
    roles_order = {"OBSERVER": 0, "COLLABORATOR": 1, "PI": 2}
    member = db.query(models.ProjectMember).filter(
        models.ProjectMember.project_id == project_id,
        models.ProjectMember.user_id == user.id,
    ).first()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this project")
    if roles_order.get(member.role, 0) < roles_order.get(min_role, 0):
        raise HTTPException(status_code=403, detail="Insufficient role")
    return member
