import asyncio
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()

_ROLE_LABELS = {
    "PI":       "Investigador Principal (PI)",
    "collab":   "Colaborador",
    "external": "Investigador Externo",
    "other":    "Otro",
}
_SEP = "─" * 44


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    institution: str
    role: str
    admin: str
    motivo: str
    investigacion: str
    colaboradores: str


def _build_body(req: RegisterRequest) -> str:
    role_label = _ROLE_LABELS.get(req.role, req.role)
    return (
        f"=== RESEARCH LAB — SOLICITUD DE ACCESO ===\n"
        f"{_SEP}\n"
        f"Nombre completo:         {req.name}\n"
        f"Correo institucional:    {req.email}\n"
        f"Institución:             {req.institution}\n"
        f"Rol:                     {role_label}\n"
        f"{_SEP}\n"
        f"Administrador / PI del proyecto:\n{req.admin}\n"
        f"{_SEP}\n"
        f"Motivo de la solicitud:\n{req.motivo}\n"
        f"{_SEP}\n"
        f"Descripción de la investigación:\n{req.investigacion}\n"
        f"{_SEP}\n"
        f"Colaboradores (nombre — correo):\n{req.colaboradores}\n"
        f"{_SEP}\n"
        f"* El solicitante entiende que el asistente IA requiere API key propia de Anthropic.\n"
        f"* El solicitante acepta firmar el acuerdo de uso al primer ingreso.\n"
    )


def _send_sync(req: RegisterRequest) -> None:
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_user or not gmail_pass:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set in environment")

    msg = MIMEMultipart()
    msg["From"]     = gmail_user
    msg["To"]       = gmail_user
    msg["Reply-To"] = req.email
    msg["Subject"]  = "Registrame"
    msg.attach(MIMEText(_build_body(req), "plain", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(gmail_user, gmail_pass)
        srv.sendmail(gmail_user, gmail_user, msg.as_string())


@router.post("/register-request")
async def register_request(req: RegisterRequest):
    if not req.name or not req.institution or not req.role or not req.admin \
            or not req.motivo or not req.investigacion or not req.colaboradores:
        raise HTTPException(status_code=422, detail="All fields are required.")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, partial(_send_sync, req))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except smtplib.SMTPException as exc:
        raise HTTPException(status_code=502, detail=f"SMTP error: {exc}")
    return {"ok": True}
