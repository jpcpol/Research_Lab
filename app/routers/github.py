"""
DT-RL-009 rev-3 — GitHub App Integration (credenciales por proyecto)
- App ID y clave privada configurados por PI en cada proyecto (cifrados en DB)
- Auth via GitHub App Installation Tokens (1 h, sin PAT personal)
- Footer de autoría profesional en cada archivo exportado
- Tipos: note, hypothesis, journal, milestone, reference
- Endpoint extra: push-graph (Mermaid snapshot al repo)
"""
import os, re, json, base64, time, secrets
import urllib.request, urllib.error
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as rsa_padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.database import get_db
from app import models
from app.auth import get_current_user, require_project_member

router = APIRouter(prefix="/projects", tags=["github"])

# ── Encryption key for per-project App private keys stored in DB ──────────────
_ENC_KEY_HEX = os.getenv("GITHUB_TOKEN_ENCRYPTION_KEY", "")

# ── Installation token cache: { (installation_id, app_id) → (token, expires_ts) }
_token_cache: dict = {}


# ── Encryption helpers ────────────────────────────────────────────────────────

def _encrypt(plaintext: str) -> str:
    """AES-256-GCM encrypt. Returns hex(nonce + ciphertext)."""
    if not _ENC_KEY_HEX:
        raise HTTPException(500, "GITHUB_TOKEN_ENCRYPTION_KEY not configured on server")
    key   = bytes.fromhex(_ENC_KEY_HEX)
    nonce = secrets.token_bytes(12)
    ct    = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
    return (nonce + ct).hex()


def _decrypt(enc_hex: str) -> str:
    """AES-256-GCM decrypt."""
    if not _ENC_KEY_HEX:
        raise HTTPException(500, "GITHUB_TOKEN_ENCRYPTION_KEY not configured on server")
    raw       = bytes.fromhex(enc_hex)
    nonce, ct = raw[:12], raw[12:]
    return AESGCM(bytes.fromhex(_ENC_KEY_HEX)).decrypt(nonce, ct, None).decode()


# ── JWT signing helpers ───────────────────────────────────────────────────────

def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).rstrip(b"=").decode()

def _b64url_b(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _make_app_jwt(app_id: str, key_b64: str) -> str:
    """JWT de 10 min firmado con la clave privada de la App."""
    try:
        pem         = base64.b64decode(key_b64)
        private_key = serialization.load_pem_private_key(pem, password=None)
    except Exception as exc:
        raise HTTPException(400, f"Invalid GitHub App private key: {exc}")

    now = int(time.time())
    hdr = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}))
    pay = _b64url(json.dumps({"iat": now - 60, "exp": now + 600, "iss": app_id}))
    msg = f"{hdr}.{pay}".encode()
    sig = private_key.sign(msg, rsa_padding.PKCS1v15(), hashes.SHA256())
    return f"{hdr}.{pay}.{_b64url_b(sig)}"


# ── Installation token ────────────────────────────────────────────────────────

def _get_installation_token(installation_id: int, app_id: str, key_b64: str) -> str:
    """Retorna un token de instalación válido (1 h), refrescándolo si quedan < 60 s."""
    cache_key = (str(installation_id), str(app_id))
    cached    = _token_cache.get(cache_key)
    if cached:
        tok, exp = cached
        if time.time() < exp - 60:
            return tok

    app_jwt = _make_app_jwt(app_id, key_b64)
    resp    = _gh("POST", f"/app/installations/{installation_id}/access_tokens", app_jwt)
    tok     = resp.get("token")
    if not tok:
        raise HTTPException(500,
            f"GitHub did not return a token for installation {installation_id}. "
            "Verify the Installation ID is correct and the App is still installed.")
    _token_cache[cache_key] = (tok, time.time() + 3600)
    return tok


# ── GitHub REST helper ────────────────────────────────────────────────────────

def _gh(method: str, path: str, gh_token: str, body: dict = None) -> dict:
    url     = f"https://api.github.com{path}"
    headers = {
        "Authorization":        f"Bearer {gh_token}",
        "Accept":               "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":         "application/json",
        "User-Agent":           "SSPA-ResearchLab/3.0",
    }
    data = json.dumps(body).encode() if body is not None else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            err = json.loads(raw)
            raise HTTPException(e.code, err.get("message", str(e)))
        except (json.JSONDecodeError, KeyError):
            raise HTTPException(e.code, raw.decode())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    text = text.lower()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n"),("ü","u")]:
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:60]


def _author_footer(author: models.User) -> str:
    """Footer de autoría para trazabilidad de contribuciones en el repo."""
    lines = ["\n\n---\n\n## Autoría\n\n"]
    title_prefix = f"{author.title} " if author.title else ""
    lines.append(f"**{title_prefix}{author.name}**  \n")
    if author.institution:
        dept = f" — {author.department}" if author.department else ""
        lines.append(f"*{author.institution}{dept}*  \n")
    if author.orcid:
        lines.append(f"ORCID: [{author.orcid}](https://orcid.org/{author.orcid})  \n")
    if author.website:
        lines.append(f"Web: {author.website}  \n")
    lines.append(
        f"\n*Contribución registrada en Aural-Syncro Research Lab · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n"
    )
    return "".join(lines)


def _to_markdown(content_type: str, obj, author: models.User) -> tuple[str, str]:
    """Retorna (file_path, markdown) con footer de autoría."""
    status_map = {
        "pending":"Pendiente","in_progress":"En proceso",
        "validated":"Validada","rejected":"Rechazada","on_hold":"En espera",
    }
    entry_map = {
        "progress":"Avance","modification":"Modificación",
        "decision":"Decisión","milestone":"Hito","note":"Nota",
    }

    if content_type == "note":
        slug = _slugify(obj.title)
        path = f"lab/notas/{slug}.md"
        md   = f"# {obj.title}\n\n"
        if obj.folder and obj.folder != "/":
            md += f"**Carpeta:** `{obj.folder}`  \n"
        if obj.tags:
            tags = " ".join(f"`#{t.strip()}`" for t in obj.tags.split(",") if t.strip())
            md += f"**Etiquetas:** {tags}  \n"
        md += f"\n{obj.body or ''}\n"

    elif content_type == "hypothesis":
        slug = _slugify(obj.title)
        path = f"lab/hipotesis/{slug}.md"
        md   = f"# Hipótesis: {obj.title}\n\n"
        md  += f"**Estado:** {status_map.get(obj.status, obj.status)}  \n"
        md  += f"**Prioridad:** P{obj.priority}  \n"
        md  += f"**Creado:** {obj.created_at.strftime('%Y-%m-%d')}\n\n"
        if obj.description:
            md += f"## Descripción\n\n{obj.description}\n"

    elif content_type == "journal":
        title = obj.title or obj.id[:8]
        slug  = _slugify(title)
        path  = f"lab/bitacora/{slug}.md"
        md    = f"# Bitácora: {title}\n\n"
        md   += f"**Tipo:** {entry_map.get(obj.entry_type, obj.entry_type)}  \n"
        md   += f"**Fecha:** {obj.created_at.strftime('%Y-%m-%d %H:%M UTC')}  \n"
        if obj.tags:
            tags = " ".join(f"`#{t.strip()}`" for t in obj.tags.split(",") if t.strip())
            md  += f"**Etiquetas:** {tags}  \n"
        md   += f"\n---\n\n{obj.body}\n"

    elif content_type == "milestone":
        slug = _slugify(obj.title)
        path = f"lab/hitos/{slug}.md"
        md   = f"# Hito: {obj.title}\n\n"
        if obj.due_date:
            md += f"**Fecha límite:** {obj.due_date}  \n"
        if obj.completed_at:
            md += f"**Completado:** {obj.completed_at.strftime('%Y-%m-%d')}  \n"
        md += "\n"
        if obj.description:
            md += f"## Descripción\n\n{obj.description}\n\n"
        reqs = getattr(obj, "requirements", []) or []
        if reqs:
            md += "## Requerimientos\n\n"
            for r in reqs:
                check = "x" if r.status == "done" else " "
                note  = f" — {r.notes}" if r.notes else ""
                md   += f"- [{check}] {r.title}{note}\n"

    elif content_type == "reference":
        slug = _slugify(obj.title)
        path = f"lab/referencias/{slug}.md"
        md   = f"# {obj.title}\n\n"
        md  += f"**Tipo:** {obj.ref_type}  \n"
        if obj.authors:
            md += f"**Autores:** {obj.authors}  \n"
        if obj.year:
            md += f"**Año:** {obj.year}  \n"
        if obj.doi:
            md += f"**DOI:** [{obj.doi}](https://doi.org/{obj.doi})  \n"
        if obj.url:
            md += f"**URL:** {obj.url}  \n"
        if obj.tags:
            tags = " ".join(f"`#{t.strip()}`" for t in obj.tags.split(",") if t.strip())
            md += f"**Etiquetas:** {tags}  \n"
        if obj.abstract:
            md += f"\n## Resumen\n\n{obj.abstract}\n"
        if obj.notes:
            md += f"\n## Notas del equipo\n\n{obj.notes}\n"

    else:
        raise HTTPException(400, f"Unsupported content type: {content_type}")

    md += _author_footer(author)
    return path, md


def _get_project_connected(project_id: str, db: Session) -> models.Project:
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    if not (p.github_installation_id and p.github_app_id and p.github_app_private_key_enc):
        raise HTTPException(400, "GitHub App not configured for this project")
    return p


def _project_gh_token(p: models.Project) -> str:
    """Obtiene el installation token usando las credenciales cifradas del proyecto."""
    key_b64 = _decrypt(p.github_app_private_key_enc)
    return _get_installation_token(int(p.github_installation_id), p.github_app_id, key_b64)


# ── Request schemas ───────────────────────────────────────────────────────────

class ConnectBody(BaseModel):
    app_id:              str    # GitHub App ID (número, pasado como string)
    app_private_key_b64: str    # PEM de la App codificado en base64 (sin saltos de línea)
    installation_id:     int    # Installation ID del repo/org
    owner:               str
    repo:                str
    create_repo:         bool = False
    repo_private:        bool = True
    repo_description:    str  = ""

class ProposeBody(BaseModel):
    content_type: str
    content_id:   str
    message:      str
    pr_title:     Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/github/status")
def github_status(
    project_id: str,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Estado de la GitHub App del proyecto."""
    require_project_member(project_id, user, db)
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    connected = bool(
        p.github_owner and p.github_repo
        and p.github_installation_id
        and p.github_app_id and p.github_app_private_key_enc
    )
    return {
        "connected":       connected,
        "owner":           p.github_owner,
        "repo":            p.github_repo,
        "installation_id": p.github_installation_id,
        "repo_url": f"https://github.com/{p.github_owner}/{p.github_repo}" if connected else None,
    }


@router.post("/{project_id}/github/connect")
def github_connect(
    project_id: str,
    body: ConnectBody,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Conecta GitHub App al proyecto (crea repo si se solicita). Solo PI."""
    require_project_member(project_id, user, db, min_role="PI")
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")

    app_id  = body.app_id.strip()
    key_b64 = body.app_private_key_b64.strip()

    # Validate credentials by attempting to exchange for an installation token
    try:
        gh_token = _get_installation_token(body.installation_id, app_id, key_b64)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Could not authenticate with the installation: {exc}")

    if body.create_repo:
        try:
            app_jwt      = _make_app_jwt(app_id, key_b64)
            install_data = _gh("GET", f"/app/installations/{body.installation_id}", app_jwt)
            account_type = install_data.get("account", {}).get("type", "User")
            create_body  = {
                "name":        body.repo.strip(),
                "description": body.repo_description or f"Repositorio del proyecto: {p.name}",
                "private":     body.repo_private,
                "auto_init":   True,
            }
            if account_type == "Organization":
                _gh("POST", f"/orgs/{body.owner}/repos", gh_token, create_body)
            else:
                _gh("POST", "/user/repos", gh_token, create_body)
        except HTTPException as e:
            if e.status_code not in (422, 409):   # 422/409 = ya existe
                raise HTTPException(e.status_code, f"Error al crear el repositorio: {e.detail}")

    try:
        repo_data = _gh("GET", f"/repos/{body.owner}/{body.repo}", gh_token)
    except HTTPException as e:
        if e.status_code == 404:
            raise HTTPException(404,
                f"Repository {body.owner}/{body.repo} not found. "
                "Make sure the App is installed on this repo.")
        raise

    # Persist — encrypt private key before storing
    p.github_app_id              = app_id
    p.github_app_private_key_enc = _encrypt(key_b64)
    p.github_installation_id     = str(body.installation_id)
    p.github_owner               = body.owner.strip()
    p.github_repo                = body.repo.strip()
    db.commit()
    return {
        "connected":       True,
        "owner":           p.github_owner,
        "repo":            p.github_repo,
        "installation_id": p.github_installation_id,
        "repo_url":        f"https://github.com/{p.github_owner}/{p.github_repo}",
        "private":         repo_data.get("private", True),
        "default_branch":  repo_data.get("default_branch", "main"),
        "created":         body.create_repo,
    }


@router.delete("/{project_id}/github/disconnect", status_code=204)
def github_disconnect(
    project_id: str,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Desconecta la GitHub App del proyecto. Solo PI."""
    require_project_member(project_id, user, db, min_role="PI")
    p = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not p:
        raise HTTPException(404, "Project not found")
    p.github_app_id              = None
    p.github_app_private_key_enc = None
    p.github_installation_id     = None
    p.github_owner               = None
    p.github_repo                = None
    db.commit()


@router.post("/{project_id}/github/propose")
def github_propose(
    project_id: str,
    body: ProposeBody,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Crea branch + commit con footer de autoría + abre PR."""
    require_project_member(project_id, user, db)
    p        = _get_project_connected(project_id, db)
    gh_token = _project_gh_token(p)
    owner, repo = p.github_owner, p.github_repo

    MODEL_MAP = {
        "note":       models.Note,
        "hypothesis": models.Hypothesis,
        "journal":    models.JournalEntry,
        "milestone":  models.Milestone,
        "reference":  models.Reference,
    }
    Model = MODEL_MAP.get(body.content_type)
    if not Model:
        raise HTTPException(400,
            "content_type must be note, hypothesis, journal, milestone or reference")

    obj = db.query(Model).filter(
        Model.id == body.content_id,
        Model.project_id == project_id,
    ).first()
    if not obj:
        raise HTTPException(404, "Content not found")

    file_path, md_content = _to_markdown(body.content_type, obj, user)

    repo_data      = _gh("GET", f"/repos/{owner}/{repo}", gh_token)
    default_branch = repo_data.get("default_branch", "main")
    ref_data       = _gh("GET", f"/repos/{owner}/{repo}/git/ref/heads/{default_branch}", gh_token)
    base_sha       = ref_data["object"]["sha"]

    ts        = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    user_slug = _slugify(user.name)[:20]
    branch    = f"propose/{user_slug}-{ts}"
    _gh("POST", f"/repos/{owner}/{repo}/git/refs", gh_token, {
        "ref": f"refs/heads/{branch}", "sha": base_sha,
    })

    commit_msg  = body.message.strip()
    commit_msg += f"\n\nCo-authored-by: {user.name} <{user.email}>"
    content_b64 = base64.b64encode(md_content.encode()).decode()
    _gh("PUT", f"/repos/{owner}/{repo}/contents/{file_path}", gh_token, {
        "message": commit_msg,
        "content": content_b64,
        "branch":  branch,
    })

    pr_title    = (body.pr_title or body.message)[:72]
    author_line = user.name
    if user.title:       author_line = f"{user.title} {author_line}"
    if user.institution: author_line += f" · {user.institution}"
    pr_body = (
        f"Propuesto desde **Aural-Syncro Research Lab** por **{author_line}**\n\n"
        f"| Campo | Valor |\n| --- | --- |\n"
        f"| Proyecto | {p.name} |\n"
        f"| Tipo | {body.content_type} |\n"
        f"| Archivo | `{file_path}` |\n"
    )
    if user.orcid:
        pr_body += f"| ORCID | [{user.orcid}](https://orcid.org/{user.orcid}) |\n"

    pr = _gh("POST", f"/repos/{owner}/{repo}/pulls", gh_token, {
        "title": pr_title, "body": pr_body, "head": branch, "base": default_branch,
    })
    return {
        "pr_number": pr["number"],
        "pr_url":    pr["html_url"],
        "branch":    branch,
        "file_path": file_path,
    }


@router.get("/{project_id}/github/prs")
def github_list_prs(
    project_id: str,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Lista PRs abiertos del repo conectado."""
    require_project_member(project_id, user, db)
    p        = _get_project_connected(project_id, db)
    gh_token = _project_gh_token(p)
    prs      = _gh("GET",
        f"/repos/{p.github_owner}/{p.github_repo}/pulls?state=open&per_page=30",
        gh_token)
    return [
        {
            "number":     pr["number"],
            "title":      pr["title"],
            "author":     pr["user"]["login"],
            "branch":     pr["head"]["ref"],
            "created_at": pr["created_at"],
            "url":        pr["html_url"],
            "body":       (pr.get("body") or "")[:400],
        }
        for pr in prs
    ]


@router.post("/{project_id}/github/prs/{pr_number}/merge")
def github_merge_pr(
    project_id: str,
    pr_number:  int,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Squash merge de un PR. Solo PI."""
    require_project_member(project_id, user, db, min_role="PI")
    p        = _get_project_connected(project_id, db)
    gh_token = _project_gh_token(p)
    result   = _gh("PUT",
        f"/repos/{p.github_owner}/{p.github_repo}/pulls/{pr_number}/merge",
        gh_token,
        {"merge_method": "squash", "commit_title": f"[Lab] Merge PR #{pr_number}"})
    return {"merged": True, "sha": result.get("sha"), "message": result.get("message")}


@router.post("/{project_id}/github/push-graph")
def github_push_graph(
    project_id: str,
    db:   Session     = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Exporta el Knowledge Graph como diagrama Mermaid y hace commit directo al repo."""
    require_project_member(project_id, user, db)
    p        = _get_project_connected(project_id, db)
    gh_token = _project_gh_token(p)
    owner, repo = p.github_owner, p.github_repo

    relations = db.query(models.Relation).filter(
        models.Relation.project_id == project_id
    ).all()
    if not relations:
        raise HTTPException(400, "Project has no relations in the Knowledge Graph")

    node_cache: dict = {}
    def _node_label(node_id: str, node_type: str) -> str:
        key = f"{node_type}:{node_id}"
        if key in node_cache:
            return node_cache[key]
        MODEL_MAP = {
            "hypothesis": models.Hypothesis, "note": models.Note,
            "milestone":  models.Milestone,  "reference": models.Reference,
            "journal":    models.JournalEntry,
        }
        M = MODEL_MAP.get(node_type)
        if M:
            obj = db.query(M).filter(M.id == node_id).first()
            if obj:
                lbl = getattr(obj, "title", None) or str(getattr(obj, "body", node_id))[:40]
                lbl = lbl.replace('"', "'").replace("\n", " ")
                node_cache[key] = lbl
                return lbl
        fallback = node_id[:8]
        node_cache[key] = fallback
        return fallback

    lines     = ["# Knowledge Graph\n", f"\n*Proyecto: {p.name}*\n", "\n```mermaid", "graph LR"]
    node_ids: set = set()
    for r in relations:
        fk = re.sub(r"[^a-zA-Z0-9]", "_", f"{r.from_type}_{r.from_id[:8]}")
        tk = re.sub(r"[^a-zA-Z0-9]", "_", f"{r.to_type}_{r.to_id[:8]}")
        if fk not in node_ids:
            lines.append(f'    {fk}["{_node_label(r.from_id, r.from_type)}"]')
            node_ids.add(fk)
        if tk not in node_ids:
            lines.append(f'    {tk}["{_node_label(r.to_id, r.to_type)}"]')
            node_ids.add(tk)
        arrow = "-->" if not r.auto else "-.->"
        lines.append(f'    {fk} {arrow}|"{r.label}"| {tk}')
    lines += [
        "```",
        f"\n\n*Generado desde Aural-Syncro Research Lab · "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n",
    ]
    md_content = "\n".join(lines)
    file_path  = "lab/knowledge-graph.md"

    repo_data      = _gh("GET", f"/repos/{owner}/{repo}", gh_token)
    default_branch = repo_data.get("default_branch", "main")

    sha = None
    try:
        existing = _gh("GET", f"/repos/{owner}/{repo}/contents/{file_path}", gh_token)
        sha = existing.get("sha")
    except HTTPException:
        pass

    put_body = {
        "message": (f"chore(graph): snapshot knowledge graph "
                    f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}]"),
        "content": base64.b64encode(md_content.encode()).decode(),
        "branch":  default_branch,
    }
    if sha:
        put_body["sha"] = sha
    _gh("PUT", f"/repos/{owner}/{repo}/contents/{file_path}", gh_token, put_body)

    return {"pushed": True, "file_path": file_path, "relations": len(relations)}
