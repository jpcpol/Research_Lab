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
    admin: str = ""
    motivo: str
    investigacion: str
    colaboradores: str


# ── Plain-text body for admin notification ────────────────────────────────────
def _admin_body(req: RegisterRequest) -> str:
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


# ── HTML confirmation email for the applicant ─────────────────────────────────
def _confirmation_html(req: RegisterRequest) -> str:
    role_label = _ROLE_LABELS.get(req.role, req.role)
    app_url    = os.environ.get("APP_URL", "https://lab.aural-syncro.com.ar")
    logo_url   = "https://researchlab.aural-syncro.com.ar/static/img/aural-logo.png"
    icon_url   = "https://researchlab.aural-syncro.com.ar/static/favicon.png"

    def row(label: str, value: str) -> str:
        return f"""
        <tr>
          <td style="padding:8px 12px;font-size:13px;color:#546e7a;white-space:nowrap;
                     border-bottom:1px solid #e8f5e9;font-weight:600;width:38%;">{label}</td>
          <td style="padding:8px 12px;font-size:13px;color:#1c1c2e;
                     border-bottom:1px solid #e8f5e9;">{value}</td>
        </tr>"""

    def block(label: str, value: str) -> str:
        return f"""
        <tr>
          <td colspan="2" style="padding:12px 12px 4px;font-size:12px;color:#546e7a;
                                  font-weight:700;letter-spacing:.06em;text-transform:uppercase;
                                  border-bottom:1px solid #e8f5e9;">{label}</td>
        </tr>
        <tr>
          <td colspan="2" style="padding:6px 12px 14px;font-size:13px;color:#1c1c2e;
                                  border-bottom:1px solid #e8f5e9;white-space:pre-wrap;">{value}</td>
        </tr>"""

    colaboradores_fmt = req.colaboradores.replace("\n", "<br/>")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Solicitud de acceso recibida — Aural-Syncro Research Lab</title>
</head>
<body style="margin:0;padding:0;background:#eaf3ea;font-family:'Segoe UI',system-ui,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eaf3ea;padding:32px 16px;">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="max-width:600px;width:100%;border-radius:16px;overflow:hidden;
                  box-shadow:0 8px 32px rgba(26,35,126,.13);">

      <!-- ── Header ── -->
      <tr>
        <td style="background:linear-gradient(135deg,#0d1554 0%,#1a237e 50%,#1565c0 100%);
                   padding:36px 40px;text-align:center;">
          <img src="{icon_url}" alt="Research Lab" width="56" height="56"
               style="border-radius:12px;margin-bottom:16px;display:block;margin-inline:auto;
                      border:2px solid rgba(255,255,255,.2);"/>
          <div style="color:rgba(255,255,255,.6);font-size:11px;letter-spacing:.14em;
                      text-transform:uppercase;margin-bottom:6px;">Aural-Syncro</div>
          <h1 style="margin:0;color:#ffffff;font-size:22px;font-family:Georgia,serif;
                     font-weight:700;letter-spacing:.01em;">Research Lab</h1>
          <div style="width:48px;height:3px;background:#ffc107;border-radius:2px;
                      margin:14px auto 0;"></div>
        </td>
      </tr>

      <!-- ── Body ── -->
      <tr>
        <td style="background:#ffffff;padding:36px 40px;">

          <h2 style="margin:0 0 8px;font-size:20px;color:#1a237e;font-family:Georgia,serif;">
            ¡Solicitud recibida, {req.name.split()[0]}!
          </h2>
          <p style="margin:0 0 24px;font-size:14px;color:#546e7a;line-height:1.7;">
            Recibimos tu solicitud de acceso a la plataforma
            <strong style="color:#1a237e;">Aural-Syncro Research Lab</strong>.
            La revisaremos y te enviaremos tus credenciales de acceso en un plazo de
            <strong>24 a 72 horas hábiles</strong>.
          </p>

          <!-- Summary card -->
          <div style="background:#f8fdf8;border:1px solid #b8d8b8;border-radius:10px;
                      overflow:hidden;margin-bottom:28px;">
            <div style="background:#1a237e;padding:10px 16px;">
              <span style="color:#ffc107;font-size:11px;font-weight:700;letter-spacing:.1em;
                           text-transform:uppercase;">Resumen de tu solicitud</span>
            </div>
            <table width="100%" cellpadding="0" cellspacing="0">
              {row("Nombre", req.name)}
              {row("Correo", req.email)}
              {row("Institución", req.institution)}
              {row("Rol", role_label)}
              {row("Administrador / PI", req.admin)}
              {block("Motivo", req.motivo)}
              {block("Investigación", req.investigacion)}
              <tr>
                <td style="padding:8px 12px;font-size:13px;color:#546e7a;white-space:nowrap;
                           font-weight:600;width:38%;">Colaboradores</td>
                <td style="padding:8px 12px;font-size:13px;color:#1c1c2e;">{colaboradores_fmt}</td>
              </tr>
            </table>
          </div>

          <!-- Next steps -->
          <div style="background:#fff8e1;border-left:4px solid #ffc107;border-radius:0 8px 8px 0;
                      padding:16px 20px;margin-bottom:28px;">
            <p style="margin:0 0 6px;font-size:13px;font-weight:700;color:#c8930a;">
              Próximos pasos
            </p>
            <ol style="margin:0;padding-left:18px;font-size:13px;color:#546e7a;line-height:1.9;">
              <li>Revisión de tu solicitud por el equipo de Aural-Syncro</li>
              <li>Recibirás un correo con tus credenciales de acceso</li>
              <li>Al ingresar por primera vez, firmarás el acuerdo de uso de la plataforma</li>
              <li>¡Listo para investigar!</li>
            </ol>
          </div>

          <p style="margin:0;font-size:13px;color:#7da87d;text-align:center;line-height:1.6;">
            Si no realizaste esta solicitud, podés ignorar este correo.<br/>
            Ante cualquier consulta, respondé directamente a este mensaje.
          </p>
        </td>
      </tr>

      <!-- ── Footer ── -->
      <tr>
        <td style="background:#1a237e;padding:24px 40px;text-align:center;">
          <img src="{logo_url}" alt="Aural-Syncro" height="40"
               style="display:block;margin:0 auto 12px;opacity:.9;"/>
          <p style="margin:0 0 4px;font-size:11px;color:#7986cb;letter-spacing:.08em;
                    text-transform:uppercase;">Aural-Syncro · Research Lab</p>
          <p style="margin:0;font-size:11px;color:#5c6bc0;">
            Procesamiento en el origen para soluciones en tiempo real
          </p>
          <div style="margin-top:14px;padding-top:14px;border-top:1px solid rgba(255,255,255,.1);">
            <a href="{app_url}" style="color:#ffc107;font-size:11px;text-decoration:none;">
              {app_url.replace("https://", "")}
            </a>
            &nbsp;·&nbsp;
            <span style="color:#5c6bc0;font-size:11px;">Argentina</span>
          </div>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _confirmation_plain(req: RegisterRequest) -> str:
    role_label = _ROLE_LABELS.get(req.role, req.role)
    app_url    = os.environ.get("APP_URL", "https://lab.aural-syncro.com.ar")
    return (
        f"Aural-Syncro Research Lab\n"
        f"{'=' * 44}\n\n"
        f"¡Solicitud recibida, {req.name.split()[0]}!\n\n"
        f"Recibimos tu solicitud de acceso a la plataforma Aural-Syncro Research Lab.\n"
        f"La revisaremos y te enviaremos tus credenciales en 24 a 72 horas hábiles.\n\n"
        f"{'─' * 44}\n"
        f"RESUMEN DE TU SOLICITUD\n"
        f"{'─' * 44}\n"
        f"Nombre:        {req.name}\n"
        f"Correo:        {req.email}\n"
        f"Institución:   {req.institution}\n"
        f"Rol:           {role_label}\n"
        f"Administrador: {req.admin}\n\n"
        f"Motivo:\n{req.motivo}\n\n"
        f"Investigación:\n{req.investigacion}\n\n"
        f"Colaboradores:\n{req.colaboradores}\n\n"
        f"{'─' * 44}\n"
        f"PRÓXIMOS PASOS\n"
        f"{'─' * 44}\n"
        f"1. Revisión de tu solicitud por el equipo de Aural-Syncro\n"
        f"2. Recibirás un correo con tus credenciales de acceso\n"
        f"3. Al ingresar por primera vez firmarás el acuerdo de uso\n"
        f"4. ¡Listo para investigar!\n\n"
        f"Ante cualquier consulta, respondé directamente a este mensaje.\n\n"
        f"{'─' * 44}\n"
        f"Aural-Syncro Research Lab\n"
        f"{app_url}\n"
    )


# ── SMTP helper ───────────────────────────────────────────────────────────────
def _smtp_send(gmail_user: str, gmail_pass: str, msg: MIMEMultipart) -> None:
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as srv:
        srv.login(gmail_user, gmail_pass)
        srv.sendmail(msg["From"], msg["To"].split(","), msg.as_string())


def _send_sync(req: RegisterRequest) -> None:
    gmail_user = os.environ.get("GMAIL_USER", "")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not gmail_user or not gmail_pass:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set in environment")

    # 1 — Admin notification (plain text, subject "Registrame")
    admin_msg = MIMEMultipart()
    admin_msg["From"]     = gmail_user
    admin_msg["To"]       = gmail_user
    admin_msg["Reply-To"] = req.email
    admin_msg["Subject"]  = "Registrame"
    admin_msg.attach(MIMEText(_admin_body(req), "plain", "utf-8"))
    _smtp_send(gmail_user, gmail_pass, admin_msg)

    # 2 — Confirmation to applicant (HTML + plain fallback)
    confirm_msg = MIMEMultipart("alternative")
    confirm_msg["From"]     = f"Aural-Syncro Research Lab <{gmail_user}>"
    confirm_msg["To"]       = req.email
    confirm_msg["Reply-To"] = gmail_user
    confirm_msg["Subject"]  = "Research Lab — Solicitud de acceso recibida"
    confirm_msg.attach(MIMEText(_confirmation_plain(req), "plain", "utf-8"))
    confirm_msg.attach(MIMEText(_confirmation_html(req),  "html",  "utf-8"))
    _smtp_send(gmail_user, gmail_pass, confirm_msg)


# ── Endpoint ──────────────────────────────────────────────────────────────────
@router.post("/register-request")
async def register_request(req: RegisterRequest):
    if not req.name or not req.institution or not req.role \
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
