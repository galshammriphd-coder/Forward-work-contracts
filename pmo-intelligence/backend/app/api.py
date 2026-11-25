"""Domain endpoints: auth, dashboard, projects, schedule, finance, risk, knowledge,
initiation wizard, governance, automation, reports, copilot and administration."""
from __future__ import annotations

import base64
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m, security
from .db import get_db
from .engines import alerts as alert_engine
from .engines import evm as evm_engine
from .engines import risk as risk_engine
from .engines.scheduling import ScheduleError
from .rag import answer as rag_answer
from .rag import compare as rag_compare
from .rag import retrieval
from .services import automation, copilot, core, initiation, knowledge, reports

router = APIRouter(prefix="/api")
User = Depends(security.current_user)
DB = Depends(get_db)
LIFECYCLE = ["idea", "initiation", "charter", "business_case", "planning", "execution", "monitoring", "closure", "benefits", "lessons"]


def _d(v):
    return date.fromisoformat(v[:10]) if v else None


# ---------- auth ----------
@router.post("/auth/login")
def login(request: Request, data: dict = Body(...), db: Session = DB):
    email = str(data.get("email", "")).strip().lower()
    since = datetime.utcnow() - timedelta(minutes=15)
    recent = [a for a in db.scalars(select(m.AuditLog).where(m.AuditLog.action == "auth.login_failed", m.AuditLog.created_at >= since))
              if str((a.detail or {}).get("email", "")).lower() == email]
    if len(recent) >= 8:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")
    u = db.scalar(select(m.User).where(func.lower(m.User.email) == email))
    if not u or not u.is_active or not security.verify_password(data.get("password", ""), u.password_hash):
        security.audit(db, None, "auth.login_failed", "user", None, None, {"email": data.get("email")}, request)
        db.commit()
        raise HTTPException(401, "Email or password is incorrect")
    if u.mfa_enabled:
        if not data.get("code"):
            return {"mfa_required": True}
        if not security.verify_totp(u.mfa_secret, data["code"]):
            raise HTTPException(401, "The verification code is incorrect")
    security.audit(db, u, "auth.login", "user", u.id, None, {}, request)
    db.commit()
    return {"token": security.make_token(u), "user": _me(u)}


def _me(u: m.User) -> dict:
    return {**core.to_dict(u), "role_key": u.role.key, "role_name_ar": u.role.name_ar, "role_name_en": u.role.name_en,
            "permissions": sorted(security.perms(u)), "all_projects": u.role.all_projects}


@router.get("/auth/me")
def me(user=User):
    return _me(user)


@router.post("/auth/logout")
def logout(db: Session = DB, user=User):
    user.token_version = (user.token_version or 0) + 1  # revokes every session of this user
    db.commit()
    return {"ok": True}


@router.post("/auth/mfa/setup")
def mfa_setup(db: Session = DB, user=User):
    user.mfa_secret = base64.b32encode(os.urandom(20)).decode()
    db.commit()
    return {"secret": user.mfa_secret, "uri": f"otpauth://totp/AI-Powered%20PMO%20Platform:{user.email}?secret={user.mfa_secret}&issuer=AI-Powered%20PMO%20Platform"}


@router.post("/auth/mfa/enable")
def mfa_enable(data: dict = Body(...), db: Session = DB, user=User):
    if data.get("disable"):
        user.mfa_enabled = False
    else:
        if not user.mfa_secret or not security.verify_totp(user.mfa_secret, data.get("code", "")):
            raise HTTPException(400, "The verification code is incorrect")
        user.mfa_enabled = True
    security.audit(db, user, "auth.mfa_change", "user", user.id, None, {"enabled": user.mfa_enabled})
    db.commit()
    return {"mfa_enabled": user.mfa_enabled}


# ---------- meta, dashboard, search ----------
@router.get("/meta")
def meta(db: Session = DB, user=User):
    return {"lifecycle": LIFECYCLE, "doc_types": knowledge.DOC_TYPES, "report_types": [{"key": k, "name_ar": v[0], "name_en": v[1], "needs_project": v[2]} for k, v in reports.TYPES.items()],
            "events": automation.EVENTS, "actions": automation.ACTIONS, "roles": [{"key": r.key, "name_ar": r.name_ar, "name_en": r.name_en} for r in db.scalars(select(m.Role))],
            "users": [{"id": u.id, "name_ar": u.name_ar, "name_en": u.name_en, "role_key": u.role.key} for u in db.scalars(select(m.User).where(m.User.is_active))],
            "settings": core.get_settings(db), "severities": alert_engine.SEVERITIES}


@router.get("/dashboard")
def dashboard(db: Session = DB, user=security.need("project.read")):
    return core.dashboard(db, user)


@router.get("/search")
def search(q: str, db: Session = DB, user=security.need("project.read")):
    q = q.strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    ids = [p.id for p in core.visible_projects(db, user)]
    out = []
    for p in db.scalars(select(m.Project).where(m.Project.id.in_(ids), m.Project.name_ar.ilike(like) | m.Project.name_en.ilike(like) | m.Project.code.ilike(like)).limit(8)):
        out.append({"type": "project", "id": p.id, "project_id": p.id, "label": p.name_ar, "label_en": p.name_en, "sub": p.code})
    for a in db.scalars(select(m.Activity).where(m.Activity.project_id.in_(ids), m.Activity.name.ilike(like)).limit(8)):
        out.append({"type": "activity", "id": a.id, "project_id": a.project_id, "label": a.name, "sub": a.wbs_code})
    for r in db.scalars(select(m.Risk).where(m.Risk.project_id.in_(ids), m.Risk.title.ilike(like)).limit(8)):
        out.append({"type": "risk", "id": r.id, "project_id": r.project_id, "label": r.title, "sub": r.code})
    if security.has(user, "docs.read"):
        for d in db.scalars(select(m.Document).where(m.Document.project_id.in_(ids), m.Document.name.ilike(like)).limit(8)):
            if security.can_read_document(user, d):
                out.append({"type": "document", "id": d.id, "project_id": d.project_id, "label": d.name, "sub": d.doc_type})
    return out


@router.get("/strategy")
def strategy(db: Session = DB, user=security.need("portfolio.read")):
    cards = [core.project_card(db, p) for p in core.visible_projects(db, user)]
    out = []
    for o in db.scalars(select(m.StrategicObjective).order_by(m.StrategicObjective.code)):
        mine = [c for c in cards if c["objective_id"] == o.id]
        bens = [b for b in db.scalars(select(m.Benefit).where(m.Benefit.objective_id == o.id)) if b.project_id in {c["id"] for c in cards}]
        real = [reports.benefit_gap(b)["realization"] for b in bens]
        real = [r for r in real if r is not None]
        tb = sum(c["budget"] or 0 for c in mine)
        out.append({**core.to_dict(o), "projects": [{"id": c["id"], "code": c["code"], "name_ar": c["name_ar"], "name_en": c["name_en"], "status": c["status"],
                                                    "progress": c["metrics"]["progress"], "health": c["metrics"]["health"], "budget": c["budget"]} for c in mine],
                    "budget": tb, "progress": round(sum((c["budget"] or 0) * c["metrics"]["progress"] for c in mine) / tb, 1) if tb else 0,
                    "benefits": len(bens), "benefits_measured": len(real), "benefit_realization": round(sum(min(r, 100) for r in real) / len(real), 1) if real else None})
    unaligned = [{"id": c["id"], "code": c["code"], "name_ar": c["name_ar"], "name_en": c["name_en"]} for c in cards if not c["objective_id"]]
    return {"objectives": out, "unaligned": unaligned}


# ---------- projects ----------
@router.get("/projects")
def projects(db: Session = DB, user=security.need("project.read")):
    return [core.project_card(db, p) for p in core.visible_projects(db, user)]


@router.post("/projects")
def create_project(request: Request, data: dict = Body(...), db: Session = DB, user=security.need("project.write")):
    if not (data.get("name_ar") or data.get("name_en")):
        raise HTTPException(400, "Enter a project name")
    vals = core.coerce(m.Project, data)
    vals.setdefault("name_ar", vals.get("name_en")); vals.setdefault("name_en", vals.get("name_ar"))
    if not vals.get("code"):
        vals["code"] = f"PRJ-{date.today().year}-{(db.scalar(select(func.max(m.Project.id))) or 0) + 1:03d}"
    if db.scalar(select(m.Project).where(m.Project.code == vals["code"])):
        raise HTTPException(400, f"Project code {vals['code']} is already used")
    vals.setdefault("manager_id", user.id)
    p = m.Project(**vals)
    db.add(p); db.flush()
    db.add(m.ProjectMember(project_id=p.id, user_id=user.id, project_role="creator"))
    security.audit(db, user, "project.create", "project", p.id, p.id, {"code": p.code}, request)
    automation.emit(db, "project.created", {"project_id": p.id, "created_from": "manual"})
    db.commit()
    return core.project_card(db, p)


@router.get("/projects/{pid}")
def project(pid: int, db: Session = DB, user=User):
    p = security.require_project(db, user, pid)
    card = core.project_card(db, p)
    cnt = lambda model: db.scalar(select(func.count()).select_from(model).where(model.project_id == pid))
    ch = db.scalar(select(m.ProjectCharter).where(m.ProjectCharter.project_id == pid))
    members = db.execute(select(m.ProjectMember, m.User).join(m.User, m.User.id == m.ProjectMember.user_id).where(m.ProjectMember.project_id == pid)).all()
    card.update(
        counts={k: cnt(v) for k, v in {"activities": m.Activity, "risks": m.Risk, "issues": m.Issue, "documents": m.Document, "milestones": m.Milestone,
                                       "stakeholders": m.Stakeholder, "changes": m.ChangeRequest, "decisions": m.Decision, "kpis": m.KPI, "benefits": m.Benefit}.items()},
        phases=[core.to_dict(x) for x in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == pid).order_by(m.ProjectPhase.order))],
        alerts=[core.to_dict(a) for a in db.scalars(select(m.Alert).where(m.Alert.project_id == pid, m.Alert.status != "resolved").order_by(m.Alert.id.desc()))],
        charter=core.to_dict(ch) if ch else None,
        members=[{"id": mem.id, "user_id": u.id, "name_ar": u.name_ar, "name_en": u.name_en, "project_role": mem.project_role, "role_key": u.role.key} for mem, u in members],
        approvals=[core.to_dict(a) for a in db.scalars(select(m.Approval).where(m.Approval.project_id == pid).order_by(m.Approval.id.desc()))],
        progress_log=[core.to_dict(a) for a in db.scalars(select(m.AuditLog).where(m.AuditLog.project_id == pid).order_by(m.AuditLog.id.desc()).limit(25))]
        if security.has(user, "project.write") else [])
    return card


@router.patch("/projects/{pid}")
def update_project(pid: int, request: Request, data: dict = Body(...), db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "project.write")
    was = p.status
    changes = {}
    for k, v in core.coerce(m.Project, data).items():
        if k not in ("code",) and getattr(p, k) != v:
            changes[k] = [str(getattr(p, k)), str(v)]
            setattr(p, k, v)
    p.last_update_at = datetime.utcnow()
    security.audit(db, user, "project.update", "project", pid, pid, {"changes": changes}, request)
    if "start_date" in changes:
        try:
            core.recompute_schedule(db, p)
        except ScheduleError as e:
            raise HTTPException(400, str(e))
    if p.status == "completed" and was != "completed":
        p.stage = "closure"
        automation.emit(db, "project.completed", {"project_id": pid})
    core.run_early_warning(db, pid)
    db.commit()
    return core.project_card(db, p)


@router.delete("/projects/{pid}")
def delete_project(pid: int, request: Request, db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "project.write")
    if user.role.key not in ("super_admin", "pmo_director") and p.manager_id != user.id:
        raise HTTPException(403, "Only the project manager or the PMO director can delete a project")
    security.audit(db, user, "project.delete", "project", pid, pid, {"code": p.code, "name": p.name_ar}, request)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/members")
def add_member(pid: int, data: dict = Body(...), db: Session = DB, user=User):
    security.require_project(db, user, pid, "project.write")
    if not db.get(m.User, data.get("user_id") or 0):
        raise HTTPException(400, "Choose a user")
    if not db.scalar(select(m.ProjectMember).where(m.ProjectMember.project_id == pid, m.ProjectMember.user_id == data["user_id"])):
        db.add(m.ProjectMember(project_id=pid, user_id=data["user_id"], project_role=data.get("project_role", "member")))
        security.audit(db, user, "project.member_add", "project", pid, pid, {"user_id": data["user_id"]})
    db.commit()
    return {"ok": True}


@router.delete("/projects/{pid}/members/{mid}")
def remove_member(pid: int, mid: int, db: Session = DB, user=User):
    security.require_project(db, user, pid, "project.write")
    mem = db.get(m.ProjectMember, mid)
    if mem and mem.project_id == pid:
        security.audit(db, user, "project.member_remove", "project", pid, pid, {"user_id": mem.user_id})
        db.delete(mem)
    db.commit()
    return {"ok": True}


# ---------- schedule ----------
@router.get("/projects/{pid}/schedule")
def schedule(pid: int, db: Session = DB, user=User):
    p = security.require_project(db, user, pid)
    acts = list(db.scalars(select(m.Activity).where(m.Activity.project_id == pid).order_by(m.Activity.order, m.Activity.id)))
    parents = {a.parent_id for a in acts if a.parent_id}
    bl = core.current_baseline(db, pid)
    cal = core.get_settings(db)["work_calendar"]
    return {"project": {"id": p.id, "start_date": p.start_date, "end_date": p.end_date},
            "activities": [{**core.to_dict(a), "is_summary": a.id in parents} for a in acts],
            "dependencies": [core.to_dict(d) for d in db.scalars(select(m.Dependency).where(m.Dependency.project_id == pid))],
            "milestones": [core.to_dict(x) for x in db.scalars(select(m.Milestone).where(m.Milestone.project_id == pid).order_by(m.Milestone.target_date))],
            "phases": [core.to_dict(x) for x in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == pid).order_by(m.ProjectPhase.order))],
            "wbs": [core.to_dict(x) for x in db.scalars(select(m.WBSElement).where(m.WBSElement.project_id == pid).order_by(m.WBSElement.code))],
            "baseline": {"id": bl.id, "name": bl.name, "created_at": bl.created_at, **bl.snapshot} if bl else None,
            "baselines": [{"id": b.id, "name": b.name, "created_at": b.created_at, "is_current": b.is_current, "finish": b.snapshot.get("finish")}
                          for b in db.scalars(select(m.Baseline).where(m.Baseline.project_id == pid).order_by(m.Baseline.id))],
            "calendar": cal, "finish": max((a.planned_end for a in acts if a.planned_end), default=None),
            "critical_path": [a.id for a in sorted(acts, key=lambda a: a.planned_start or date.min) if a.is_critical and a.id not in parents]}


@router.post("/projects/{pid}/schedule/recalculate")
def recalc(pid: int, db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "schedule.write")
    try:
        res = core.recompute_schedule(db, p)
    except ScheduleError as e:
        raise HTTPException(400, str(e))
    security.audit(db, user, "schedule.recalculate", "project", pid, pid, {"finish": str(res["finish"])})
    core.run_early_warning(db, pid)
    db.commit()
    return {"finish": res["finish"], "duration": res["duration"], "critical_path": res["critical_path"]}


@router.post("/projects/{pid}/baselines")
def new_baseline(pid: int, data: dict = Body(default={}), db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "schedule.write")
    n = db.scalar(select(func.count()).select_from(m.Baseline).where(m.Baseline.project_id == pid)) or 0
    b = core.create_baseline(db, p, user, data.get("name") or f"Baseline {n + 1}")
    security.audit(db, user, "baseline.create", "baseline", b.id, pid, {"name": b.name})
    db.commit()
    return {"id": b.id, "name": b.name}


@router.put("/settings/{key}")
def put_setting(key: str, request: Request, value: dict = Body(...), db: Session = DB, user=security.need("admin.settings")):
    if key not in core.get_settings(db):
        raise HTTPException(404, "Unknown setting")
    if key == "risk_thresholds":
        v = [int(value.get(k, 0)) for k in ("low", "moderate", "high")]
        if not (0 < v[0] < v[1] < v[2] < 25):
            raise HTTPException(400, "Thresholds must increase: low < moderate < high < 25")
        core.set_setting(db, key, dict(zip(("low", "moderate", "high"), v)))
        db.flush()
        th = core.get_settings(db)["risk_thresholds"]
        for r in db.scalars(select(m.Risk)):  # reclassify every risk with the new limits
            r.level = risk_engine.classify(r.score or 1, th)
    else:
        core.set_setting(db, key, value)
    security.audit(db, user, "settings.update", "setting", None, None, {"key": key, "value": value}, request)
    db.flush()
    if key == "work_calendar":
        for p in db.scalars(select(m.Project).where(m.Project.status.in_(["planned", "active"]))):
            core.recompute_schedule(db, p)
    core.run_early_warning(db)
    db.commit()
    return core.get_settings(db)


# ---------- finance ----------
@router.get("/projects/{pid}/finance")
def finance(pid: int, db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "finance.read")
    mt = core.project_metrics(db, p)
    acts = core.leaf_activities(list(db.scalars(select(m.Activity).where(m.Activity.project_id == pid))))
    costs = list(db.scalars(select(m.Cost).where(m.Cost.project_id == pid)))
    phases = list(db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == pid).order_by(m.ProjectPhase.order)))
    adicts = [{"planned_start": a.planned_start, "planned_end": a.planned_end, "progress": a.progress, "weight": a.weight,
               "estimated_cost": a.estimated_cost, "duration_days": a.duration_days} for a in acts]
    start = p.start_date or min((a.planned_start for a in acts if a.planned_start), default=None)
    end = max([a.planned_end for a in acts if a.planned_end] + ([p.end_date] if p.end_date else []), default=None)
    curve = evm_engine.s_curve(p.budget or 0, adicts, [(c.cost_date, c.amount) for c in costs if c.kind == "actual"], start, end, date.today()) if start and end else []
    months: dict = {}
    for c in costs:
        if c.cost_date:
            k = c.cost_date.strftime("%Y-%m")
            months.setdefault(k, {"month": k, "actual": 0, "commitment": 0})[c.kind] += c.amount
    last = max((c.cost_date for c in costs if c.cost_date), default=None)
    return {"metrics": mt, "s_curve": curve, "cash_flow": [months[k] for k in sorted(months)],
            "by_phase": [{"phase": ph.name, "planned": sum(a.estimated_cost or 0 for a in acts if a.phase_id == ph.id),
                          "actual": sum(c.amount for c in costs if c.kind == "actual" and (c.phase_id == ph.id or (c.activity_id and any(a.id == c.activity_id and a.phase_id == ph.id for a in acts))))} for ph in phases],
            "by_activity": sorted([{"activity": a.name, "wbs_code": a.wbs_code, "planned": a.estimated_cost or 0,
                                    "actual": sum(c.amount for c in costs if c.kind == "actual" and c.activity_id == a.id)} for a in acts], key=lambda x: -x["planned"])[:15],
            "source": {"budget": "projects.budget", "actual": "costs (kind = actual)", "progress": "activities.progress",
                       "last_cost_entry": last, "last_project_update": p.last_update_at}}


# ---------- risk ----------
@router.get("/risks/heatmap")
def heatmap(project_id: int | None = None, db: Session = DB, user=security.need("project.read")):
    if project_id:
        security.require_project(db, user, project_id)
        ids = [project_id]
    else:
        ids = [p.id for p in core.visible_projects(db, user)]
    th = core.get_settings(db)["risk_thresholds"]
    rows = [{"id": r.id, "score": r.score, "level": r.level, "shared_key": r.shared_key, "probability": r.probability, "impact": r.impact}
            for r in db.scalars(select(m.Risk).where(m.Risk.project_id.in_(ids), m.Risk.status != "closed"))]
    return {"grid": risk_engine.heatmap(rows, th), "counts": risk_engine.counts(rows), "thresholds": th,
            "total_rows": len(rows), "unique": len(risk_engine.unique(rows))}


# ---------- RACI & resources ----------
@router.get("/projects/{pid}/raci")
def raci(pid: int, db: Session = DB, user=User):
    security.require_project(db, user, pid)
    rows = list(db.scalars(select(m.RACIAssignment).where(m.RACIAssignment.project_id == pid)))
    parties = sorted({r.party for r in rows} | {s.name for s in db.scalars(select(m.Stakeholder).where(m.Stakeholder.project_id == pid))})
    acts = core.leaf_activities(list(db.scalars(select(m.Activity).where(m.Activity.project_id == pid).order_by(m.Activity.order, m.Activity.id))))
    cells = {f"{r.activity_id}|{r.party}": r.raci for r in rows}
    issues = [a.id for a in acts if sum(1 for r in rows if r.activity_id == a.id and r.raci == "A") != 1]
    return {"parties": parties, "activities": [{"id": a.id, "name": a.name, "wbs_code": a.wbs_code} for a in acts], "cells": cells, "needs_one_accountable": issues}


@router.put("/projects/{pid}/raci")
def set_raci(pid: int, data: dict = Body(...), db: Session = DB, user=User):
    security.require_project(db, user, pid, "project.write")
    a = db.get(m.Activity, data.get("activity_id") or 0)
    if not a or a.project_id != pid or not data.get("party"):
        raise HTTPException(400, "Choose an activity and a party")
    row = db.scalar(select(m.RACIAssignment).where(m.RACIAssignment.activity_id == a.id, m.RACIAssignment.party == data["party"]))
    val = (data.get("raci") or "").upper()
    if val not in ("", "R", "A", "C", "I"):
        raise HTTPException(400, "Value must be R, A, C or I")
    if not val:
        if row:
            db.delete(row)
    elif row:
        row.raci = val
    else:
        db.add(m.RACIAssignment(project_id=pid, activity_id=a.id, party=data["party"], raci=val))
    db.commit()
    return {"ok": True}


@router.get("/resources/utilization")
def utilization(project_id: int | None = None, db: Session = DB, user=security.need("project.read")):
    if project_id:
        security.require_project(db, user, project_id)
    ids = [project_id] if project_id else None
    rows = reports.resource_utilization(db, ids)
    names = {p.id: p for p in core.visible_projects(db, user)}
    for r in rows:
        for a in r["assignments"]:
            p = names.get(a["project_id"])
            a["project_code"] = p.code if p else "—"  # projects outside the user's scope stay anonymous
            a["project_name_ar"], a["project_name_en"] = (p.name_ar, p.name_en) if p else ("مشروع آخر", "Another project")
    return rows


# ---------- documents & knowledge ----------
def _doc(db: Session, user, doc_id: int, write=False) -> m.Document:
    d = db.get(m.Document, doc_id)
    if not d or not security.can_access_project(db, user, d.project_id) or not security.has(user, "docs.read") or not security.can_read_document(user, d):
        raise HTTPException(404, "Document not found")
    if write:
        security.require(user, "docs.write")
    return d


@router.get("/projects/{pid}/documents")
def documents(pid: int, db: Session = DB, user=User):
    security.require_project(db, user, pid, "docs.read")
    return [knowledge.doc_dict(d) for d in security.readable_documents_query(db, user, pid) or []]


@router.post("/projects/{pid}/documents")
async def upload(pid: int, file: UploadFile = File(...), doc_type: str = Form("other"), name: str = Form(""), folder: str = Form("/"),
                 tags: str = Form(""), confidentiality: int = Form(1), access_roles: str = Form(""), doc_date: str = Form(""),
                 approval_status: str = Form("draft"), db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "docs.write")
    if confidentiality > (user.role.clearance or 0):
        raise HTTPException(403, "You cannot classify a document above your own clearance")
    try:
        d = knowledge.save_upload(db, user, p, file.filename, await file.read(), doc_type=doc_type, name=name or None, folder=folder,
                                  tags=[t.strip() for t in tags.split(",") if t.strip()], confidentiality=confidentiality,
                                  access_roles=[r.strip() for r in access_roles.split(",") if r.strip()], doc_date=_d(doc_date), approval_status=approval_status)
    except knowledge.UploadError as e:
        raise HTTPException(422, str(e))
    p.last_update_at = datetime.utcnow()
    db.commit()
    return knowledge.doc_dict(d)


@router.post("/documents/{doc_id}/versions")
async def new_version(doc_id: int, file: UploadFile = File(...), note: str = Form(""), db: Session = DB, user=User):
    d = _doc(db, user, doc_id, True)
    try:
        knowledge.add_version(db, user, d, file.filename, await file.read(), note)
    except knowledge.UploadError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return knowledge.doc_dict(d)


@router.patch("/documents/{doc_id}")
def update_doc(doc_id: int, data: dict = Body(...), db: Session = DB, user=User):
    d = _doc(db, user, doc_id, True)
    if int(data.get("confidentiality", 0) or 0) > (user.role.clearance or 0):
        raise HTTPException(403, "You cannot classify a document above your own clearance")
    for k in ("name", "doc_type", "folder", "tags", "confidentiality", "access_roles", "approval_status", "doc_date"):
        if k in data:
            setattr(d, k, _d(data[k]) if k == "doc_date" else data[k])
    security.audit(db, user, "document.update", "document", d.id, d.project_id, {"fields": sorted(data)})
    db.commit()
    return knowledge.doc_dict(d)


@router.delete("/documents/{doc_id}")
def delete_doc(doc_id: int, db: Session = DB, user=User):
    d = _doc(db, user, doc_id, True)
    security.audit(db, user, "document.delete", "document", d.id, d.project_id, {"name": d.name})
    for v in d.versions:
        Path(v.storage_path).unlink(missing_ok=True)
    db.delete(d)
    db.commit()
    return {"ok": True}


@router.post("/documents/{doc_id}/reindex")
def reindex(doc_id: int, db: Session = DB, user=User):
    d = _doc(db, user, doc_id, True)
    knowledge._index(db, d)
    db.commit()
    return knowledge.doc_dict(d)


@router.get("/documents/{doc_id}/download")
def download(doc_id: int, version: int | None = None, db: Session = DB, user=User):
    d = _doc(db, user, doc_id)
    v = next((x for x in d.versions if x.version == (version or d.current_version)), None)
    if not v or not Path(v.storage_path).exists():
        raise HTTPException(404, "File not found")
    security.audit(db, user, "document.download", "document", d.id, d.project_id, {"version": v.version})
    db.commit()
    return FileResponse(v.storage_path, filename=v.filename)


@router.get("/documents/{doc_id}/content")
def content(doc_id: int, version: int | None = None, db: Session = DB, user=User):
    """Parsed content by page and section — the in-app viewer that citations link into."""
    d = _doc(db, user, doc_id)
    chunks = db.scalars(select(m.DocumentChunk).where(m.DocumentChunk.document_id == d.id, m.DocumentChunk.version == (version or d.current_version)).order_by(m.DocumentChunk.ordinal))
    security.audit(db, user, "document.view", "document", d.id, d.project_id, {})
    db.commit()
    return {"document": knowledge.doc_dict(d), "version": version or d.current_version,
            "chunks": [{"id": c.id, "page": c.page, "section": c.section, "kind": c.kind, "text": c.text, "flagged": c.flagged} for c in chunks]}


@router.get("/documents/{doc_id}/summary")
def doc_summary(doc_id: int, db: Session = DB, user=User):
    return rag_answer.summarize(db, [_doc(db, user, doc_id)])


@router.get("/documents/{doc_id}/tables")
def doc_tables(doc_id: int, db: Session = DB, user=User):
    return rag_answer.tables(db, _doc(db, user, doc_id))


@router.get("/documents/{doc_id}/diff")
def doc_diff(doc_id: int, v_from: int, v_to: int, db: Session = DB, user=User):
    return rag_answer.version_diff(db, _doc(db, user, doc_id), v_from, v_to)


@router.post("/projects/{pid}/documents/compare")
def compare_docs(pid: int, data: dict = Body(...), db: Session = DB, user=User):
    security.require_project(db, user, pid, "docs.read")
    a, b = _doc(db, user, data.get("a") or 0), _doc(db, user, data.get("b") or 0)
    if a.project_id != pid or b.project_id != pid or a.id == b.id:
        raise HTTPException(400, "Choose two different documents of this project")
    rows = rag_compare.compare(db, a, b)
    stored = rag_compare.store(db, pid, rows)
    security.audit(db, user, "document.compare", "document", a.id, pid, {"with": b.id, "conflicts": len(rows)})
    db.commit()
    return [{**r, "id": s.id, "review_status": s.review_status} for r, s in zip(rows, stored)]


@router.get("/projects/{pid}/conflicts")
def conflicts(pid: int, db: Session = DB, user=User):
    security.require_project(db, user, pid, "docs.read")
    readable = {d.id: d for d in security.readable_documents_query(db, user, pid) or []}
    out = []
    for c in db.scalars(select(m.DocumentConflict).where(m.DocumentConflict.project_id == pid).order_by(m.DocumentConflict.id.desc())):
        if c.doc_a_id in readable and c.doc_b_id in readable:
            out.append({**core.to_dict(c), "doc_a": readable[c.doc_a_id].name, "doc_b": readable[c.doc_b_id].name})
    return out


@router.patch("/conflicts/{cid}")
def review_conflict(cid: int, data: dict = Body(...), db: Session = DB, user=User):
    c = db.get(m.DocumentConflict, cid)
    if not c:
        raise HTTPException(404, "Not found")
    security.require_project(db, user, c.project_id, "docs.write")
    if data.get("review_status") not in ("open", "accepted_a", "accepted_b", "dismissed"):
        raise HTTPException(400, "Unknown review status")
    c.review_status = data["review_status"]
    security.audit(db, user, "conflict.review", "document_conflict", cid, c.project_id, {"status": c.review_status})
    db.commit()
    return core.to_dict(c)


@router.get("/projects/{pid}/knowledge/search")
def knowledge_search(pid: int, q: str, db: Session = DB, user=User):
    security.require_project(db, user, pid, "docs.read")
    hits = retrieval.retrieve(db, user, pid, q, k=10)
    security.audit(db, user, "knowledge.search", "project", pid, pid, {"q": q[:200], "hits": len(hits)})
    db.commit()
    return [{"chunk_id": h.chunk.id, "document_id": h.doc.id, "document": h.doc.name, "page": h.chunk.page, "section": h.chunk.section,
             "text": h.chunk.text[:400], "score": round(h.score, 3), "coverage": round(h.coverage, 2), "keyword": round(h.bm25, 2), "vector": round(h.vector, 3)} for h in hits]


def _conv(db: Session, user, cid: int) -> m.ProjectConversation:
    c = db.get(m.ProjectConversation, cid)
    if not c or c.user_id != user.id:  # conversations are private to their owner
        raise HTTPException(404, "Conversation not found")
    if c.project_id:
        security.require_project(db, user, c.project_id, "chat.use")
    return c


def _conv_out(c, full=True):
    out = {"id": c.id, "project_id": c.project_id, "title": c.title, "created_at": c.created_at, "scope": c.scope}
    if full:
        out["messages"] = [core.to_dict(x) for x in c.messages]
    return out


@router.get("/projects/{pid}/conversations")
def conversations(pid: int, db: Session = DB, user=User):
    security.require_project(db, user, pid, "chat.use")
    return [_conv_out(c, False) for c in db.scalars(select(m.ProjectConversation).where(
        m.ProjectConversation.project_id == pid, m.ProjectConversation.user_id == user.id).order_by(m.ProjectConversation.id.desc()))]


@router.post("/projects/{pid}/conversations")
def new_conversation(pid: int, db: Session = DB, user=User):
    security.require_project(db, user, pid, "chat.use")
    c = m.ProjectConversation(project_id=pid, user_id=user.id, title="")
    db.add(c); db.commit()
    return _conv_out(c)


@router.get("/conversations/{cid}")
def conversation(cid: int, db: Session = DB, user=User):
    return _conv_out(_conv(db, user, cid))


@router.delete("/conversations/{cid}")
def delete_conversation(cid: int, db: Session = DB, user=User):
    db.delete(_conv(db, user, cid)); db.commit()
    return {"ok": True}


@router.post("/conversations/{cid}/messages")
def ask(cid: int, data: dict = Body(...), db: Session = DB, user=User):
    c = _conv(db, user, cid)
    q = (data.get("question") or "").strip()
    if not q:
        raise HTTPException(400, "Type a question")
    if c.project_id:
        p = security.require_project(db, user, c.project_id, "chat.use")
        versions = data.get("versions", "current")
        try:
            msg = knowledge.chat(db, user, p, c, q, doc_ids=data.get("doc_ids") or None, date_from=_d(data.get("date_from")),
                                 date_to=_d(data.get("date_to")), versions=versions if versions in ("current", "all") else int(versions))
        except retrieval.AccessDenied:
            raise HTTPException(403, "You do not have access to this project's documents")
    else:
        security.require(user, "copilot.use")
        res = copilot.ask(db, user, q)
        db.add(m.ConversationMessage(conversation_id=c.id, role="user", content=q))
        c.title = c.title or q[:70]
        msg = m.ConversationMessage(conversation_id=c.id, role="assistant", blocks=res["blocks"], citations=res["citations"],
                                    content="\n\n".join(b["text"] for b in res["blocks"]))
        db.add(msg)
    db.commit()
    return core.to_dict(msg)


@router.get("/copilot/conversations")
def copilot_conversations(db: Session = DB, user=security.need("copilot.use")):
    return [_conv_out(c, False) for c in db.scalars(select(m.ProjectConversation).where(
        m.ProjectConversation.project_id.is_(None), m.ProjectConversation.user_id == user.id).order_by(m.ProjectConversation.id.desc()))]


@router.post("/copilot/conversations")
def copilot_new(db: Session = DB, user=security.need("copilot.use")):
    c = m.ProjectConversation(project_id=None, user_id=user.id, title="")
    db.add(c); db.commit()
    return _conv_out(c)


@router.post("/export")
def export_text(data: dict = Body(...), user=User):
    """Export a chat answer (or any titled text + tables) to Word, PDF or Excel."""
    fmt = data.get("format", "docx")
    if fmt not in reports.RENDER:
        raise HTTPException(400, "Format must be docx, pdf or xlsx")
    lang = data.get("lang", "ar")
    sections = [{"key": f"t{i}", "kind": "table", "title": t.get("title") or "", "head": t["head"], "rows": t["rows"]} for i, t in enumerate(data.get("tables", []))]
    cites = data.get("citations") or []
    if cites:
        sections.append({"key": "sources", "kind": "table", "title": "المصادر" if lang == "ar" else "Sources",
                         "head": ["#", "الملف" if lang == "ar" else "File", "الصفحة" if lang == "ar" else "Page", "القسم" if lang == "ar" else "Section", "المقتطف" if lang == "ar" else "Excerpt"],
                         "rows": [[c.get("n"), c.get("document"), c.get("page"), c.get("section"), c.get("snippet")] for c in cites]})
    rep = {"type": "export", "lang": lang, "title": data.get("title") or "AI-Powered PMO Platform", "scope": data.get("scope", ""), "period": "",
           "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "summary": [l for l in (data.get("text") or "").split("\n") if l.strip()],
           "summary_label": "الإجابة" if lang == "ar" else "Answer", "comment": "", "comment_label": "", "sections": sections}
    fn, mime = reports.RENDER[fmt]
    return Response(fn(rep), media_type=mime, headers={"Content-Disposition": f'attachment; filename="export.{fmt}"'})


# ---------- initiation wizard ----------
def _session(db, user, sid) -> m.InitiationSession:
    s = db.get(m.InitiationSession, sid)
    if not s or (s.user_id != user.id and user.role.key not in ("super_admin", "pmo_director")):
        raise HTTPException(404, "Session not found")
    return s


def _sess_out(s):
    return {"id": s.id, "filename": s.filename, "language": s.language, "status": s.status, "draft": s.draft,
            "approvals": s.approvals or {}, "project_id": s.project_id, "created_at": s.created_at, "sections": initiation.SECTIONS}


@router.get("/initiation")
def init_list(db: Session = DB, user=security.need("initiation.use")):
    return [{"id": s.id, "filename": s.filename, "status": s.status, "project_id": s.project_id, "created_at": s.created_at,
             "name": (s.draft.get("profile", {}).get("name") or {}).get("value")}
            for s in db.scalars(select(m.InitiationSession).where(m.InitiationSession.user_id == user.id).order_by(m.InitiationSession.id.desc()))]


@router.post("/initiation")
async def init_upload(file: UploadFile = File(...), db: Session = DB, user=security.need("initiation.use")):
    from .rag.parsers import ParseError
    try:
        s = initiation.start(db, user, file.filename, await file.read())
    except (ParseError, knowledge.UploadError) as e:
        db.rollback()
        raise HTTPException(422, str(e))
    db.commit()
    return _sess_out(s)


@router.get("/initiation/{sid}")
def init_get(sid: int, db: Session = DB, user=security.need("initiation.use")):
    return _sess_out(_session(db, user, sid))


@router.post("/initiation/{sid}/generate/{step}")
def init_generate(sid: int, step: str, db: Session = DB, user=security.need("initiation.use")):
    s = _session(db, user, sid)
    try:
        initiation.generate(db, s, step)
    except (ValueError, ScheduleError) as e:
        raise HTTPException(400, str(e))
    db.commit()
    return _sess_out(s)


@router.patch("/initiation/{sid}")
def init_patch(sid: int, data: dict = Body(...), db: Session = DB, user=security.need("initiation.use")):
    s = _session(db, user, sid)
    if s.status == "activated":
        raise HTTPException(400, "This session has already created a project")
    try:
        initiation.update_draft(db, s, data)
    except (ValueError, ScheduleError, KeyError) as e:
        db.rollback()
        raise HTTPException(400, f"Could not apply the change: {e}")
    db.commit()
    return _sess_out(s)


@router.post("/initiation/{sid}/approve")
def init_approve(sid: int, data: dict = Body(...), db: Session = DB, user=security.need("initiation.use")):
    s = _session(db, user, sid)
    try:
        initiation.approve(db, s, user, data.get("section"), data.get("approved", True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return _sess_out(s)


@router.post("/initiation/{sid}/activate")
def init_activate(sid: int, data: dict = Body(default={}), db: Session = DB, user=security.need("initiation.use")):
    s = _session(db, user, sid)
    try:
        p = initiation.activate(db, s, user, data.get("portfolio_id"), data.get("program_id"), data.get("department_id"))
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    core.run_early_warning(db, p.id)
    db.commit()
    return {"project_id": p.id, "code": p.code}


# ---------- governance ----------
@router.get("/approvals")
def approvals(status: str | None = None, db: Session = DB, user=security.need("project.read")):
    ids = {p.id: p for p in core.visible_projects(db, user)}
    q = select(m.Approval).order_by(m.Approval.id.desc())
    if status:
        q = q.where(m.Approval.status == status)
    return [{**core.to_dict(a), "project_code": ids[a.project_id].code if a.project_id else None,
             "project_name_ar": ids[a.project_id].name_ar if a.project_id else None, "project_name_en": ids[a.project_id].name_en if a.project_id else None,
             "can_decide": security.has(user, "approve") and (not a.approver_role or user.role.key in (a.approver_role, "super_admin", "pmo_director"))}
            for a in db.scalars(q) if a.project_id is None or a.project_id in ids]


@router.post("/approvals/{aid}/decide")
def decide(aid: int, request: Request, data: dict = Body(...), db: Session = DB, user=security.need("approve")):
    a = db.get(m.Approval, aid)
    if not a:
        raise HTTPException(404, "Not found")
    if a.project_id:
        security.require_project(db, user, a.project_id)
    try:
        automation.decide(db, a, user, bool(data.get("approve")), data.get("note", ""))
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if a.instance_id is None and a.project_id:  # stand-alone stage-gate approval
        for ph in db.scalars(select(m.ProjectPhase).where(m.ProjectPhase.project_id == a.project_id, m.ProjectPhase.gate_status == "requested")):
            if ph.name in (a.title or ""):
                ph.gate_status = a.status
    security.audit(db, user, "approval.decide", "approval", aid, a.project_id, {"decision": a.status, "note": data.get("note", "")}, request)
    db.commit()
    return core.to_dict(a)


@router.post("/projects/{pid}/workflows")
def start_wf(pid: int, data: dict = Body(...), db: Session = DB, user=User):
    p = security.require_project(db, user, pid, "project.write")
    try:
        inst = automation.start_workflow(db, data.get("key", "project_lifecycle"), p, user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    security.audit(db, user, "workflow.start", "workflow_instance", inst.id, pid, {"key": data.get("key")})
    db.commit()
    return core.to_dict(inst)


@router.get("/workflows/instances")
def wf_instances(db: Session = DB, user=security.need("project.read")):
    ids = {p.id: p for p in core.visible_projects(db, user)}
    defs = {d.id: d for d in db.scalars(select(m.WorkflowDefinition))}
    return [{**core.to_dict(i), "definition_name_ar": defs[i.definition_id].name_ar, "definition_name_en": defs[i.definition_id].name_en,
             "steps": defs[i.definition_id].steps, "project_code": ids[i.project_id].code if i.project_id else None,
             "project_name_ar": ids[i.project_id].name_ar if i.project_id else None, "project_name_en": ids[i.project_id].name_en if i.project_id else None}
            for i in db.scalars(select(m.WorkflowInstance).order_by(m.WorkflowInstance.id.desc())) if i.project_id is None or i.project_id in ids]


@router.post("/phases/{phase_id}/gate")
def request_gate(phase_id: int, db: Session = DB, user=User):
    ph = db.get(m.ProjectPhase, phase_id)
    if not ph:
        raise HTTPException(404, "Not found")
    security.require_project(db, user, ph.project_id, "project.write")
    if ph.gate_status in ("requested", "approved"):
        raise HTTPException(400, "This gate has already been requested or approved")
    ph.gate_status = "requested"
    db.add(m.Approval(project_id=ph.project_id, title=f"اعتماد بوابة المرحلة: {ph.name}", approver_role="pmo_director"))
    security.audit(db, user, "gate.request", "project_phase", ph.id, ph.project_id, {"phase": ph.name})
    db.commit()
    return core.to_dict(ph)


@router.get("/audit")
def audit_log(project_id: int | None = None, action: str | None = None, limit: int = 200, db: Session = DB, user=security.need("audit.read")):
    q = select(m.AuditLog).order_by(m.AuditLog.id.desc()).limit(min(limit, 1000))
    if project_id:
        q = q.where(m.AuditLog.project_id == project_id)
    if action:
        q = q.where(m.AuditLog.action.ilike(f"%{action}%"))
    return [core.to_dict(a) for a in db.scalars(q)]


# ---------- alerts, notifications, automation ----------
@router.get("/alerts")
def alerts(project_id: int | None = None, status: str = "active", db: Session = DB, user=security.need("project.read")):
    ids = {p.id: p for p in core.visible_projects(db, user)}
    q = select(m.Alert).order_by(m.Alert.id.desc())
    if status == "active":
        q = q.where(m.Alert.status != "resolved")
    if project_id:
        q = q.where(m.Alert.project_id == project_id)
    order = {s: i for i, s in enumerate(reversed(alert_engine.SEVERITIES))}
    rows = [a for a in db.scalars(q) if a.project_id in ids]
    rows.sort(key=lambda a: (order.get(a.severity, 9), -a.id))
    return [{**core.to_dict(a), "project_code": ids[a.project_id].code, "project_name_ar": ids[a.project_id].name_ar, "project_name_en": ids[a.project_id].name_en} for a in rows]


@router.post("/alerts/run")
def run_alerts(db: Session = DB, user=security.need("project.read")):
    r = core.run_early_warning(db)
    core.snapshot_risks(db)
    db.commit()
    return r


@router.patch("/alerts/{aid}")
def ack_alert(aid: int, data: dict = Body(...), db: Session = DB, user=User):
    a = db.get(m.Alert, aid)
    if not a:
        raise HTTPException(404, "Not found")
    security.require_project(db, user, a.project_id)
    if data.get("status") in ("open", "acknowledged"):
        a.status = data["status"]
        security.audit(db, user, "alert.acknowledge", "alert", aid, a.project_id, {"status": a.status})
    db.commit()
    return core.to_dict(a)


@router.get("/notifications")
def notifications(db: Session = DB, user=User):
    return [core.to_dict(n) for n in db.scalars(select(m.Notification).where(m.Notification.user_id == user.id).order_by(m.Notification.id.desc()).limit(60))]


@router.post("/notifications/read")
def read_notifications(data: dict = Body(default={}), db: Session = DB, user=User):
    q = select(m.Notification).where(m.Notification.user_id == user.id, m.Notification.is_read.is_(False))
    if data.get("id"):
        q = q.where(m.Notification.id == data["id"])
    for n in db.scalars(q):
        n.is_read = True
    db.commit()
    return {"ok": True}


@router.post("/automation/rules/{rid}/run")
def run_rule(rid: int, data: dict = Body(default={}), db: Session = DB, user=security.need("automation.write")):
    r = db.get(m.AutomationRule, rid)
    if not r:
        raise HTTPException(404, "Not found")
    if data.get("project_id"):
        security.require_project(db, user, data["project_id"])
    run = automation.run_rule(db, r, {k: v for k, v in data.items() if v is not None}, f"manual:{user.email}")
    security.audit(db, user, "automation.manual_run", "automation_rule", rid, data.get("project_id"), {"status": run.status})
    db.commit()
    return core.to_dict(run)


@router.get("/automation/runs")
def runs(limit: int = 100, db: Session = DB, user=security.need("project.read")):
    rules = {r.id: r for r in db.scalars(select(m.AutomationRule))}
    ids = security.accessible_project_ids(db, user)
    return [{**core.to_dict(r), "rule_name_ar": rules[r.rule_id].name_ar, "rule_name_en": rules[r.rule_id].name_en}
            for r in db.scalars(select(m.AutomationRun).order_by(m.AutomationRun.id.desc()).limit(min(limit, 500)))
            if ids is None or r.project_id in ids]


# ---------- reports & copilot ----------
def _report(db, user, data):
    if data.get("project_id"):
        security.require_project(db, user, int(data["project_id"]))
    try:
        return reports.build(db, user, data.get("type", "executive_portfolio"), data.get("lang", "ar"), data.get("project_id"), data.get("portfolio_id"),
                             _d(data.get("date_from")), _d(data.get("date_to")), data.get("include") or None, data.get("comment", ""))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/reports/build")
def build_report(data: dict = Body(...), db: Session = DB, user=security.need("report.read")):
    return _report(db, user, data)


@router.post("/reports/export")
def export_report(data: dict = Body(...), db: Session = DB, user=security.need("report.read")):
    fmt = data.get("format", "pdf")
    if fmt not in reports.RENDER:
        raise HTTPException(400, "Format must be pdf, docx or xlsx")
    rep = _report(db, user, data)
    security.audit(db, user, "report.export", "report", None, data.get("project_id"), {"type": rep["type"], "format": fmt})
    db.commit()
    fn, mime = reports.RENDER[fmt]
    return Response(fn(rep), media_type=mime, headers={"Content-Disposition": f'attachment; filename="{rep["type"]}.{fmt}"'})


@router.post("/copilot/ask")
def copilot_ask(data: dict = Body(...), db: Session = DB, user=security.need("copilot.use")):
    q = (data.get("question") or "").strip()
    if not q:
        raise HTTPException(400, "Type a question")
    res = copilot.ask(db, user, q)
    db.commit()
    return res


# ---------- administration ----------
@router.get("/admin/users")
def users(db: Session = DB, user=security.need("admin.users")):
    return [_me(u) for u in db.scalars(select(m.User).order_by(m.User.id))]


@router.post("/admin/users")
def create_user(request: Request, data: dict = Body(...), db: Session = DB, user=security.need("admin.users")):
    role = db.scalar(select(m.Role).where(m.Role.key == data.get("role_key")))
    if not role or not data.get("email") or len(data.get("password") or "") < 8:
        raise HTTPException(400, "Enter an email, a role and a password of at least 8 characters")
    if db.scalar(select(m.User).where(func.lower(m.User.email) == data["email"].lower())):
        raise HTTPException(400, "This email is already registered")
    u = m.User(email=data["email"].strip(), name_ar=data.get("name_ar") or data.get("name_en"), name_en=data.get("name_en") or data.get("name_ar"),
               password_hash=security.hash_password(data["password"]), role_id=role.id, department_id=data.get("department_id"))
    db.add(u); db.flush()
    security.audit(db, user, "user.create", "user", u.id, None, {"email": u.email, "role": role.key}, request)
    db.commit()
    return _me(u)


@router.patch("/admin/users/{uid}")
def update_user(uid: int, request: Request, data: dict = Body(...), db: Session = DB, user=security.need("admin.users")):
    u = db.get(m.User, uid)
    if not u:
        raise HTTPException(404, "Not found")
    if "role_key" in data:
        role = db.scalar(select(m.Role).where(m.Role.key == data["role_key"]))
        if not role:
            raise HTTPException(400, "Unknown role")
        u.role_id = role.id
    for k in ("name_ar", "name_en", "is_active", "department_id"):
        if k in data:
            setattr(u, k, data[k])
    if data.get("password"):
        if len(data["password"]) < 8:
            raise HTTPException(400, "Password must be at least 8 characters")
        u.password_hash = security.hash_password(data["password"])
        u.token_version = (u.token_version or 0) + 1
    if u.id == user.id and data.get("is_active") is False:
        raise HTTPException(400, "You cannot deactivate your own account")
    security.audit(db, user, "user.update", "user", uid, None, {"fields": sorted(k for k in data if k != "password")}, request)
    db.commit(); db.refresh(u)
    return _me(u)


@router.get("/admin/roles")
def roles(db: Session = DB, user=security.need("admin.users")):
    return {"permissions": [{"key": k, "description": v} for k, v in security.PERMISSIONS.items()],
            "roles": [{**core.to_dict(r), "permissions": sorted(p.key for p in r.permissions)} for r in db.scalars(select(m.Role).order_by(m.Role.id))]}


@router.patch("/admin/roles/{rid}")
def update_role(rid: int, request: Request, data: dict = Body(...), db: Session = DB, user=security.need("admin.users")):
    r = db.get(m.Role, rid)
    if not r:
        raise HTTPException(404, "Not found")
    if r.key == "super_admin":
        raise HTTPException(400, "The Super Administrator role cannot be changed")
    if "permissions" in data:
        r.permissions = list(db.scalars(select(m.Permission).where(m.Permission.key.in_(data["permissions"]))))
    for k in ("all_projects", "clearance"):
        if k in data:
            setattr(r, k, data[k])
    security.audit(db, user, "role.update", "role", rid, None, {"permissions": data.get("permissions")}, request)
    db.commit()
    return {"ok": True}
