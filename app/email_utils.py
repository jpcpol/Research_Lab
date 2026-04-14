"""
email_utils.py — Envío de correos para el Research Lab
Usa Gmail SMTP_SSL (port 465) con GMAIL_USER + GMAIL_APP_PASSWORD,
igual que management_platform/backend_api/app/services/invitation_service.py.
Sin credenciales → log en stdout (modo dev).
"""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

GMAIL_USER         = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
APP_URL            = os.getenv("APP_URL", "http://localhost:8004")

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, html: str, text: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("[EMAIL-DEV] To=%s | Subject=%s\n%s", to, subject, text)
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Aural-Syncro Research Lab <{GMAIL_USER}>"
    msg["To"]      = to
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html,  "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, to, msg.as_string())
        logger.info("[EMAIL] Sent to=%s subject=%s", to, subject)
    except smtplib.SMTPAuthenticationError:
        logger.error("[EMAIL] Auth failed — verificar GMAIL_APP_PASSWORD")
    except Exception as exc:
        logger.error("[EMAIL] Error enviando a %s: %s", to, exc)


def send_invitation(to: str, project_name: str, inviter_name: str, token: str) -> None:
    link = f"{APP_URL}/?invite={token}"
    subject = f"Invitación al Research Lab — {project_name}"
    text = (
        f"Hola,\n\n"
        f"{inviter_name} te invitó a colaborar en el proyecto '{project_name}' "
        f"en Aural-Syncro Research Lab.\n\n"
        f"Activá tu cuenta con este enlace:\n{link}\n\n"
        f"O bien ingresá a {APP_URL} y escribí tu email para activar tu cuenta.\n\n"
        f"— Aural-Syncro Research Lab"
    )
    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0a0f14;font-family:Inter,system-ui,sans-serif">
<div style="max-width:480px;margin:2rem auto;background:#0f1923;border:0.5px solid rgba(148,210,189,.22);border-radius:12px;padding:2rem">
  <div style="color:#4dd9ac;font-weight:700;font-size:12px;letter-spacing:.1em;margin-bottom:1.5rem">AURAL-SYNCRO · RESEARCH LAB</div>
  <h2 style="color:#e2efe8;font-size:1.15rem;margin:0 0 .75rem">Invitación a colaborar</h2>
  <p style="color:#a8c4b4;font-size:13px;line-height:1.7;margin:0 0 1.25rem">
    <strong style="color:#e2efe8">{inviter_name}</strong> te invitó a participar del proyecto
    <strong style="color:#4dd9ac">"{project_name}"</strong>.
  </p>
  <a href="{link}" style="display:inline-block;background:#2ecc8e;color:#0a0f14;font-weight:700;font-size:13px;padding:12px 24px;border-radius:8px;text-decoration:none">
    Activar mi cuenta →
  </a>
  <p style="color:#7aaa92;font-size:11px;margin-top:1.5rem;line-height:1.6">
    También podés ingresar a <a href="{APP_URL}" style="color:#4dd9ac">{APP_URL}</a>
    y escribir tu email en la pantalla de acceso.
  </p>
</div>
</body>
</html>
"""
    _send(to, subject, html, text)


def send_pin(to: str, pin: str) -> None:
    subject = "Tu código de verificación — Research Lab"
    text = (
        f"Tu PIN de verificación es: {pin}\n\n"
        f"Válido por 15 minutos. No lo compartas con nadie.\n\n"
        f"— Aural-Syncro Research Lab"
    )
    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0a0f14;font-family:Inter,system-ui,sans-serif">
<div style="max-width:420px;margin:2rem auto;background:#0f1923;border:0.5px solid rgba(148,210,189,.22);border-radius:12px;padding:2rem">
  <div style="color:#4dd9ac;font-weight:700;font-size:12px;letter-spacing:.1em;margin-bottom:1.5rem">AURAL-SYNCRO · RESEARCH LAB</div>
  <h2 style="color:#e2efe8;font-size:1.1rem;margin:0 0 1rem">Código de verificación</h2>
  <p style="color:#a8c4b4;font-size:13px;margin:0 0 1rem">Tu PIN de un solo uso:</p>
  <div style="font-size:2.4rem;font-weight:700;letter-spacing:.5em;color:#4dd9ac;font-family:monospace;margin:0 0 1.25rem">{pin}</div>
  <p style="color:#7aaa92;font-size:11px;line-height:1.6">
    Válido por <strong>15 minutos</strong>. No compartas este código.
  </p>
</div>
</body>
</html>
"""
    _send(to, subject, html, text)
