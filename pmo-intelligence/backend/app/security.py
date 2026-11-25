"""Authentication (PBKDF2 + JWT, optional TOTP) and authorisation (RBAC + project scope
+ document clearance). Enforced in the service layer — never only in the UI."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from datetime import datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from . import config, models as m
from .db import get_db

PERMISSIONS = {
    "portfolio.read": "View portfolios, programmes and strategy", "portfolio.write": "Manage portfolios and programmes",
    "project.read": "View projects in scope", "project.write": "Create and edit projects",
    "schedule.write": "Edit activities, dependencies and baselines", "risk.write": "Edit risks and responses",
    "finance.read": "View budgets and costs", "finance.write": "Edit budgets and costs",
    "resource.write": "Manage resources and assignments", "docs.read": "Read project documents",
    "docs.write": "Upload and manage documents", "chat.use": "Use project knowledge chat",
    "copilot.use": "Use the PMO Copilot", "initiation.use": "Create projects from a charter",
    "governance.write": "Manage policies, gates and workflows", "approve": "Decide approvals",
    "automation.write": "Manage automation and alert rules", "report.read": "Build and export reports",
    "benefit.write": "Manage benefits and lessons", "admin.users": "Manage users and roles",
    "admin.settings": "Change platform settings", "audit.read": "Read the audit trail",
}
_ALL = set(PERMISSIONS)
_VIEW = {"portfolio.read", "project.read", "finance.read", "docs.read", "report.read", "copilot.use", "chat.use"}
# key: (name_ar, name_en, all_projects, clearance, permissions)
ROLES = {
    "super_admin": ("مدير النظام", "Super Administrator", True, 3, _ALL),
    "pmo_director": ("مدير مكتب إدارة المشاريع", "PMO Director", True, 3, _ALL - {"admin.users"}),
    "portfolio_manager": ("مدير المحفظة", "Portfolio Manager", True, 2, _VIEW | {"portfolio.write", "project.write", "risk.write", "approve", "benefit.write", "initiation.use"}),
    "program_manager": ("مدير البرنامج", "Program Manager", False, 2, _VIEW | {"project.write", "schedule.write", "risk.write", "resource.write", "docs.write", "approve", "benefit.write", "initiation.use"}),
    "project_manager": ("مدير المشروع", "Project Manager", False, 2, _VIEW | {"project.write", "schedule.write", "risk.write", "finance.write", "resource.write", "docs.write", "benefit.write", "initiation.use"}),
    "project_coordinator": ("منسق المشروع", "Project Coordinator", False, 1, _VIEW | {"schedule.write", "docs.write", "risk.write"}),
    "risk_manager": ("مدير المخاطر", "Risk Manager", True, 2, _VIEW | {"risk.write", "automation.write"}),
    "financial_controller": ("المراقب المالي", "Financial Controller", True, 2, _VIEW | {"finance.write", "approve"}),
    "resource_manager": ("مدير الموارد", "Resource Manager", True, 1, _VIEW | {"resource.write"}),
    "team_member": ("عضو فريق", "Team Member", False, 1, {"project.read", "docs.read", "chat.use", "docs.write"}),
    "executive_viewer": ("مطّلع تنفيذي", "Executive Viewer", True, 2, _VIEW),
    "auditor": ("مدقق", "Auditor", True, 3, _VIEW | {"audit.read"}),
}


# ---------- passwords & tokens ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 240_000)
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        return hmac.compare_digest(hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 240_000).hex(), dk)
    except Exception:
        return False


def make_token(user: m.User) -> str:
    exp = datetime.utcnow() + timedelta(minutes=config.TOKEN_TTL_MINUTES)
    return jwt.encode({"sub": str(user.id), "tv": user.token_version or 0, "exp": exp}, config.SECRET_KEY, algorithm="HS256")


def totp(secret_b32: str, at: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret_b32)
    counter = struct.pack(">Q", int((at or time.time()) // step))
    h = hmac.new(key, counter, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


def verify_totp(secret: str, code: str) -> bool:
    now = time.time()
    return any(hmac.compare_digest(totp(secret, now + d * 30), (code or "").strip()) for d in (-1, 0, 1))


def current_user(request: Request, db: Session = Depends(get_db)) -> m.User:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    try:
        data = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Session expired — sign in again")
    user = db.get(m.User, int(data["sub"]))
    if not user or not user.is_active or (user.token_version or 0) != data.get("tv", 0):
        raise HTTPException(401, "Session is no longer valid")
    request.state.user = user
    return user


# ---------- authorisation ----------
def perms(user: m.User) -> set:
    return {p.key for p in user.role.permissions}


def has(user: m.User, perm: str) -> bool:
    return perm in perms(user)


def require(user: m.User, perm: str):
    if not has(user, perm):
        raise HTTPException(403, f"Your role does not allow this action ({perm})")


def need(perm: str):
    def dep(user: m.User = Depends(current_user)):
        require(user, perm)
        return user
    return Depends(dep)


def accessible_project_ids(db: Session, user: m.User):
    """None = every project; otherwise the explicit set this user may see."""
    if user.role.all_projects:
        return None
    ids = set(db.scalars(select(m.ProjectMember.project_id).where(m.ProjectMember.user_id == user.id)))
    ids |= set(db.scalars(select(m.Project.id).where(m.Project.manager_id == user.id)))
    prog = list(db.scalars(select(m.Program.id).where(m.Program.manager_id == user.id)))
    if prog:
        ids |= set(db.scalars(select(m.Project.id).where(m.Project.program_id.in_(prog))))
    return ids


def can_access_project(db: Session, user: m.User, project_id: int) -> bool:
    ids = accessible_project_ids(db, user)
    return ids is None or project_id in ids


def require_project(db: Session, user: m.User, project_id: int, perm: str = "project.read") -> m.Project:
    require(user, perm)
    p = db.get(m.Project, project_id)
    # same answer for "missing" and "not yours": do not reveal that the project exists
    if not p or not can_access_project(db, user, project_id):
        raise HTTPException(404, "Project not found")
    return p


def can_read_document(user: m.User, doc: m.Document) -> bool:
    if doc.uploaded_by == user.id:
        return True
    if doc.access_roles:
        return user.role.key in doc.access_roles
    return (user.role.clearance or 0) >= (doc.confidentiality or 0)


def readable_documents_query(db: Session, user: m.User, project_id: int):
    """Document filter applied in SQL *before* any retrieval happens."""
    if not has(user, "docs.read") or not can_access_project(db, user, project_id):
        return None
    q = select(m.Document).where(m.Document.project_id == project_id)
    docs = [d for d in db.scalars(q) if can_read_document(user, d)]
    return docs


def audit(db: Session, user: m.User | None, action: str, entity_type: str = "", entity_id=None,
          project_id=None, detail: dict | None = None, request: Request | None = None):
    db.add(m.AuditLog(user_id=user.id if user else None, user_email=user.email if user else None,
                      action=action, entity_type=entity_type, entity_id=entity_id, project_id=project_id,
                      detail=detail or {}, ip=request.client.host if request and request.client else None))
